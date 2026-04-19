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
    etage: Optional[str] = None, salle: Optional[str] = None,
    type: Optional[str] = None, marque: Optional[str] = None,
    statut: Optional[str] = None, fonction: Optional[str] = None,
    distance: bool = False,
    distance_max: Optional[float] = None,
    sort_by: Optional[str] = None,
    save_history: bool = False,
    user_x: Optional[float] = None,
    user_y: Optional[float] = None,
    user_etage: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Optional[models.Utilisateur] = Depends(auth.get_current_user_optional)
):
    try: etage_id = int(etage) if etage and etage.lower() != 'null' else None
    except: etage_id = None
    
    try: salle_id = int(salle) if salle and salle.lower() != 'null' else None
    except: salle_id = None
    
    try: user_etage_id = int(user_etage) if user_etage and user_etage.lower() != 'null' else None
    except: user_etage_id = None
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
        # user_etage entre toujours dans la clé : il déclenche le floor_bonus
        # et sert de clé de tri secondaire. user_x/y en revanche ne sont
        # consultés que si la distance est explicitement demandée — sinon on
        # les exclut pour éviter que chaque position utilisateur invalide
        # l'entrée de cache.
        distance_active = distance or (distance_max is not None) or (sort_by == "distance")
        pos_part = f":{user_x}:{user_y}" if distance_active else ""
        params_str = f"search:{q}:{etage}:{salle}:{type}:{marque}:{statut}:{fonction}:{distance}:{distance_max}:{sort_by}{pos_part}:{user_etage}"
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
        filtre_etage_id=etage_id,
        filtre_salle_id=salle_id,
        filtre_type=type,
        filtre_marque=marque,
        filtre_statut=statut,
        filtre_fonction=fonction,
        sort_by_distance=distance,
        max_distance=distance_max,
        sort_by=sort_by,
        user_x=user_x,
        user_y=user_y,
        user_etage=user_etage_id
    )

    if redis_client and cache_key:
        try:
            encoded_results = jsonable_encoder(results)
            redis_client.set(cache_key, json.dumps(encoded_results), ex=300)
        except Exception as e:
            logger.error(f"⚠️ Redis SET error in search_global: {e}")
            pass

    return results

@router.get("/search/debug")
def search_debug(
    q: Optional[str] = None,
    etage: Optional[str] = None, salle: Optional[str] = None,
    type: Optional[str] = None, marque: Optional[str] = None,
    statut: Optional[str] = None, fonction: Optional[str] = None,
    distance: bool = False,
    distance_max: Optional[float] = None,
    sort_by: Optional[str] = None,
    user_x: Optional[float] = None,
    user_y: Optional[float] = None,
    user_etage: Optional[str] = None,
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """
    Même logique que /search mais retourne la ventilation du score pour chaque
    résultat (BM25, phrase, palier, étage, distance, total) — utile pour la
    démo du jury et le tuning des pondérations.
    """
    try: etage_id = int(etage) if etage and etage.lower() != 'null' else None
    except: etage_id = None
    try: salle_id = int(salle) if salle and salle.lower() != 'null' else None
    except: salle_id = None
    try: user_etage_id = int(user_etage) if user_etage and user_etage.lower() != 'null' else None
    except: user_etage_id = None

    results = search_engine.search(
        db=db, query=q,
        filtre_etage_id=etage_id, filtre_salle_id=salle_id,
        filtre_type=type, filtre_marque=marque,
        filtre_statut=statut, filtre_fonction=fonction,
        sort_by_distance=distance, max_distance=distance_max, sort_by=sort_by,
        user_x=user_x, user_y=user_y, user_etage=user_etage_id,
        debug=True,
    )

    return {
        "query": q,
        "count": len(results),
        "results": [
            {
                "id_objet": o.id_objet,
                "nom_model": o.nom_model,
                "type_objet": o.type_objet,
                "nom_marque": o.nom_marque,
                "statut": o.statut,
                "etage": o.salle.num_etage if o.salle else None,
                "salle": o.salle.nom_salle if o.salle else None,
                "score_breakdown": getattr(o, "_score_breakdown", None),
            }
            for o in results[:limit]
        ],
    }


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
