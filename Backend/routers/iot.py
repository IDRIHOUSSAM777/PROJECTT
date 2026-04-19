import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Body
from sqlalchemy.orm import Session
from typing import List, Optional

from data import models
from data import schemas
import auth
from data.database import get_db
from data.redis_client import clear_search_cache, publish_status_change, publish_event, CHANNEL_STATUTS, redis_client
from security import anomaly_detection as sec

# TTL (en secondes) appliqué à chaque clé Redis "heartbeat:{mac}" : si aucun
# heartbeat n'est reçu pendant cette fenêtre, la clé expire et le watcher de
# main.py bascule l'objet en Panne (rapport §7.3.2 Protocole 1).
HEARTBEAT_TTL = 90

router = APIRouter(tags=["IoT Heartbeat"])


def _raise_security_alert(
    db: Session,
    id_objet: Optional[int],
    detection: dict,
    quarantine: bool = False,
) -> None:
    """Crée une alerte Security (anti-doublon) et, si demandé, bascule
    l'objet en statut Quarantaine. Appelé par tous les détecteurs."""
    reason = detection.get("reason", "anomaly")
    details = detection.get("details", {})
    message = f"[SECURITY] {reason} — {details}"

    existante = None
    if id_objet is not None:
        existante = (
            db.query(models.Alerte)
            .filter(
                models.Alerte.id_objet == id_objet,
                models.Alerte.est_resolu == False,
                models.Alerte.source == "Security",
                models.Alerte.message.contains(reason),
            )
            .first()
        )

    if not existante:
        db.add(
            models.Alerte(
                message=message[:480],
                niveau="Critical",
                source="Security",
                id_objet=id_objet,
            )
        )

    if quarantine and id_objet is not None:
        objet = (
            db.query(models.Objet)
            .filter(models.Objet.id_objet == id_objet)
            .first()
        )
        if objet and objet.statut != "Quarantaine":
            objet.statut = "Quarantaine"
            try:
                publish_status_change(
                    id_objet, "Quarantaine", source="security", extra={"reason": reason}
                )
            except Exception:
                pass

@router.post("/iot/heartbeat")
def receive_heartbeat(
    heartbeat: schemas.HeartbeatSchema, 
    request: Request, 
    db: Session = Depends(get_db)
):
    objet = db.query(models.Objet).filter(models.Objet.mac_adresse == heartbeat.mac_adresse).first()
    if not objet:
        raise HTTPException(404, "Objet inconnu (MAC non reconnue)")

    client_ip = request.client.host if request.client else ""

    # -- Détection cybersécurité --------------------------------------------
    # Un rogue device / conflit ARP / heartbeat hors segment autorisé doit
    # mettre l'objet en Quarantaine immédiatement (ne jamais faire confiance
    # à la source tant que l'admin n'a pas validé).
    subnet_det = sec.check_subnet_allowed(client_ip)
    if subnet_det.get("detected"):
        _raise_security_alert(db, objet.id_objet, subnet_det, quarantine=True)

    mac_det = sec.check_mac_conflict(client_ip, heartbeat.mac_adresse)
    if mac_det.get("detected"):
        _raise_security_alert(db, objet.id_objet, mac_det, quarantine=True)

    rate_det = sec.check_heartbeat_rate(heartbeat.mac_adresse)
    if rate_det.get("detected"):
        _raise_security_alert(db, objet.id_objet, rate_det, quarantine=False)

    # Si l'objet vient d'être mis en Quarantaine par un détecteur ci-dessus,
    # on n'écrase pas le statut en traitant la suite.
    if objet.statut == "Quarantaine":
        db.commit()
        clear_search_cache()
        return {"status": "quarantined", "message": "Anomalie détectée — objet en quarantaine"}

    objet.ip_adress = client_ip
    objet.last_heartbeat = datetime.utcnow()

    # Empreinte TTL : tant que cette clé existe dans Redis, l'objet est considéré
    # vivant. Le watcher de main.py marque Panne dès qu'elle expire.
    try:
        redis_client.setex(f"heartbeat:{heartbeat.mac_adresse}", HEARTBEAT_TTL, "alive")
    except Exception as e:
        print(f"⚠️ Redis setex heartbeat échoué : {str(e)}")

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
    publish_status_change(objet.id_objet, objet.statut, source="heartbeat", extra={"raw": heartbeat.statut})
    return {"status": "ok", "message": f"Heartbeat traité. Statut actuel : {objet.statut}"}


# ----------------------------------------------------------------------------
# WEBHOOK STATUTS (Protocole 1 du rapport §7.3.2)
# Plus léger que /iot/heartbeat : la passerelle IoT envoie uniquement les
# transitions de statut, sans toucher à last_heartbeat / IP.
# ----------------------------------------------------------------------------
@router.post("/iot/status", tags=["IoT Webhook"])
def receive_status_webhook(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    mac = payload.get("mac_adresse") or payload.get("mac")
    nouveau_statut = payload.get("statut") or payload.get("status")
    if not mac or not nouveau_statut:
        raise HTTPException(400, "Champs requis : mac_adresse, statut")

    objet = db.query(models.Objet).filter(models.Objet.mac_adresse == mac).first()
    if not objet:
        raise HTTPException(404, "Objet inconnu (MAC non reconnue)")

    ancien_statut = objet.statut

    # Détection de flapping : trop de transitions rapides => anomalie
    flap_det = sec.check_status_flapping(objet.id_objet, nouveau_statut, ancien_statut)
    if flap_det.get("detected"):
        _raise_security_alert(db, objet.id_objet, flap_det, quarantine=True)
        db.commit()
        clear_search_cache()
        return {
            "status": "quarantined",
            "reason": "status_flapping",
            "ancien": ancien_statut,
        }

    objet.statut = nouveau_statut

    # Auto-création d'alerte si transition vers Panne (anti-doublon)
    if nouveau_statut == "Panne" and ancien_statut != "Panne":
        existante = db.query(models.Alerte).filter(
            models.Alerte.id_objet == objet.id_objet,
            models.Alerte.est_resolu == False,
            models.Alerte.source == "IoT",
        ).first()
        if not existante:
            db.add(models.Alerte(
                message=f"Panne signalée par webhook : {payload.get('detail', nouveau_statut)}",
                niveau="Critical",
                source="IoT",
                id_objet=objet.id_objet,
            ))

    db.commit()
    clear_search_cache()
    publish_status_change(objet.id_objet, nouveau_statut, source="webhook", extra={"ancien": ancien_statut})
    return {"status": "ok", "ancien": ancien_statut, "nouveau": nouveau_statut}


# ----------------------------------------------------------------------------
# ACTIONNER (W3C Web of Things — invokeaction)
# Exécute une action exposée par le Thing Description (cf. /objets/{id}/td).
# L'action doit correspondre à une fonctionnalité de l'objet.
# ----------------------------------------------------------------------------
@router.post("/objets/{objet_id}/action", tags=["Web of Things (W3C)"])
def invoke_action(
    objet_id: int,
    action: Optional[str] = None,
    body: Optional[dict] = Body(None),
    current_user: models.Utilisateur = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    # action peut venir en query param (?action=…) ou en body { "action": "…" }
    action_name = (action or (body or {}).get("action") or "").strip().lower()
    if not action_name:
        raise HTTPException(400, "Paramètre 'action' requis")

    objet = db.query(models.Objet).filter(models.Objet.id_objet == objet_id).first()
    if not objet:
        raise HTTPException(404, "Objet introuvable")

    if objet.statut in ("Panne", "Signalé"):
        raise HTTPException(409, f"Objet indisponible (statut: {objet.statut})")

    fonctions_dispo = {f.nom.lower() for f in objet.fonctionnalites}
    if action_name not in fonctions_dispo:
        raise HTTPException(
            400,
            f"Action '{action_name}' non supportée. Disponibles: {sorted(fonctions_dispo)}",
        )

    # Simulation d'exécution : on émet un événement "action invoquée" sur Pub/Sub.
    # Une vraie passerelle IoT s'abonnerait à ce canal pour piloter l'objet réel.
    user_id = current_user.id_utilisateur if current_user.id_utilisateur != 0 else None
    publish_event("channel:actions", {
        "id_objet": objet_id,
        "action": action_name,
        "invoked_by": user_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    })

    return {
        "status": "invoked",
        "id_objet": objet_id,
        "action": action_name,
        "message": f"Action '{action_name}' envoyée à l'objet",
    }

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
