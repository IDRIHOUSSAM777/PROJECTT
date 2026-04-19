from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date
from datetime import datetime, timedelta
from data.database import get_db
from data.models import Objet, Utilisateur, Salle, Favori, Alerte

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
    occupied_count = sum(v for k, v in stats_dict.items() if "occup" in str(k).lower())
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
    
    # Récupération détaillée pour les modales du dashboard
    all_users = db.query(Utilisateur).all()
    all_objects = db.query(Objet).all()

    # KPI : Total Favoris
    total_favorites = db.query(Favori).count()

    # Top Favoris : Top 10 des objets réellement ajoutés en favoris (INNER JOIN)
    top_favorited = (
        db.query(Objet, func.count(Favori.id_objet).label("fav_count"))
        .join(Favori, Objet.id_objet == Favori.id_objet)
        .group_by(Objet.id_objet)
        .order_by(func.count(Favori.id_objet).desc(), Objet.id_objet.asc())
        .limit(10)
        .all()
    )

    popular_items = [
        {
            "id": o.id_objet,
            "marque": o.nom_marque,
            "modele": o.nom_model,
            "count": fav_count,
            "statut": o.statut
        } for o, fav_count in top_favorited
    ]

    # KPI Cybersécurité
    quarantine_count = sum(v for k, v in stats_dict.items() if "quarantaine" in str(k).lower())
    security_alerts_active = (
        db.query(Alerte)
        .filter(Alerte.source == "Security", Alerte.est_resolu == False)
        .count()
    )
    security_alerts = (
        db.query(Alerte)
        .filter(Alerte.source == "Security", Alerte.est_resolu == False)
        .order_by(Alerte.date_alerte.desc())
        .limit(10)
        .all()
    )

    return {
        "kpi": {
            "available_count": available_count,
            "occupied_count": occupied_count,
            "broken_count": broken_count,
            "quarantine_count": quarantine_count,
            "security_alerts_active": security_alerts_active,
        },
        "security": {
            "active_alerts": [
                {
                    "id": a.id_alerte,
                    "message": a.message,
                    "niveau": a.niveau,
                    "id_objet": a.id_objet,
                    "date_alerte": a.date_alerte.isoformat() if a.date_alerte else None,
                }
                for a in security_alerts
            ],
        },
        "details": {
            "users": [
                {"id": u.id_utilisateur, "nom": u.nom, "prenom": u.prenom, "email": u.email} 
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
            "room_bars": room_stats
        },
        "events": {
            "popular_items": popular_items
        }
    }
