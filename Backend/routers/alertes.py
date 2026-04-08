from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import List

from data import models
from data import schemas
import auth
from data.database import get_db
from routers.notifications import create_notification

router = APIRouter(tags=["Gestion des Alertes (Admin)"])

OPEN_RESERVATION_STATUSES = ["ACTIVE", "Active", "WAITING", "Waiting"]

@router.get("/admin/alertes", response_model=List[schemas.AlerteResponse])
def get_alertes(resolved: bool = False, db: Session = Depends(get_db), current_user: models.Utilisateur = Depends(auth.get_current_admin)):
    alertes = db.query(models.Alerte).filter(models.Alerte.est_resolu == resolved).all()
    
    response = []
    for a in alertes:
        signaleur = "IoT Automatique"
        if a.id_utilisateur and a.utilisateur:
            signaleur = f"{a.utilisateur.nom} {a.utilisateur.prenom}"
        nom_objet = "Objet Inconnu"
        if a.objet:
            nom_salle = a.objet.salle.nom_salle if a.objet.salle else "Salle Inconnue"
            nom_objet = f"{a.objet.type_objet} {a.objet.nom_model} ({nom_salle})"
            
        response.append({
            "id_alerte": a.id_alerte,
            "message": a.message,
            "niveau": a.niveau,
            "source": a.source,
            "date_alerte": a.date_alerte,
            "est_resolu": a.est_resolu,
            "nom_objet": nom_objet,
            "nom_signaleur": signaleur
        })
    return response

@router.put("/admin/alertes/{alerte_id}/resolve")
def resolve_alerte(
    alerte_id: int, 
    nouveau_statut_objet: str = Body(..., embed=True), 
    db: Session = Depends(get_db), 
    current_user: models.Utilisateur = Depends(auth.get_current_admin)
):
    alerte = db.query(models.Alerte).filter(models.Alerte.id_alerte == alerte_id).first()
    if not alerte: raise HTTPException(404, "Alerte introuvable")
    
    alerte.est_resolu = True
    
    if alerte.objet:
        alerte.objet.statut = nouveau_statut_objet
        
        if nouveau_statut_objet == "Disponible":
             pass 
        elif nouveau_statut_objet == "Panne":
             alerte.objet.description = f"EN PANNE (Confirmé par Admin via alerte #{alerte_id})"
             
             reservations_affectees = db.query(models.Reservation).filter(
                 models.Reservation.id_objet == alerte.objet.id_objet,
                 models.Reservation.statut_reservation.in_(OPEN_RESERVATION_STATUSES)
             ).all()
             
             for res in reservations_affectees:
                 create_notification(
                     db=db,
                     user_id=res.id_utilisateur,
                     message=f"L'objet {alerte.objet.nom_model} (Réservation #{res.id}) vient d'être déclaré en PANNE.",
                     type_notification="PANNE_ALERTE",
                     object_id=alerte.objet.id_objet,
                     reservation_id=res.id
                 )

    db.commit()
    return {"message": f"Alerte résolue. L'objet est maintenant '{nouveau_statut_objet}'"}


@router.post("/objets/{objet_id}/report")
def signaler_probleme(
    objet_id: int, 
    description: str, 
    current_user: models.Utilisateur = Depends(auth.get_current_user), 
    db: Session = Depends(get_db)
):
    objet = db.query(models.Objet).filter(models.Objet.id_objet == objet_id).first()
    if not objet: raise HTTPException(404, "Objet introuvable")
    
    if objet.statut != "Panne":
        objet.statut = "Signalé" 
    
    new_alerte = models.Alerte(
        message=description,
        niveau="Warning",
        source="Utilisateur",
        id_objet=objet_id,
        id_utilisateur=current_user.id_utilisateur
    )
    
    db.add(new_alerte)
    db.commit()
    
    return {"message": "Problème signalé. L'objet est en attente de vérification."}
