"""
Semantic Search Service — SmartFind
====================================
Adds a vector-similarity layer on top of the existing BM25 / NLP pipeline.

Model: paraphrase-multilingual-MiniLM-L12-v2
  • Supports French, English, Arabic and 50+ other languages out of the box.
  • 384-dimensional embeddings, runs on CPU in ~20 ms per query.

Flow:
  1. build(db) — generates one embedding per equipment document and stores
     them in Redis as a JSON blob (key: semantic:embeddings:v1).
     The corpus is rebuilt automatically when the cache is invalidated by
     clear_search_cache() (called on every inventory / reservation change).

  2. score(query, obj) — encodes the raw user query and returns the cosine
     similarity [0.0 – 1.0] against the stored embedding for `obj`.

  3. invalidate() — deletes the Redis key so the next search triggers a rebuild.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Dict, List, Optional

import numpy as np
from sqlalchemy.orm import Session, joinedload

from data import models
from search.nlp_service import normalize_text

logger = logging.getLogger(__name__)

# ── Model name ────────────────────────────────────────────────────────────────
SEMANTIC_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

# ── Redis keys ─────────────────────────────────────────────────────────────────
SEMANTIC_CACHE_KEY = "semantic:embeddings:v1"
SEMANTIC_CACHE_TTL = 3600  # 1 h — invalidated explicitly by clear_search_cache

# ── In-memory freshness window (avoids hitting Redis on every request) ─────────
_RAM_CACHE_TTL = 120  # seconds


def _build_document(obj: models.Objet) -> str:
    """Concatenate all searchable text fields into one document string."""
    parts = [
        obj.type_objet or "",
        obj.nom_marque or "",
        obj.nom_model or "",
        obj.description or "",
        (obj.salle.nom_salle if obj.salle and obj.salle.nom_salle else ""),
        " ".join(f.nom for f in (getattr(obj, "fonctionnalites", None) or []) if f and f.nom),
    ]
    return " ".join(p for p in parts if p).strip()


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Fast cosine similarity between two 1-D vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


class SemanticSearchService:
    """
    Singleton service — loaded once at startup, embeddings cached in Redis.
    """

    def __init__(self):
        self._model = None          # lazy-loaded on first use
        self._model_loaded = False

        # In-memory corpus cache:  {obj_id: np.ndarray}
        self._corpus: Dict[int, np.ndarray] = {}
        self._corpus_built_at: float = 0.0

    # ── Model loading ─────────────────────────────────────────────────────────

    def _load_model(self):
        """Lazy-load the sentence-transformer model (triggered on first search)."""
        if self._model_loaded:
            return
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("⚡ Loading semantic model: %s", SEMANTIC_MODEL_NAME)
            self._model = SentenceTransformer(SEMANTIC_MODEL_NAME)
            self._model_loaded = True
            logger.info("✅ Semantic model loaded successfully.")
        except Exception as exc:
            logger.warning("⚠️ Could not load sentence-transformers: %s", exc)
            self._model = None
            self._model_loaded = True  # don't retry on every request

    # ── Redis helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _get_redis():
        try:
            from data.redis_client import redis_client
            return redis_client
        except Exception:
            return None

    def _load_from_redis(self) -> bool:
        """Load corpus embeddings from Redis into RAM. Returns True on success."""
        redis = self._get_redis()
        if not redis:
            return False
        try:
            raw = redis.get(SEMANTIC_CACHE_KEY)
            if not raw:
                return False
            data: Dict[str, List[float]] = json.loads(raw)
            self._corpus = {int(k): np.array(v, dtype=np.float32) for k, v in data.items()}
            self._corpus_built_at = time.time()
            logger.info("📦 Semantic embeddings loaded from Redis (%d objects)", len(self._corpus))
            return True
        except Exception as exc:
            logger.warning("⚠️ Failed to load semantic cache from Redis: %s", exc)
            return False

    def _save_to_redis(self) -> None:
        """Persist the in-memory corpus to Redis."""
        redis = self._get_redis()
        if not redis:
            return
        try:
            serialisable = {str(k): v.tolist() for k, v in self._corpus.items()}
            redis.set(SEMANTIC_CACHE_KEY, json.dumps(serialisable), ex=SEMANTIC_CACHE_TTL)
            logger.info("💾 Semantic embeddings saved to Redis (%d objects)", len(self._corpus))
        except Exception as exc:
            logger.warning("⚠️ Failed to save semantic cache to Redis: %s", exc)

    # ── Public API ────────────────────────────────────────────────────────────

    def build(self, db: Session, force: bool = False) -> None:
        """
        Build (or refresh) the corpus embeddings.
        Results are cached in Redis for 1 h and in RAM for 120 s.
        """
        # 1. RAM freshness check
        if not force and self._corpus and (time.time() - self._corpus_built_at) < _RAM_CACHE_TTL:
            return
        # 2. Redis cache
        if not force and self._load_from_redis():
            return

        self._load_model()
        if self._model is None:
            return  # sentence-transformers not available — skip silently

        objets = (
            db.query(models.Objet)
            .options(
                joinedload(models.Objet.salle),
                joinedload(models.Objet.fonctionnalites),
            )
            .all()
        )
        if not objets:
            return

        documents = [_build_document(obj) for obj in objets]
        ids = [obj.id_objet for obj in objets]

        logger.info("🔢 Encoding %d equipment documents for semantic search…", len(documents))
        try:
            embeddings = self._model.encode(
                documents,
                batch_size=32,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,   # cosine = dot product when both normalised
            )
        except Exception as exc:
            logger.error("⚠️ Semantic encoding failed: %s", exc)
            return

        self._corpus = {obj_id: emb for obj_id, emb in zip(ids, embeddings)}
        self._corpus_built_at = time.time()
        self._save_to_redis()
        logger.info("✅ Semantic corpus built: %d vectors", len(self._corpus))

    def score(self, query: str, obj: models.Objet) -> float:
        """
        Return cosine similarity [0.0 – 1.0] between `query` and `obj`.
        Returns 0.0 if the model is not loaded or embeddings unavailable.
        """
        if not query or self._model is None:
            return 0.0

        obj_embedding = self._corpus.get(obj.id_objet)
        if obj_embedding is None:
            return 0.0

        try:
            query_embedding = self._model.encode(
                query,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
        except Exception:
            return 0.0

        # Both embeddings are L2-normalised → dot product == cosine similarity
        return float(np.dot(query_embedding, obj_embedding))

    def invalidate(self) -> None:
        """Delete cached embeddings from Redis (called on inventory change)."""
        self._corpus = {}
        self._corpus_built_at = 0.0
        redis = self._get_redis()
        if redis:
            try:
                redis.delete(SEMANTIC_CACHE_KEY)
                logger.info("🗑️ Semantic embedding cache invalidated.")
            except Exception as exc:
                logger.warning("⚠️ Could not invalidate semantic cache: %s", exc)


# ── Module-level singleton ─────────────────────────────────────────────────────
semantic_service = SemanticSearchService()
