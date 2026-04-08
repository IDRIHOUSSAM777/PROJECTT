import math
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from typing import Dict, List, Optional
from data import models
from search.nlp_service import normalize_text

WAITING_STATUSES = {"WAITING", "EN ATTENTE"}
CANCELLED_STATUSES = {"CANCELLED", "ANNULEE", "ANNULÉE", "DONE", "TERMINE", "TERMINÉ"}

class RankingEngine:
    @staticmethod
    def distance_from_user(obj, user_x: float = 0.0, user_y: float = 0.0, user_etage: Optional[int] = None) -> float:
        """
        Calcule la distance euclidienne entre un objet et la position de l'utilisateur en intégrant l'étage.
        Si l'objet n'est pas au même étage que l'utilisateur, on ajoute une pénalité de "marche" (ex: escaliers).
        """
        salle = getattr(obj, "salle", None)
        if not salle: return float("inf")
        x, y = getattr(salle, "coord_x", None), getattr(salle, "coord_y", None)
        if x is None or y is None: return float("inf")
        
        dx = float(x) - user_x
        dy = float(y) - user_y
        dist_2d = math.sqrt(dx**2 + dy**2)
        
        if user_etage is not None and salle.num_etage is not None:
            etage_diff = abs(salle.num_etage - user_etage)
            if etage_diff > 0:
                # Pénalité de marche réaliste pour l'affichage (escaliers = 25m)
                # Le vrai TRI strict par étage se fait dans search_engine.py
                vertical_penalty = etage_diff * 25.0
                return math.sqrt(dist_2d**2 + vertical_penalty**2)
                
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
        if not math.isfinite(distance_value): return 0.0
        return max(0.0, 100.0 - (min(distance_value, 5000.0) / 50.0))

    @staticmethod
    def load_waiting_counts(db: Session, object_ids: List[int]) -> Dict[int, int]:
        if not object_ids: return {}
        status_upper = func.upper(func.coalesce(models.Reservation.statut_reservation, ""))
        rows = db.query(models.Reservation.id_objet, func.count(models.Reservation.id))\
            .filter(models.Reservation.id_objet.in_(object_ids), status_upper.in_(list(WAITING_STATUSES)))\
            .group_by(models.Reservation.id_objet).all()
        return {int(oid): int(count or 0) for oid, count in rows}

    @staticmethod
    def load_popularity_counts(db: Session, object_ids: List[int]) -> Dict[int, int]:
        if not object_ids: return {}
        status_upper = func.upper(func.coalesce(models.Reservation.statut_reservation, ""))
        rows = db.query(models.Reservation.id_objet, func.count(models.Reservation.id))\
            .filter(models.Reservation.id_objet.in_(object_ids), ~status_upper.in_(list(CANCELLED_STATUSES)))\
            .group_by(models.Reservation.id_objet).all()
        return {int(oid): int(count or 0) for oid, count in rows}

    @staticmethod
    def sql_popularity_score():
        from sqlalchemy import select, func, cast, Float
        status_upper = func.upper(func.coalesce(models.Reservation.statut_reservation, ""))
        
        subq = select(
            models.Reservation.id_objet,
            func.count(models.Reservation.id).label("pop_count")
        ).where(~status_upper.in_(list(CANCELLED_STATUSES)))\
         .group_by(models.Reservation.id_objet).subquery()
        
        return func.coalesce(
            select(subq.c.pop_count).where(subq.c.id_objet == models.Objet.id_objet).scalar_subquery(),
            0
        )

    @staticmethod
    def sql_waiting_score():
        from sqlalchemy import select, func
        status_upper = func.upper(func.coalesce(models.Reservation.statut_reservation, ""))
        
        subq = select(
            models.Reservation.id_objet,
            func.count(models.Reservation.id).label("wait_count")
        ).where(status_upper.in_(list(WAITING_STATUSES)))\
         .group_by(models.Reservation.id_objet).subquery()
         
        return func.coalesce(
            select(subq.c.wait_count).where(subq.c.id_objet == models.Objet.id_objet).scalar_subquery(),
            0
        )

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
