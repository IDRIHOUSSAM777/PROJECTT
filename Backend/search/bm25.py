"""
BM25 (Best Matching 25) Scorer — implémentation canonique d'Okapi BM25.

Formule de référence (Robertson & Zaragoza, 2009) :
    BM25(D, Q) = Σ_{t ∈ Q} IDF(t) · [ tf(t, D) · (k1 + 1) ] / [ tf(t, D) + k1 · (1 − b + b · |D| / avgdl) ]
    IDF(t)    = log( (N − df(t) + 0.5) / (df(t) + 0.5) + 1 )

Paramètres classiques :
    k1 = 1.5   (saturation de tf ; entre 1.2 et 2.0 dans la littérature)
    b  = 0.75  (pénalité de longueur de document)

Les statistiques du corpus (N, avgdl, doc_freq) sont calculées une fois puis
mises en cache dans Redis. Elles sont invalidées par
``data.redis_client.clear_search_cache`` dès que l'inventaire change.
"""

from __future__ import annotations

import json
import logging
import math
import time
from collections import Counter
from typing import Dict, List, Optional

from sqlalchemy.orm import Session, joinedload

from data import models
from search.nlp_service import split_words

logger = logging.getLogger(__name__)

BM25_K1 = 1.5
BM25_B = 0.75
BM25_CACHE_KEY = "bm25:corpus_stats:v2"
BM25_CACHE_TTL = 3600  # 1h — invalidé explicitement par clear_search_cache

# Pondération par champ : un match dans le nom du modèle pèse 3× plus qu'un match
# dans la description. Reproduit le rôle de setweight() de PostgreSQL côté Python.
FIELD_WEIGHTS = {
    "nom_model": 3.0,
    "type_objet": 3.0,
    "nom_marque": 2.0,
    "nom_salle": 2.0,
    "fonctionnalites": 2.0,
    "description": 1.0,
}


class BM25Scorer:
    """
    Scorer BM25 avec statistiques de corpus mises en cache.

    Usage:
        scorer = BM25Scorer()
        scorer.build(db)                # calcule ou lit depuis Redis
        score = scorer.score(tokens, obj)
    """

    def __init__(self, k1: float = BM25_K1, b: float = BM25_B):
        self.k1 = k1
        self.b = b
        self.N: int = 0
        self.avgdl: float = 1.0
        self.doc_freq: Dict[str, int] = {}
        self._built_at: float = 0.0

    # ─────────────────────────────────────────────────────────────────
    # Préparation des stats de corpus
    # ─────────────────────────────────────────────────────────────────
    def _load_from_cache(self) -> bool:
        try:
            from data.redis_client import redis_client
        except Exception:
            return False
        if redis_client is None:
            return False
        try:
            raw = redis_client.get(BM25_CACHE_KEY)
            if not raw:
                return False
            data = json.loads(raw)
            self.N = int(data.get("N", 0))
            self.avgdl = float(data.get("avgdl", 1.0)) or 1.0
            self.doc_freq = {k: int(v) for k, v in data.get("doc_freq", {}).items()}
            self._built_at = time.time()
            return True
        except Exception as exc:
            logger.warning("BM25 cache read failed: %s", exc)
            return False

    def _save_to_cache(self) -> None:
        try:
            from data.redis_client import redis_client
        except Exception:
            return
        if redis_client is None:
            return
        try:
            redis_client.set(
                BM25_CACHE_KEY,
                json.dumps({"N": self.N, "avgdl": self.avgdl, "doc_freq": self.doc_freq}),
                ex=BM25_CACHE_TTL,
            )
        except Exception as exc:
            logger.warning("BM25 cache write failed: %s", exc)

    def build(self, db: Session, force: bool = False) -> None:
        """
        Construit les stats BM25. Les résultats sont cachés dans Redis 1 h.
        La mémoire instance est considérée fraîche pendant 120 s pour éviter
        les appels Redis à chaque requête.
        """
        if not force and self.N > 0 and (time.time() - self._built_at) < 120:
            return
        if not force and self._load_from_cache():
            return

        objets = (
            db.query(models.Objet)
            .options(
                joinedload(models.Objet.salle),
                joinedload(models.Objet.fonctionnalites),
            )
            .all()
        )
        if not objets:
            self.N = 0
            self.avgdl = 1.0
            self.doc_freq = {}
            self._built_at = time.time()
            return

        doc_lengths: List[int] = []
        df: Dict[str, int] = {}

        for obj in objets:
            tokens = self._document_tokens(obj)
            doc_lengths.append(max(1, len(tokens)))
            for tok in set(tokens):
                df[tok] = df.get(tok, 0) + 1

        self.N = len(objets)
        self.avgdl = sum(doc_lengths) / max(1, len(doc_lengths))
        self.doc_freq = df
        self._built_at = time.time()
        self._save_to_cache()
        logger.info("BM25 stats rebuilt: N=%d avgdl=%.2f terms=%d", self.N, self.avgdl, len(df))

    # ─────────────────────────────────────────────────────────────────
    # Composition du document (pondérée par champ)
    # ─────────────────────────────────────────────────────────────────
    def _document_tokens(self, obj) -> List[str]:
        """
        Renvoie la liste pondérée des tokens du document : chaque champ est
        répété selon son poids (``FIELD_WEIGHTS``), reproduisant ``setweight``.
        """
        fields = {
            "nom_model": obj.nom_model or "",
            "type_objet": obj.type_objet or "",
            "nom_marque": obj.nom_marque or "",
            "description": obj.description or "",
            "nom_salle": (obj.salle.nom_salle if obj.salle and obj.salle.nom_salle else ""),
            "fonctionnalites": " ".join(
                f.nom for f in (getattr(obj, "fonctionnalites", None) or []) if f and f.nom
            ),
        }
        tokens: List[str] = []
        for key, value in fields.items():
            if not value:
                continue
            weight = int(round(FIELD_WEIGHTS.get(key, 1.0)))
            field_tokens = split_words(value)
            tokens.extend(field_tokens * weight)
        return tokens

    # ─────────────────────────────────────────────────────────────────
    # Scoring
    # ─────────────────────────────────────────────────────────────────
    def idf(self, term: str) -> float:
        if self.N == 0:
            return 0.0
        df = self.doc_freq.get(term, 0)
        return math.log((self.N - df + 0.5) / (df + 0.5) + 1.0)

    def score(self, query_tokens: List[str], obj) -> float:
        """
        Calcule le score BM25 d'un objet pour une liste de tokens de requête
        (déjà normalisés et dédupliqués, si nécessaire).
        """
        if not query_tokens or self.N == 0:
            return 0.0
        doc_tokens = self._document_tokens(obj)
        if not doc_tokens:
            return 0.0

        tf_counter = Counter(doc_tokens)
        doc_len = len(doc_tokens)
        denom_len_factor = 1.0 - self.b + self.b * (doc_len / max(1.0, self.avgdl))

        score = 0.0
        for term in query_tokens:
            tf = tf_counter.get(term, 0)
            if tf == 0:
                continue
            idf_val = self.idf(term)
            numerator = tf * (self.k1 + 1.0)
            denominator = tf + self.k1 * denom_len_factor
            score += idf_val * (numerator / denominator)
        return score

    def score_batch(self, query_tokens: List[str], objets) -> Dict[int, float]:
        """Renvoie {id_objet: score} pour un lot — évite de recalculer avgdl."""
        if not query_tokens or self.N == 0:
            return {}
        return {int(obj.id_objet): self.score(query_tokens, obj) for obj in objets}


# Singleton partagé entre les requêtes (garde les stats en RAM 120 s)
bm25_scorer = BM25Scorer()
