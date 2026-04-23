"""
Dispatcher : envoie une action à l'agent local de l'équipement.

Stratégie :
  - Visio (organiser_meeting)    → généré en interne (URL Jitsi), aucun agent requis
  - Autres types (imprimer, scan, …) → POST HTTP à http://{obj.ip_adress}:9000/execute

L'agent répond soit synchrone (exécution rapide) soit asynchrone en appelant
notre callback POST /objets/agent/callback avec le résultat final.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from data import models


# Port fixe sur lequel l'agent écoute ; choix arbitraire, hors well-known ports.
AGENT_PORT = int(os.getenv("DEVICE_AGENT_PORT", "9000"))
AGENT_TIMEOUT = float(os.getenv("DEVICE_AGENT_TIMEOUT", "10.0"))

# Token partagé par tous les agents en démo. En prod on aurait une clé par objet.
AGENT_SHARED_TOKEN = os.getenv("DEVICE_AGENT_TOKEN", "smartfind-agent-dev-token")

# URL publique du backend (utilisée par l'agent pour télécharger payload + callback).
# En démo locale le backend tourne sur le même réseau que l'agent.
BACKEND_PUBLIC_BASE = os.getenv("BACKEND_PUBLIC_BASE", "http://127.0.0.1:8000")


def _jitsi_room_url(title: Optional[str]) -> str:
    """Génère une URL Jitsi unique. Le nom de salle inclut un UUID pour éviter
    les collisions — le titre éventuel est prépend\u00e9 pour l'humain."""
    slug = (title or "").strip().lower().replace(" ", "-")
    slug = "".join(c for c in slug if c.isalnum() or c == "-")[:40]
    room = f"smartfind-{slug}-{uuid.uuid4().hex[:8]}" if slug else f"smartfind-{uuid.uuid4().hex[:12]}"
    return f"https://meet.jit.si/{room}"


def dispatch_task(task: models.DeviceTask, objet: models.Objet, db: Session) -> dict:
    """
    Envoie la tâche à l'agent (ou la résout localement pour la visio).

    Renvoie un dict :
      {"sync": bool, "result_url": Optional[str], "error": Optional[str]}
      - sync=True  → tâche terminée en synchrone, lire result_url/error
      - sync=False → agent a accepté, statut final viendra via callback
    """
    # ── Cas spécial Visio : pas d'agent, on génère l'URL ici ────────────────
    if task.action == "organiser_meeting":
        url = _jitsi_room_url(task.payload_text)
        task.status = "success"
        task.result_url = url
        task.completed_at = datetime.utcnow()
        db.commit()
        return {"sync": True, "result_url": url, "error": None}

    # ── Cas général : HTTP vers l'agent ─────────────────────────────────────
    if not objet.ip_adress:
        task.status = "failed"
        task.error = "Équipement non provisionné (aucune IP configurée)"
        task.completed_at = datetime.utcnow()
        db.commit()
        return {"sync": True, "result_url": None, "error": task.error}

    agent_url = f"http://{objet.ip_adress}:{AGENT_PORT}/execute"
    payload_download_url = (
        f"{BACKEND_PUBLIC_BASE}/{task.payload_path.lstrip('/')}"
        if task.payload_path else None
    )
    body = {
        "task_id": task.id_task,
        "action": task.action,
        "payload_url": payload_download_url,
        "payload_text": task.payload_text,
        "callback_url": f"{BACKEND_PUBLIC_BASE}/objets/agent/callback",
        "type_objet": objet.type_objet,
    }
    headers = {"X-Agent-Token": AGENT_SHARED_TOKEN}

    try:
        with httpx.Client(timeout=AGENT_TIMEOUT) as client:
            resp = client.post(agent_url, json=body, headers=headers)
        if resp.status_code >= 500:
            raise httpx.HTTPStatusError(
                f"Agent HTTP {resp.status_code}", request=resp.request, response=resp
            )
        data = {}
        try:
            data = resp.json() or {}
        except Exception:
            pass

        # L'agent peut répondre synchrone ou demander un traitement asynchrone.
        if data.get("sync") is True:
            task.status = "success" if resp.status_code < 400 else "failed"
            task.result_url = data.get("result_url")
            task.error = data.get("error")
            task.completed_at = datetime.utcnow()
        else:
            # Statut intermédiaire : l'agent a accusé réception, on attend callback
            task.status = "dispatched"
        db.commit()
        return {
            "sync": bool(data.get("sync")),
            "result_url": data.get("result_url"),
            "error": data.get("error"),
        }
    except httpx.TimeoutException:
        task.status = "timeout"
        task.error = f"Agent injoignable ({objet.ip_adress}:{AGENT_PORT}) — timeout"
        task.completed_at = datetime.utcnow()
        db.commit()
        return {"sync": True, "result_url": None, "error": task.error}
    except Exception as e:
        task.status = "failed"
        task.error = f"Échec dispatch : {e}"
        task.completed_at = datetime.utcnow()
        db.commit()
        return {"sync": True, "result_url": None, "error": task.error}
