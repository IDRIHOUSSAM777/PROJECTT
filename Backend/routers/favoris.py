from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from data import models
from data import schemas
import auth
from data.database import get_db

router = APIRouter(tags=["Favoris"])

def _ensure_real_user(current_user: models.Utilisateur):
    # L'admin hardcodé a id_utilisateur=0 et n'existe pas en DB → FK violation si on tente d'insérer.
    if current_user.email == "admin@smartfind.com":
        raise HTTPException(status_code=403, detail="L'administrateur ne gère pas de favoris")


@router.get("/users/me/favorites", response_model=List[schemas.FavoriResponse])
def list_favorites(
    current_user: models.Utilisateur = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_real_user(current_user)
    favoris = (
        db.query(models.Favori)
        .filter(models.Favori.id_utilisateur == current_user.id_utilisateur)
        .order_by(models.Favori.date_ajout.desc())
        .all()
    )
    return [
        schemas.FavoriResponse(
            id_objet=f.objet.id_objet,
            nom_model=f.objet.nom_model,
            nom_marque=f.objet.nom_marque,
            type_objet=f.objet.type_objet,
            statut=f.objet.statut,
            url_photo=f.objet.url_photo,
            date_ajout=f.date_ajout,
        )
        for f in favoris
        if f.objet is not None
    ]


@router.post("/users/me/favorites/{objet_id}", response_model=schemas.FavoriResponse)
def add_favorite(
    objet_id: int,
    current_user: models.Utilisateur = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_real_user(current_user)
    objet = db.query(models.Objet).filter(models.Objet.id_objet == objet_id).first()
    if not objet:
        raise HTTPException(status_code=404, detail="Objet introuvable")

    existing = (
        db.query(models.Favori)
        .filter(
            models.Favori.id_utilisateur == current_user.id_utilisateur,
            models.Favori.id_objet == objet_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Objet déjà dans les favoris")

    fav = models.Favori(id_utilisateur=current_user.id_utilisateur, id_objet=objet_id)
    db.add(fav)
    db.commit()
    db.refresh(fav)

    return schemas.FavoriResponse(
        id_objet=objet.id_objet,
        nom_model=objet.nom_model,
        nom_marque=objet.nom_marque,
        type_objet=objet.type_objet,
        statut=objet.statut,
        url_photo=objet.url_photo,
        date_ajout=fav.date_ajout,
    )


@router.delete("/users/me/favorites/{objet_id}")
def remove_favorite(
    objet_id: int,
    current_user: models.Utilisateur = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_real_user(current_user)
    fav = (
        db.query(models.Favori)
        .filter(
            models.Favori.id_utilisateur == current_user.id_utilisateur,
            models.Favori.id_objet == objet_id,
        )
        .first()
    )
    if not fav:
        raise HTTPException(status_code=404, detail="Favori introuvable")

    db.delete(fav)
    db.commit()
    return {"message": "Favori supprimé"}
