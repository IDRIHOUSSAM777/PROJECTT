import json
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from typing import List, Optional

from data import models
from data import schemas
import auth
from data.database import get_db
from search.search_engine import engine as search_engine

from data.redis_client import redis_client
import logging

router = APIRouter(tags=["Recherche & Consultation"])

@router.get("/search", response_model=List[schemas.ObjetResponse])
def search_global(
    q: Optional[str] = None,
    etage: Optional[int] = None, salle: Optional[int] = None,
    type: Optional[str] = None, marque: Optional[str] = None,
    statut: Optional[str] = None, fonction: Optional[str] = None,
    distance: bool = False,
    distance_max: Optional[float] = None,
    sort_by: Optional[str] = None,
    save_history: bool = False,
    user_x: float = 0.0,
    user_y: float = 0.0,
    user_etage: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Optional[models.Utilisateur] = Depends(auth.get_current_user_optional)
):
    if current_user and save_history and q and q.strip():
        query_text = q.strip()
        last_entry = db.query(models.Historique)\
            .filter(
                models.Historique.id_utilisateur == current_user.id_utilisateur,
                models.Historique.requete_search == query_text
            )\
            .order_by(models.Historique.date_his.desc())\
            .first()

        should_insert = True
        if last_entry and last_entry.date_his:
            should_insert = (datetime.utcnow() - last_entry.date_his).total_seconds() > 2

        if should_insert:
            hist = models.Historique(requete_search=query_text, id_utilisateur=current_user.id_utilisateur)
            db.add(hist)
            db.commit()

    cache_key = None
    if redis_client and not save_history:
        params_str = f"search:{q}:{etage}:{salle}:{type}:{marque}:{statut}:{fonction}:{distance}:{distance_max}:{sort_by}:{user_x}:{user_y}:{user_etage}"
        cache_key = params_str
        try:
            cached_result = redis_client.get(cache_key)
            if cached_result:
                return json.loads(cached_result)
        except Exception as e:
            logger.error(f"⚠️ Redis GET error in search_global: {e}")
            pass 

    results = search_engine.search(
        db=db,
        query=q,
        filtre_etage_id=etage,
        filtre_salle_id=salle,
        filtre_type=type,
        filtre_marque=marque,
        filtre_statut=statut,
        filtre_fonction=fonction,
        sort_by_distance=distance,
        max_distance=distance_max,
        sort_by=sort_by,
        user_x=user_x,
        user_y=user_y,
        user_etage=user_etage
    )

    if redis_client and cache_key:
        try:
            encoded_results = jsonable_encoder(results)
            redis_client.set(cache_key, json.dumps(encoded_results), ex=300)
        except Exception as e:
            logger.error(f"⚠️ Redis SET error in search_global: {e}")
            pass

    return results

@router.get("/search/suggest")
def search_suggest(
    q: str = Query(..., min_length=1),
    limit: int = Query(8, ge=1, le=20),
    db: Session = Depends(get_db),
):
    return {
        "suggestions": search_engine.suggest(
            db=db,
            query=q,
            limit=limit,
        )
    }

@router.get("/search/filters")
def get_search_filters(active_only: bool = Query(False), db: Session = Depends(get_db)):
    types = [
        row[0]
        for row in db.query(models.Objet.type_objet).filter(models.Objet.type_objet.isnot(None)).distinct().order_by(models.Objet.type_objet.asc()).all()
        if row[0]
    ]

    marques = [
        row[0]
        for row in db.query(models.Objet.nom_marque).filter(models.Objet.nom_marque.isnot(None)).distinct().order_by(models.Objet.nom_marque.asc()).all()
        if row[0]
    ]

    statuts = [
        row[0]
        for row in db.query(models.Objet.statut).filter(models.Objet.statut.isnot(None)).distinct().order_by(models.Objet.statut.asc()).all()
        if row[0]
    ]

    fonctionnalites = [
        row[0]
        for row in db.query(models.Fonctionnalite.nom).filter(models.Fonctionnalite.nom.isnot(None)).distinct().order_by(models.Fonctionnalite.nom.asc()).all()
        if row[0]
    ]

    if active_only:
        etages = [
            row[0]
            for row in db.query(models.Salle.num_etage)\
                .join(models.Objet, models.Salle.id_salle == models.Objet.id_salle)\
                .distinct().order_by(models.Salle.num_etage.asc()).all()
            if row[0] is not None
        ]

        salles = db.query(models.Salle)\
            .join(models.Objet, models.Salle.id_salle == models.Objet.id_salle)\
            .distinct()\
            .order_by(models.Salle.num_etage.asc(), models.Salle.nom_salle.asc())\
            .all()
    else:
        etages = [
            row[0]
            for row in db.query(models.Etage.num_etage).distinct().order_by(models.Etage.num_etage.asc()).all()
            if row[0] is not None
        ]

        salles = db.query(models.Salle).order_by(models.Salle.num_etage.asc(), models.Salle.nom_salle.asc()).all()

    return {
        "types": types,
        "marques": marques,
        "statuts": statuts,
        "fonctionnalites": fonctionnalites,
        "etages": etages,
        "salles": [
            {
                "id_salle": s.id_salle,
                "nom_salle": s.nom_salle,
                "num_etage": s.num_etage,
                "coord_x": s.coord_x,
                "coord_y": s.coord_y,
                "largeur": getattr(s, 'largeur', 20),
                "longueur": getattr(s, 'longueur', 20),
            }
            for s in salles
        ],
    }
