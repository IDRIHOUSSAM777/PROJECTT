from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date
from datetime import datetime, timedelta
from data.database import get_db
from data.models import Objet, Utilisateur, Alerte, Reservation, Salle

router = APIRouter(prefix="/admin", tags=["Admin Dashboard"])

@router.get("/dashboard-stats")
def get_dashboard_stats(db: Session = Depends(get_db)):
    # KPI 1 & 2 : Utilisateurs et Équipements totaux
    total_users = db.query(Utilisateur).count()
    total_equipments = db.query(Objet).count()
    
    # KPI 3 & 4 : Statuts des objets
    status_counts = db.query(Objet.statut, func.count(Objet.id_objet)).group_by(Objet.statut).all()
    stats_dict = {s[0]: s[1] for s in status_counts}
    
    available_count = sum(v for k, v in stats_dict.items() if "disponible" in str(k).lower())
    occupied_count = sum(v for k, v in stats_dict.items() if "occup" in str(k).lower() or "reserv" in str(k).lower())
    broken_count = sum(v for k, v in stats_dict.items() if "panne" in str(k).lower() or "error" in str(k).lower())
    
    # Graphes : Objets par salle (Toutes les salles, même vides)
    room_counts = (
        db.query(Salle.nom_salle, Salle.num_etage, func.count(Objet.id_objet))
        .select_from(Salle)
        .outerjoin(Objet, Salle.id_salle == Objet.id_salle)
        .group_by(Salle.id_salle, Salle.nom_salle, Salle.num_etage)
        .order_by(Salle.id_salle)
        .all()
    )
    room_stats = [{"salle": r[0] if r[0] else "Inconnue", "etage": r[1] if r[1] is not None else "-", "count": r[2]} for r in room_counts]
    
    # Équipements non assignés à une salle
    unassigned = db.query(Objet).filter(Objet.id_salle == None).count()
    if unassigned > 0:
        room_stats.append({"salle": "Non assigné", "etage": "-", "count": unassigned})
    
    # Événements : Alertes non résolues
    active_alerts = db.query(Alerte).filter(Alerte.est_resolu == False).order_by(Alerte.date_alerte.desc()).limit(5).all()
    
    # Événements : 5 Dernières Réservations
    recent_reservations = (
        db.query(Reservation, Utilisateur.nom, Utilisateur.prenom, Objet.nom_model)
        .join(Utilisateur, Reservation.id_utilisateur == Utilisateur.id_utilisateur)
        .join(Objet, Reservation.id_objet == Objet.id_objet)
        .order_by(Reservation.date_reservation.desc())
        .limit(5)
        .all()
    )

    # Récupération détaillée pour les modales du dashboard
    all_users = db.query(Utilisateur).all()
    all_objects = db.query(Objet).all()

    # Top 10 Mensuel : Équipements les plus réservés (30 derniers jours)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    top_10 = (
        db.query(Objet.nom_marque, Objet.nom_model, func.count(Reservation.id).label("total_res"))
        .join(Reservation, Objet.id_objet == Reservation.id_objet)
        .filter(Reservation.date_reservation >= thirty_days_ago)
        .group_by(Objet.id_objet, Objet.nom_marque, Objet.nom_model)
        .order_by(func.count(Reservation.id).desc())
        .limit(10)
        .all()
    )

    # Tendance des réservations sur 30 jours (LineChart)
    trend_data = (
        db.query(cast(Reservation.date_reservation, Date).label("day"), func.count(Reservation.id))
        .filter(Reservation.date_reservation >= thirty_days_ago)
        .group_by(cast(Reservation.date_reservation, Date))
        .order_by(cast(Reservation.date_reservation, Date))
        .all()
    )

    return {
        "kpi": {
            "total_users": total_users,
            "total_equipments": total_equipments,
            "available_count": available_count,
            "occupied_count": occupied_count,
            "broken_count": broken_count
        },
        "details": {
            "users": [
                {"id": u.id_utilisateur, "nom": u.nom, "prenom": u.prenom, "email": u.email, "role": u.role} 
                for u in all_users
            ],
            "equipments": [
                {"id": o.id_objet, "marque": o.nom_marque, "modele": o.nom_model, "statut": o.statut, "mac": o.mac_adresse, "ip": o.ip_adress}
                for o in all_objects
            ]
        },
        "charts": {
            "status_pie": [
                {"name": "Disponible", "value": available_count, "color": "#27ae60"},
                {"name": "Occupé", "value": occupied_count, "color": "#f39c12"},
                {"name": "En panne", "value": broken_count, "color": "#e74c3c"}
            ],
            "room_bars": room_stats,
            "reservation_trend": [
                {"date": str(t[0]), "count": t[1]} for t in trend_data
            ]
        },
        "events": {
            "active_alerts": [
                {
                    "id": a.id_alerte,
                    "message": a.message,
                    "date": a.date_alerte,
                    "niveau": a.niveau
                } for a in active_alerts
            ],
            "recent_reservations": [
                {
                    "reservation_id": r.Reservation.id,
                    "user": f"{r.nom} {r.prenom}",
                    "object_model": r.nom_model,
                    "date": r.Reservation.date_reservation,
                    "status": r.Reservation.statut_reservation
                } for r in recent_reservations
            ],
            "top_10_mensuel": [
                {
                    "marque": t[0],
                    "modele": t[1],
                    "reservations": t[2]
                } for t in top_10
            ]
        }
    }
