import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List

from data import models
from data import schemas
from data.database import get_db
from routers.notifications import create_notification
from data.redis_client import clear_search_cache

router = APIRouter(tags=["IoT Heartbeat"])

OPEN_RESERVATION_STATUSES = ["ACTIVE", "Active", "WAITING", "Waiting"]

@router.post("/iot/heartbeat")
def receive_heartbeat(
    heartbeat: schemas.HeartbeatSchema, 
    request: Request, 
    db: Session = Depends(get_db)
):
    objet = db.query(models.Objet).filter(models.Objet.mac_adresse == heartbeat.mac_adresse).first()
    if not objet: 
        raise HTTPException(404, "Objet inconnu (MAC non reconnue)")
    
    objet.ip_adress = request.client.host
    objet.last_heartbeat = datetime.utcnow()

    status_critique = ["Critical", "Panne", "Erreur", "Surchauffe", "Error"]
    status_warning = ["Warning", "Low Battery", "Papier Bas", "Maintenance"]
    status_ok = ["OK", "Available", "Ready", "Disponible"]

    if heartbeat.statut in status_critique:
        objet.statut = "Panne"
        
        alerte_existante = db.query(models.Alerte).filter(
            models.Alerte.id_objet == objet.id_objet,
            models.Alerte.est_resolu == False,
            models.Alerte.source == "IoT"
        ).first()
        
        if not alerte_existante:
            new_alerte = models.Alerte(
                message=f"ALERTE CRITIQUE AUTO : {heartbeat.statut}",
                niveau="Critical",
                source="IoT",
                id_objet=objet.id_objet
            )
            db.add(new_alerte)
            
        reservations_affectees = db.query(models.Reservation).filter(
            models.Reservation.id_objet == objet.id_objet,
            models.Reservation.statut_reservation.in_(OPEN_RESERVATION_STATUSES)
        ).all()
        
        for res in reservations_affectees:
            create_notification(
                db=db,
                user_id=res.id_utilisateur,
                message=f"L'objet {objet.nom_model} (Réservation #{res.id}) vient d'être signalé en PANNE par le système.",
                type_notification="PANNE_IOT",
                object_id=objet.id_objet,
                reservation_id=res.id
            )

    elif heartbeat.statut in status_warning:
        if objet.statut != "Panne":
            objet.statut = "Signalé"
            
        alerte_existante = db.query(models.Alerte).filter(
            models.Alerte.id_objet == objet.id_objet,
            models.Alerte.message.contains("Warning"), 
            models.Alerte.est_resolu == False
        ).first()

        if not alerte_existante:
            new_alerte = models.Alerte(
                message=f"Maintenance requise : {heartbeat.statut}",
                niveau="Warning",
                source="IoT",
                id_objet=objet.id_objet
            )
            db.add(new_alerte)

    elif heartbeat.statut in status_ok:
        if objet.statut in ["Panne", "Signalé"]:
            objet.statut = "Disponible"

    db.commit()
    clear_search_cache()
    return {"status": "ok", "message": f"Heartbeat traité. Statut actuel : {objet.statut}"}

@router.get("/objets/{objet_id}/td", tags=["Web of Things (W3C)"])
def get_thing_description(objet_id: int, db: Session = Depends(get_db)):
    """
    Génère un Thing Description (TD) au format JSON-LD selon le standard W3C Web of Things.
    Permet l'interopérabilité sémantique de l'objet.
    """
    objet = db.query(models.Objet).filter(models.Objet.id_objet == objet_id).first()
    if not objet:
        raise HTTPException(status_code=404, detail="Objet introuvable")

    td = {
        "@context": "https://www.w3.org/2019/wot/td/v1",
        "id": f"urn:dev:mac:{objet.mac_adresse}" if objet.mac_adresse else f"urn:dev:id:{objet.id_objet}",
        "title": f"{objet.nom_marque} {objet.nom_model}".strip(),
        "description": objet.description or f"Objet connecté de type {objet.type_objet} sur SmartFind",
        "securityDefinitions": {
            "bearer_sc": {"scheme": "bearer", "format": "jwt"}
        },
        "security": ["bearer_sc"],
        "properties": {
            "statut": {
                "type": "string",
                "readOnly": True,
                "description": "Statut actuel de l'objet (Disponible, Occupé, Panne)",
            }
        },
        "actions": {},
        "events": {
            "alerte": {
                "description": "Événement de niveau Warning ou Critical déclenché par l'IoT ou un signalement utilisateur",
                "data": {"type": "string"}
            }
        }
    }

    for fonc in objet.fonctionnalites:
        action_name = fonc.nom.lower()
        td["actions"][action_name] = {
            "description": f"Exécuter l'action interne : {action_name}",
            "forms": [{
                "href": f"/objets/{objet.id_objet}/action?action={action_name}",
                "op": ["invokeaction"],
                "contentType": "application/json"
            }]
        }

    return td
