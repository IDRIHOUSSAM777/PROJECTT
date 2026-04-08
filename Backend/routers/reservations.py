from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional

from data import models
from data import schemas
import auth
from data.database import get_db
from routers.notifications import create_notification
from data.redis_client import clear_search_cache

router = APIRouter(tags=["Réservations & Actions"])

WAITING_RESERVATION_STATUSES = ["WAITING", "Waiting"]
ACTIVE_RESERVATION_STATUSES = ["ACTIVE", "Active"]
OPEN_RESERVATION_STATUSES = ACTIVE_RESERVATION_STATUSES + WAITING_RESERVATION_STATUSES


def _count_waiting(db: Session, object_id: int) -> int:
    return int(
        db.query(func.count(models.Reservation.id))
        .filter(
            models.Reservation.id_objet == object_id,
            models.Reservation.statut_reservation.in_(WAITING_RESERVATION_STATUSES),
        )
        .scalar()
        or 0
    )


def _get_active_reservation(db: Session, object_id: int):
    return (
        db.query(models.Reservation)
        .filter(
            models.Reservation.id_objet == object_id,
            models.Reservation.statut_reservation.in_(ACTIVE_RESERVATION_STATUSES),
        )
        .order_by(models.Reservation.date_reservation.asc())
        .first()
    )


def _get_oldest_waiting_reservation(db: Session, object_id: int):
    return (
        db.query(models.Reservation)
        .filter(
            models.Reservation.id_objet == object_id,
            models.Reservation.statut_reservation.in_(WAITING_RESERVATION_STATUSES),
        )
        .order_by(models.Reservation.date_reservation.asc())
        .first()
    )


def _get_my_open_reservation(db: Session, object_id: int, user_id: int):
    return (
        db.query(models.Reservation)
        .filter(
            models.Reservation.id_objet == object_id,
            models.Reservation.id_utilisateur == user_id,
            models.Reservation.statut_reservation.in_(OPEN_RESERVATION_STATUSES),
        )
        .order_by(models.Reservation.date_reservation.desc())
        .first()
    )


def _compute_distance_m(objet: models.Objet):
    if not objet.salle:
        return None

    x = objet.salle.coord_x
    y = objet.salle.coord_y
    if x is None or y is None:
        return None

    return round(((x ** 2) + (y ** 2)) ** 0.5, 2)


def _serialize_equipment_details(objet: models.Objet, current_user: models.Utilisateur, db: Session):
    salle = objet.salle
    etage = salle.etage if salle else None

    active_reservation = _get_active_reservation(db, objet.id_objet)
    my_reservation = _get_my_open_reservation(db, objet.id_objet, current_user.id_utilisateur)

    return {
        "id": objet.id_objet,
        "name": objet.nom_model,
        "type": objet.type_objet,
        "marque": objet.nom_marque,
        "status": objet.statut,
        "mac_adresse": objet.mac_adresse,
        "ip_adress": objet.ip_adress,
        "localisation": {
            "building": etage.nom_building if etage else None,
            "floor": salle.num_etage if salle else None,
            "room": salle.nom_salle if salle else None,
        },
        "distance_m": _compute_distance_m(objet),
        "description": objet.description,
        "url_photo": objet.url_photo,
        "fonctionnalites": [f.nom for f in (objet.fonctionnalites or []) if f and f.nom],
        "queue_count": _count_waiting(db, objet.id_objet),
        "active_reservation_id": active_reservation.id if active_reservation else None,
        "my_reservation_id": my_reservation.id if my_reservation else None,
        "my_reservation_status": my_reservation.statut_reservation if my_reservation else None,
    }


def _cancel_reservation_and_update_queue(
    reservation: models.Reservation,
    db: Session,
    close_status: str = "CANCELLED",
    action_word: str = "annulée",
):
    objet_id = reservation.id_objet
    objet = db.query(models.Objet).filter(models.Objet.id_objet == objet_id).first()
    if not objet:
        raise HTTPException(status_code=404, detail="Objet introuvable")

    status_upper = (reservation.statut_reservation or "").upper()

    if status_upper == "ACTIVE":
        reservation.statut_reservation = close_status
        next_waiting = _get_oldest_waiting_reservation(db, objet.id_objet)

        if next_waiting:
            next_waiting.statut_reservation = "ACTIVE"
            objet.statut = "Occupé"
            create_notification(
                db=db,
                user_id=next_waiting.id_utilisateur,
                message=f"Votre tour est arrivé pour {objet.nom_model}.",
                type_notification="TURN_READY",
                object_id=objet.id_objet,
                reservation_id=next_waiting.id,
            )
            message = f"Réservation {action_word}. Le prochain utilisateur est passé actif."
        else:
            objet.statut = "Disponible"
            message = f"Réservation {action_word}. L'objet est à nouveau disponible."

    elif status_upper == "WAITING":
        reservation.statut_reservation = "CANCELLED"
        message = "Retiré de la file d'attente."
        
        # Check if we should revert object to Disponible if no reservations are left
        # (Though usually if there was a WAITING, there was an ACTIVE)
        active_exists = _get_active_reservation(db, objet_id)
        if not active_exists:
            # If for some reason we cancelled the only waiting and no active existed
            waiting_count = _count_waiting(db, objet_id)
            if waiting_count == 0:
                objet.statut = "Disponible"
    else:
        message = "Réservation déjà clôturée."

    db.commit()
    clear_search_cache()

    return {
        "message": message,
        "reservation_id": reservation.id,
        "reservation_status": reservation.statut_reservation,
        "queue_count": _count_waiting(db, objet.id_objet),
        "object_status": objet.statut,
    }


@router.post("/objets/{objet_id}/reserve")
def reserve_objet(objet_id: int, current_user: models.Utilisateur = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    payload = schemas.ReservationCreateRequest(
        object_id=objet_id,
        user_id=current_user.id_utilisateur,
    )
    return create_reservation(payload=payload, db=db, current_user=current_user)

@router.post("/objets/{objet_id}/action")
def actionner_objet(objet_id: int, action: str = Query(..., description="imprimer, scanner..."), current_user: models.Utilisateur = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    objet = db.query(models.Objet).filter(models.Objet.id_objet == objet_id).first()
    if not objet: raise HTTPException(404, "Objet introuvable")
    
    reservation = (
        db.query(models.Reservation)
        .filter(
            models.Reservation.id_objet == objet_id,
            models.Reservation.id_utilisateur == current_user.id_utilisateur,
            models.Reservation.statut_reservation.in_(ACTIVE_RESERVATION_STATUSES)
        )
        .first()
    )
    
    if objet.statut == "Occupé" and not reservation:
        raise HTTPException(403, "Cet objet est utilisé par quelqu'un d'autre")
    
    if objet.statut == "Panne":
        raise HTTPException(400, "Objet en panne, impossible d'actionner")

    return {"message": f"Action '{action}' envoyée à {objet.nom_model} (IP: {objet.ip_adress})"}


@router.get("/objects/{object_id}", response_model=schemas.EquipmentDetailsResponse)
def get_object_details(
    object_id: int,
    db: Session = Depends(get_db),
    current_user: models.Utilisateur = Depends(auth.get_current_user),
):
    objet = db.query(models.Objet).filter(models.Objet.id_objet == object_id).first()
    if not objet:
        raise HTTPException(status_code=404, detail="Objet introuvable")

    return _serialize_equipment_details(objet, current_user, db)


@router.get("/objects/{object_id}/queue", response_model=schemas.QueueInfoResponse)
def get_object_queue(
    object_id: int,
    db: Session = Depends(get_db),
    current_user: models.Utilisateur = Depends(auth.get_current_user),
):
    objet = db.query(models.Objet).filter(models.Objet.id_objet == object_id).first()
    if not objet:
        raise HTTPException(status_code=404, detail="Objet introuvable")

    active_reservation = _get_active_reservation(db, object_id)

    return {
        "object_id": object_id,
        "waiting_count": _count_waiting(db, object_id),
        "active_reservation_id": active_reservation.id if active_reservation else None,
    }


@router.post("/reservations", response_model=schemas.ReservationActionResponse)
def create_reservation(
    payload: schemas.ReservationCreateRequest,
    db: Session = Depends(get_db),
    current_user: models.Utilisateur = Depends(auth.get_current_user),
):
    user_id = payload.user_id or current_user.id_utilisateur

    if payload.user_id and payload.user_id != current_user.id_utilisateur and current_user.role != "Admin":
        raise HTTPException(status_code=403, detail="Non autorisé")

    objet = db.query(models.Objet).filter(models.Objet.id_objet == payload.object_id).first()
    if not objet:
        raise HTTPException(status_code=404, detail="Objet introuvable")

    if objet.statut == "Panne":
        raise HTTPException(status_code=400, detail="Objet en panne, réservation impossible")

    existing = _get_my_open_reservation(db, payload.object_id, user_id)
    if existing:
        return {
            "message": "Vous avez déjà une réservation en cours pour cet objet.",
            "reservation_id": existing.id,
            "reservation_status": existing.statut_reservation,
            "queue_count": _count_waiting(db, payload.object_id),
            "object_status": objet.statut,
        }

    active_reservation = _get_active_reservation(db, payload.object_id)

    if active_reservation is None:
        reservation_status = "ACTIVE"
        objet.statut = "Occupé"
        message = "Réservation confirmée"
    else:
        reservation_status = "WAITING"
        objet.statut = "Occupé"
        message = "Ajouté à la file d'attente"

    reservation = models.Reservation(
        id_utilisateur=user_id,
        id_objet=payload.object_id,
        statut_reservation=reservation_status,
    )

    db.add(reservation)
    db.commit()
    db.refresh(reservation)
    clear_search_cache()

    return {
        "message": message,
        "reservation_id": reservation.id,
        "reservation_status": reservation.statut_reservation,
        "queue_count": _count_waiting(db, payload.object_id),
        "object_status": objet.statut,
    }

@router.delete("/reservations/{reservation_id}", response_model=schemas.ReservationActionResponse)
def cancel_reservation_by_id(
    reservation_id: int,
    db: Session = Depends(get_db),
    current_user: models.Utilisateur = Depends(auth.get_current_user),
):
    reservation = db.query(models.Reservation).filter(models.Reservation.id == reservation_id).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Réservation introuvable")

    if reservation.id_utilisateur != current_user.id_utilisateur and current_user.role != "Admin":
        raise HTTPException(status_code=403, detail="Non autorisé")

    return _cancel_reservation_and_update_queue(reservation, db)

@router.post("/reservations/{reservation_id}/complete", response_model=schemas.ReservationActionResponse)
def complete_reservation_by_id(
    reservation_id: int,
    db: Session = Depends(get_db),
    current_user: models.Utilisateur = Depends(auth.get_current_user),
):
    reservation = db.query(models.Reservation).filter(models.Reservation.id == reservation_id).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Réservation introuvable")

    if reservation.id_utilisateur != current_user.id_utilisateur and current_user.role != "Admin":
        raise HTTPException(status_code=403, detail="Non autorisé")

    status_upper = (reservation.statut_reservation or "").upper()
    if status_upper != "ACTIVE":
        raise HTTPException(status_code=400, detail="Seule une réservation active peut être terminée")

    return _cancel_reservation_and_update_queue(
        reservation=reservation,
        db=db,
        close_status="DONE",
        action_word="terminée",
    )
