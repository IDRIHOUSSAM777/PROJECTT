import json
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List

from data import models
from data import schemas
from data.database import get_db

import redis
try:
    redis_client = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
    redis_client.ping()
except Exception as e:
    redis_client = None

router = APIRouter(tags=["Données Publiques (Catégories & Salles)"])

@router.get("/categories", response_model=List[schemas.CategoryResponse])
def get_categories(db: Session = Depends(get_db)):
    cache_key = "categories_list"
    if redis_client:
        try:
            cached_result = redis_client.get(cache_key)
            if cached_result:
                return json.loads(cached_result)
        except Exception:
            pass

    results = db.query(
        models.Objet.type_objet,
        func.count(models.Objet.id_objet)
    ).filter(models.Objet.type_objet.isnot(None))\
     .group_by(models.Objet.type_objet)\
     .order_by(models.Objet.type_objet.asc())\
     .all()

    response_data = [
        {"nom": type_name, "count": int(count or 0)}
        for type_name, count in results
        if type_name
    ]

    if redis_client:
        try:
            redis_client.set(cache_key, json.dumps(response_data), ex=3600)
        except Exception:
            pass

    return response_data

@router.get("/salles")
def get_all_salles(db: Session = Depends(get_db)):
    return db.query(models.Salle).all()
