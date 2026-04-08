from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List

from data import models
from data import schemas
import auth
from data.database import get_db

router = APIRouter(tags=["Notifications"])

def create_notification(
    db: Session,
    user_id: int,
    message: str,
    type_notification: str = "INFO",
    object_id: Optional[int] = None,
    reservation_id: Optional[int] = None,
):
    notif = models.Notification(
        id_utilisateur=user_id,
        message=message,
        type_notification=type_notification,
        id_objet=object_id,
        id_reservation=reservation_id,
    )
    db.add(notif)
    return notif

def count_unread_notifications(db: Session, user_id: int) -> int:
    return int(
        db.query(func.count(models.Notification.id_notification))
        .filter(
            models.Notification.id_utilisateur == user_id,
            models.Notification.est_lu == False, 
        )
        .scalar()
        or 0
    )


@router.get("/users/me/notifications", response_model=schemas.NotificationListResponse)
def get_my_notifications(
    limit: int = Query(10, ge=1, le=100),
    unread_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: models.Utilisateur = Depends(auth.get_current_user),
):
    query = db.query(models.Notification).filter(
        models.Notification.id_utilisateur == current_user.id_utilisateur
    )

    if unread_only:
        query = query.filter(models.Notification.est_lu == False)

    items = query.order_by(models.Notification.date_notification.desc()).limit(limit).all()
    unread_count = count_unread_notifications(db, current_user.id_utilisateur)

    return {
        "items": items,
        "unread_count": unread_count,
    }


@router.post("/users/me/notifications/{notification_id}/read", response_model=schemas.NotificationUpdateResponse)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: models.Utilisateur = Depends(auth.get_current_user),
):
    notif = (
        db.query(models.Notification)
        .filter(
            models.Notification.id_notification == notification_id,
            models.Notification.id_utilisateur == current_user.id_utilisateur,
        )
        .first()
    )

    if not notif:
        raise HTTPException(status_code=404, detail="Notification introuvable")

    if not notif.est_lu:
        notif.est_lu = True
        db.commit()

    return {
        "message": "Notification marquée comme lue.",
        "unread_count": count_unread_notifications(db, current_user.id_utilisateur),
    }


@router.post("/users/me/notifications/read-all", response_model=schemas.NotificationUpdateResponse)
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    current_user: models.Utilisateur = Depends(auth.get_current_user),
):
    (
        db.query(models.Notification)
        .filter(
            models.Notification.id_utilisateur == current_user.id_utilisateur,
            models.Notification.est_lu == False,
        )
        .update({models.Notification.est_lu: True}, synchronize_session=False)
    )
    db.commit()
    return {
        "message": "Toutes les notifications marquées comme lues.",
        "unread_count": 0,
    }
