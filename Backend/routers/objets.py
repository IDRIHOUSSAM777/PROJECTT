import os
import shutil
import uuid
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from sqlalchemy.orm import Session
from typing import List

from data import models
from data import schemas
import auth
from data.database import get_db
from data.redis_client import clear_search_cache

router = APIRouter(tags=["Gestion Objets (Admin)"])

@router.post("/objets", response_model=schemas.ObjetResponse)
def create_objet(
    objet: schemas.ObjetCreate, 
    current_user: models.Utilisateur = Depends(auth.get_current_admin),
    db: Session = Depends(get_db)
):
    db_objet = models.Objet(
        nom_model=objet.nom_model, 
        nom_marque=objet.nom_marque,
        type_objet=objet.type_objet, 
        description=objet.description,
        id_salle=objet.id_salle, 
        mac_adresse=objet.mac_adresse,
        ip_adress=objet.ip_adress,
        pos_x=objet.pos_x,
        pos_y=objet.pos_y,
        statut="Disponible" 
    )
    
    for nom_fonc in objet.fonctionnalites:
        nom_clean = nom_fonc.capitalize()
        fonc = db.query(models.Fonctionnalite).filter_by(nom=nom_clean).first()
        if not fonc: 
            fonc = models.Fonctionnalite(nom=nom_clean)
        db_objet.fonctionnalites.append(fonc)

    db.add(db_objet)
    db.commit()
    db.refresh(db_objet)
    clear_search_cache()
    return db_objet

@router.get("/objets/{objet_id}", response_model=schemas.ObjetResponse)
def get_objet(objet_id: int, db: Session = Depends(get_db), current_user: models.Utilisateur = Depends(auth.get_current_user)):
    objet = db.query(models.Objet).filter(models.Objet.id_objet == objet_id).first()
    if not objet:
        raise HTTPException(404, "Objet introuvable")
    return objet

@router.put("/objets/{objet_id}", response_model=schemas.ObjetResponse)
def update_objet(objet_id: int, update_data: schemas.ObjetUpdate, current_user: models.Utilisateur = Depends(auth.get_current_admin), db: Session = Depends(get_db)):
    objet = db.query(models.Objet).filter(models.Objet.id_objet == objet_id).first()
    if not objet: raise HTTPException(404, "Objet introuvable")
    
    if update_data.statut: objet.statut = update_data.statut
    if update_data.nom_model: objet.nom_model = update_data.nom_model
    if update_data.description: objet.description = update_data.description
    if update_data.nom_marque is not None: objet.nom_marque = update_data.nom_marque
    if update_data.type_objet is not None: objet.type_objet = update_data.type_objet
    if update_data.mac_adresse is not None: objet.mac_adresse = update_data.mac_adresse
    if update_data.ip_adress is not None: objet.ip_adress = update_data.ip_adress
    if update_data.id_salle is not None: objet.id_salle = update_data.id_salle
    
    if update_data.fonctionnalites is not None:
        # Clear existing and update
        objet.fonctionnalites = []
        for nom_fonc in update_data.fonctionnalites:
            nom_clean = nom_fonc.capitalize()
            fonc = db.query(models.Fonctionnalite).filter_by(nom=nom_clean).first()
            if not fonc: 
                fonc = models.Fonctionnalite(nom=nom_clean)
            objet.fonctionnalites.append(fonc)
    db.commit()
    db.refresh(objet)
    clear_search_cache()
    return objet

@router.delete("/objets/{objet_id}")
def delete_objet(objet_id: int, current_user: models.Utilisateur = Depends(auth.get_current_admin), db: Session = Depends(get_db)):
    objet = db.query(models.Objet).filter(models.Objet.id_objet == objet_id).first()
    if not objet: raise HTTPException(404, "Objet introuvable")
    
    try:
        # Fetch reservations for this object
        res_ids = [r.id for r in db.query(models.Reservation).filter(models.Reservation.id_objet == objet_id).all()]
        
        # Cascades to prevent IntegrityError on child rows
        if res_ids:
            db.query(models.Notification).filter(models.Notification.id_reservation.in_(res_ids)).delete(synchronize_session=False)
            
        db.query(models.Notification).filter(models.Notification.id_objet == objet_id).delete(synchronize_session=False)
        db.query(models.Alerte).filter(models.Alerte.id_objet == objet_id).delete(synchronize_session=False)
        db.query(models.Reservation).filter(models.Reservation.id_objet == objet_id).delete(synchronize_session=False)

        # Clear M2M associations manually (Fonctionnalites)
        objet.fonctionnalites = []
        
        db.delete(objet)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error on delete: {e}")
        raise HTTPException(500, "Erreur interne lors de la suppression.")
        
    clear_search_cache()
    return {"message": "Objet supprimé avec succès"}

@router.post("/objets/{objet_id}/upload-photo")
def upload_objet_photo(
    objet_id: int, 
    file: UploadFile = File(...), 
    current_user: models.Utilisateur = Depends(auth.get_current_admin), 
    db: Session = Depends(get_db)
):
    objet = db.query(models.Objet).filter(models.Objet.id_objet == objet_id).first()
    if not objet:
        raise HTTPException(404, "Objet introuvable")

    ext = (file.filename or "").split(".")[-1]
    if not ext or ext.lower() not in ["jpg", "jpeg", "png", "webp"]:
        raise HTTPException(400, "Format de fichier non supporté. Utilisez JPG, PNG ou WEBP.")

    safe_filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join("uploads", safe_filename)

    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    objet.url_photo = f"/uploads/{safe_filename}"
    db.commit()
    clear_search_cache()

    return {"message": "Image uploadée avec succès", "url": objet.url_photo}

@router.get("/types", response_model=List[str])
def get_types(db: Session = Depends(get_db)):
    types = db.query(models.Objet.type_objet).distinct().all()
    return [t[0] for t in types if t[0]]

@router.get("/fonctionnalites", response_model=List[str])
def get_fonctionnalites(db: Session = Depends(get_db)):
    foncs = db.query(models.Fonctionnalite.nom).all()
    return [f[0] for f in foncs if f[0]]
