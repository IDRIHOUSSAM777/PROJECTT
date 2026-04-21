"""
Gestion de l'alimentation physique des équipements.

Concept : lier Objet.statut (BD) à l'alimentation réelle du matériel pour
réaliser des économies d'énergie. Au lieu de laisser les équipements
allumés 24/7, ils sont placés en veille profonde par défaut et réveillés
à la demande via un Magic Packet Wake-on-LAN quand un utilisateur clique
sur l'équipement dans l'application.

Choix architectural : WoL uniquement (standard IEEE universellement supporté,
un seul adaptateur à maintenir, extensible via une Action W3C WoT turnOn
dont l'implémentation interne pourra accueillir IPMI, prises Zigbee, API
constructeurs plus tard sans casser le contrat client).
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from wakeonlan import send_magic_packet

import auth
from data import models, schemas
from data.database import get_db
from data.rate_limit import limiter
from data.redis_client import clear_search_cache, publish_status_change

router = APIRouter(prefix="/objets", tags=["Power Management"])


def auto_wake_if_needed(obj: models.Objet, db: Session) -> dict | None:
    """
    Réveille automatiquement l'équipement si (et seulement si) :
      - il supporte le WoL (supports_wol = True)
      - une MAC est renseignée
      - son power_state n'est pas déjà "on"

    Retourne un dict descriptif quand un Magic Packet a été envoyé, None sinon.
    Échec silencieux : une erreur d'envoi n'interrompt pas l'action utilisateur
    (l'équipement peut être déjà allumé sans que power_state ait été mis à jour).
    """
    if not obj.supports_wol or not obj.mac_adresse:
        return None
    if obj.power_state == "on":
        return None

    try:
        send_magic_packet(obj.mac_adresse)
    except Exception as e:
        print(f"⚠️ [AUTO-WAKE] Magic Packet échoué pour {obj.mac_adresse}: {e}")
        return None

    now = datetime.utcnow()
    obj.power_state = "on"
    obj.last_wake_at = now
    db.commit()
    db.refresh(obj)

    try:
        clear_search_cache()
    except Exception:
        pass

    try:
        publish_status_change(
            obj.id_objet,
            obj.statut,
            source="auto-wake",
            extra={"power_state": "on"},
        )
    except Exception:
        pass

    return {
        "mac_adresse": obj.mac_adresse,
        "power_state": "on",
        "triggered_at": now.isoformat() + "Z",
    }


def _build_thing_description(obj: models.Objet) -> dict:
    """
    Thing Description W3C WoT (v1.1) pour un équipement.

    Le contrat reste stable quel que soit le protocole d'allumage sous-jacent.
    Aujourd'hui : WoL uniquement pour les objets dont supports_wol=True.
    Demain : IPMI, prises Zigbee, API constructeurs — sans modifier le TD
    côté client, seule l'implémentation interne de /wake évolue.
    """
    td = {
        "@context": "https://www.w3.org/2022/wot/td/v1.1",
        "id": f"urn:smartfind:objet:{obj.id_objet}",
        "title": obj.nom_model or f"Objet {obj.id_objet}",
        "description": obj.description or "",
        "securityDefinitions": {
            "bearer_sc": {"scheme": "bearer", "format": "jwt"}
        },
        "security": "bearer_sc",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["Disponible", "Occupé", "Panne", "Signalé"],
                "readOnly": True,
                "forms": [
                    {"href": f"/objets/{obj.id_objet}", "op": "readproperty"}
                ],
            },
            "powerState": {
                "type": "string",
                "enum": ["on", "sleep", "unknown"],
                "readOnly": True,
                "forms": [
                    {"href": f"/objets/{obj.id_objet}", "op": "readproperty"}
                ],
            },
        },
        "actions": {},
    }

    if obj.supports_wol and obj.mac_adresse:
        td["actions"]["turnOn"] = {
            "description": (
                "Réveille l'équipement. Implémentation actuelle : Magic Packet "
                "Wake-on-LAN. Extensible à IPMI / prises connectées / API "
                "constructeurs sans changement de contrat."
            ),
            "safe": False,
            "idempotent": True,
            "forms": [
                {
                    "href": f"/objets/{obj.id_objet}/wake",
                    "op": "invokeaction",
                    "contentType": "application/json",
                }
            ],
        }

    return td


@router.post("/{id_objet}/wake", response_model=schemas.WakeResponse)
@limiter.limit("5/minute")
def wake_objet(
    request: Request,
    id_objet: int,
    current_user: models.Utilisateur = Depends(auth.get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Envoie un Magic Packet WoL vers l'adresse MAC de l'équipement.

    Endpoint de maintenance (admin uniquement). Le chemin nominal pour les
    utilisateurs passe par /objets/{id}/action : le réveil est alors déclenché
    automatiquement par auto_wake_if_needed() avant l'invocation de l'action.

    Pré-conditions :
      - l'équipement existe
      - supports_wol = True
      - mac_adresse renseignée et valide

    Post-conditions :
      - power_state bascule en "on"
      - last_wake_at mis à jour
      - cache de recherche invalidé (le power_state impacte la pertinence)
      - événement publié sur le canal realtime
    """
    obj = (
        db.query(models.Objet)
        .filter(models.Objet.id_objet == id_objet)
        .first()
    )
    if not obj:
        raise HTTPException(status_code=404, detail="Objet introuvable")

    if not obj.supports_wol:
        raise HTTPException(
            status_code=400,
            detail="Cet équipement ne supporte pas le Wake-on-LAN.",
        )

    if not obj.mac_adresse:
        raise HTTPException(
            status_code=400,
            detail="Adresse MAC manquante sur cet équipement.",
        )

    try:
        # wakeonlan accepte les MAC au format AA:BB:CC:DD:EE:FF ou AA-BB-...
        send_magic_packet(obj.mac_adresse)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Adresse MAC invalide : {e}")
    except Exception as e:
        # Erreur réseau, socket, broadcast bloqué, etc.
        raise HTTPException(
            status_code=502,
            detail=f"Envoi du Magic Packet échoué : {e}",
        )

    now = datetime.utcnow()
    obj.power_state = "on"
    obj.last_wake_at = now
    db.commit()
    db.refresh(obj)

    # Le power_state peut être utilisé comme facteur de ranking (bonus pour les
    # équipements déjà réveillés), donc on invalide le cache.
    try:
        clear_search_cache()
    except Exception:
        pass

    try:
        publish_status_change(obj.id_objet, obj.statut, source="wake-on-lan")
    except Exception:
        pass

    return schemas.WakeResponse(
        message="Magic Packet envoyé.",
        mac_adresse=obj.mac_adresse,
        power_state=obj.power_state,
        triggered_at=now,
    )


@router.get("/{id_objet}/thing-description")
def get_thing_description(
    id_objet: int,
    db: Session = Depends(get_db),
):
    """
    Thing Description W3C WoT (v1.1) de l'équipement.

    Endpoint public (pas d'auth) : un TD décrit le contrat d'interaction,
    pas les données métier. L'invocation réelle de turnOn reste protégée
    par l'authentification sur /wake.
    """
    obj = (
        db.query(models.Objet)
        .filter(models.Objet.id_objet == id_objet)
        .first()
    )
    if not obj:
        raise HTTPException(status_code=404, detail="Objet introuvable")
    return _build_thing_description(obj)
