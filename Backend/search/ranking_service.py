import math
import os
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from typing import Dict, List, Optional
from data import models
from search.nlp_service import normalize_text

# Match tier bonuses — used by SmartSearchEngine to prioritize exact > synonym > fuzzy.
# Tuned so that an exact hit always beats a synonym hit regardless of availability bonus (100),
# and a synonym hit always beats a fuzzy/trigram hit.
MATCH_TIER_BONUS = {
    "exact": 500.0,
    "synonym": 250.0,
    "fuzzy": 100.0,
    "trigram": 40.0,
}

class RankingEngine:
    @staticmethod
    def distance_from_user(
        obj,
        user_x: Optional[float] = None,
        user_y: Optional[float] = None,
        user_etage: Optional[int] = None,
    ) -> float:
        """
        Distance entre l'objet et l'utilisateur (même unité que coord_x/coord_y).
        Retourne inf dès qu'une donnée manque : signale "distance inconnue"
        au lieu de forcer un faux (0,0) qui polluerait le ranking.
        Le tri strict par étage est fait en aval dans search_engine._score_and_sort.
        """
        salle = getattr(obj, "salle", None)
        if not salle:
            return float("inf")
        if user_x is None or user_y is None:
            return float("inf")
        x, y = getattr(salle, "coord_x", None), getattr(salle, "coord_y", None)
        if x is None or y is None:
            return float("inf")

        dx = float(x) - float(user_x)
        dy = float(y) - float(user_y)
        dist_2d = math.sqrt(dx**2 + dy**2)

        if user_etage is not None and salle.num_etage is not None:
            etage_diff = abs(salle.num_etage - user_etage)
            if etage_diff > 0:
                # Pénalité "escaliers" dans la même unité que coord_x/y.
                # Surchargeable via FLOOR_PENALTY_UNITS (par défaut : 25).
                floor_penalty = float(os.getenv("FLOOR_PENALTY_UNITS", "25")) * etage_diff
                return math.sqrt(dist_2d**2 + floor_penalty**2)

        return dist_2d

    @staticmethod
    def availability_score(status: Optional[str]) -> float:
        norm = normalize_text(status)
        if "dispon" in norm or norm == "available": return 100.0
        if "occup" in norm or "reserve" in norm or "busy" in norm: return 45.0
        if "panne" in norm or "signal" in norm or "error" in norm: return 10.0
        return 30.0

    @staticmethod
    def sql_availability_score():
        from sqlalchemy import case
        return case(
            (models.Objet.statut.ilike("%dispon%"), 100.0),
            (models.Objet.statut.ilike("%avail%"), 100.0),
            (models.Objet.statut.ilike("%occup%"), 45.0),
            (models.Objet.statut.ilike("%reserv%"), 45.0),
            (models.Objet.statut.ilike("%busy%"), 45.0),
            (models.Objet.statut.ilike("%panne%"), 10.0),
            (models.Objet.statut.ilike("%signal%"), 10.0),
            (models.Objet.statut.ilike("%error%"), 10.0),
            else_=30.0
        )

    @staticmethod
    def distance_score(distance_value: float) -> float:
        """
        Bonus de proximité recalé sur les deltas réalistes en intérieur.
        Horizon par défaut : 200 unités (surchargeable via DISTANCE_SCORE_MAX).
        Mapping : d=0 → 100, d=DISTANCE_SCORE_MAX → 0, linéaire.
        """
        if not math.isfinite(distance_value):
            return 0.0
        horizon = float(os.getenv("DISTANCE_SCORE_MAX", "200"))
        if horizon <= 0:
            return 0.0
        clamped = min(max(distance_value, 0.0), horizon)
        return max(0.0, 100.0 * (1.0 - clamped / horizon))

    @staticmethod
    def load_waiting_counts(db: Session, object_ids: List[int]) -> Dict[int, int]:
        return {}

    @staticmethod
    def load_popularity_counts(db: Session, object_ids: List[int]) -> Dict[int, int]:
        return {}

    @staticmethod
    def sql_popularity_score():
        from sqlalchemy import literal
        return literal(0.0)

    @staticmethod
    def sql_waiting_score():
        from sqlalchemy import literal
        return literal(0.0)

    @staticmethod
    def load_postgres_text_ranks(db: Session, object_ids: List[int], query_clean: str) -> Dict[int, float]:
        if not object_ids or not query_clean: return {}
        engine = db.get_bind()
        if not engine or engine.dialect.name != "postgresql": return {}
        
        document = func.concat_ws(" ",
            func.coalesce(models.Objet.nom_model, ""),
            func.coalesce(models.Objet.type_objet, ""),
            func.coalesce(models.Objet.nom_marque, ""),
            func.coalesce(models.Objet.description, "")
        )
        ts_rank = func.ts_rank_cd(func.to_tsvector("simple", document), func.plainto_tsquery("simple", query_clean)).label("text_rank")
        try:
            rows = db.query(models.Objet.id_objet, ts_rank).filter(models.Objet.id_objet.in_(object_ids)).all()
            return {int(oid): float(rank or 0.0) for oid, rank in rows}
        except SQLAlchemyError:
            return {}

    @staticmethod
    def build_haystack(obj: models.Objet) -> str:
        fonctionnalites = " ".join([f.nom for f in (obj.fonctionnalites or []) if f and f.nom])
        salle_nom = obj.salle.nom_salle if obj.salle and obj.salle.nom_salle else ""
        return f"{obj.type_objet or ''} {obj.nom_marque or ''} {obj.nom_model or ''} {obj.description or ''} {salle_nom} {fonctionnalites}".lower().strip()

    @staticmethod
    def sql_text_rank(query_clean: str):
        if not query_clean:
            from sqlalchemy import literal
            return literal(0.0)

        document = func.concat_ws(" ",
            func.coalesce(models.Objet.nom_model, ""),
            func.coalesce(models.Objet.type_objet, ""),
            func.coalesce(models.Objet.nom_marque, ""),
            func.coalesce(models.Objet.description, "")
        )
        return func.ts_rank_cd(func.to_tsvector("simple", document), func.plainto_tsquery("simple", query_clean))

    @staticmethod
    def sql_trgm_similarity(query_clean: str):
        """
        Similarité trigramme Postgres (extension pg_trgm, index GIN déjà en place).
        Retourne un score 0..1 utilisable en ORDER BY / filtrage pour le fallback fuzzy.
        """
        if not query_clean:
            from sqlalchemy import literal
            return literal(0.0)
        document = func.concat_ws(" ",
            func.coalesce(models.Objet.nom_model, ""),
            func.coalesce(models.Objet.type_objet, ""),
            func.coalesce(models.Objet.nom_marque, ""),
        )
        return func.similarity(document, query_clean)
