from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import List

from data import models
from data import schemas
import auth
from data.database import get_db

router = APIRouter(tags=["Gestion des Alertes (Admin)"])


@router.get("/admin/alertes/unread_count")
def get_unread_alertes_count(
    db: Session = Depends(get_db),
    current_user: models.Utilisateur = Depends(auth.get_current_admin),
):
    """Nombre d'alertes non-lues (non résolues et non vues par l'admin)."""
    count = db.query(models.Alerte).filter(
        models.Alerte.est_resolu == False,
        models.Alerte.vu == False,
    ).count()
    return {"count": count}


@router.post("/admin/alertes/mark_all_read")
def mark_all_alertes_read(
    db: Session = Depends(get_db),
    current_user: models.Utilisateur = Depends(auth.get_current_admin),
):
    """Marque toutes les alertes non résolues comme lues par l'admin."""
    updated = db.query(models.Alerte).filter(
        models.Alerte.est_resolu == False,
        models.Alerte.vu == False,
    ).update({models.Alerte.vu: True}, synchronize_session=False)
    db.commit()
    return {"updated": updated}


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
            "nom_signaleur": signaleur,
            "id_objet": a.id_objet,
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

    db.commit()

    if alerte.objet:
        from data.redis_client import clear_search_cache, publish_status_change
        clear_search_cache()
        publish_status_change(alerte.objet.id_objet, nouveau_statut_objet, source="admin_resolve", extra={"alerte_id": alerte_id})

    return {"message": f"Alerte résolue. L'objet est maintenant '{nouveau_statut_objet}'"}


@router.delete("/admin/alertes/{alerte_id}")
def delete_alerte(
    alerte_id: int,
    db: Session = Depends(get_db),
    current_user: models.Utilisateur = Depends(auth.get_current_admin),
):
    alerte = db.query(models.Alerte).filter(models.Alerte.id_alerte == alerte_id).first()
    if not alerte:
        raise HTTPException(404, "Alerte introuvable")
    db.delete(alerte)
    db.commit()
    return {"message": "Alerte supprimée"}


@router.post("/objets/{objet_id}/report")
def signaler_probleme(
    objet_id: int,
    description: str = Body(..., embed=True),
    current_user: models.Utilisateur = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    objet = db.query(models.Objet).filter(models.Objet.id_objet == objet_id).first()
    if not objet: raise HTTPException(404, "Objet introuvable")

    description = (description or "").strip()
    if not description:
        raise HTTPException(400, "Description requise")

    if objet.statut != "Panne":
        objet.statut = "Signalé"

    print(f"📩 [REPORT] Nouveau signalement pour l'objet {objet_id}: {description}")
    id_utilisateur_db = current_user.id_utilisateur if current_user.id_utilisateur != 0 else None

    new_alerte = models.Alerte(
        message=description,
        niveau="Warning",
        source="Utilisateur",
        id_objet=objet_id,
        id_utilisateur=id_utilisateur_db
    )

    db.add(new_alerte)
    db.commit()
    print(f"✅ [REPORT] Alerte #{new_alerte.id_alerte} enregistrée en BDD.")

    # Invalidation du cache (le statut a changé) + publication temps réel
    from data.redis_client import clear_search_cache, publish_status_change
    clear_search_cache()
    publish_status_change(objet_id, objet.statut, source="report")

    return {"message": "Problème signalé. L'objet est en attente de vérification."}
