"""
Routes : actions utilisateur → équipement.

Endpoints :
  GET  /objets/{id}/actions       → liste des actions disponibles pour cet objet
  POST /objets/{id}/action        → déclenche une action (JSON ou multipart)
  GET  /tasks/{task_id}           → statut d'une tâche (pour polling côté frontend)
  POST /objets/agent/callback     → callback de l'agent local (asynchrone)
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Optional, List

from fastapi import (
    APIRouter, Depends, HTTPException, UploadFile, File, Form, Header, Request,
)
from sqlalchemy.orm import Session

import auth
from data import models, schemas
from data.database import get_db
from data.rate_limit import limiter
from actions.catalog import (
    is_interactive_type,
    get_action_spec,
    list_actions_for_object,
)
from actions.dispatcher import dispatch_task, AGENT_SHARED_TOKEN
from routers.power import auto_wake_if_needed


router = APIRouter(tags=["Actions (User → Device)"])


# Racine pour les fichiers liés aux tâches. Sert /uploads via StaticFiles.
UPLOADS_DIR = "uploads"
TASKS_SUBDIR = "tasks"


def _save_upload(file: UploadFile, task_id_hint: str) -> str:
    """Sauvegarde un fichier uploadé dans uploads/tasks/{hint}/ et retourne
    le chemin relatif (servi via /uploads/…)."""
    folder = os.path.join(UPLOADS_DIR, TASKS_SUBDIR, task_id_hint)
    os.makedirs(folder, exist_ok=True)
    safe_name = os.path.basename(file.filename or "payload.bin").replace("..", "_")
    dest = os.path.join(folder, safe_name)
    with open(dest, "wb") as f:
        content = file.file.read()
        f.write(content)
    return f"/{dest}"


@router.get("/objets/{id_objet}/actions", response_model=List[schemas.ActionSpec])
def list_object_actions(
    id_objet: int,
    db: Session = Depends(get_db),
    current_user: models.Utilisateur = Depends(auth.get_current_user),
):
    """Liste filtrée des actions exposables pour l'UI."""
    objet = db.query(models.Objet).filter(models.Objet.id_objet == id_objet).first()
    if not objet:
        raise HTTPException(404, "Objet introuvable")

    fonctions = [f.nom for f in objet.fonctionnalites]
    return list_actions_for_object(objet.type_objet, fonctions)


@router.post("/objets/{id_objet}/action", response_model=schemas.ActionDispatchResponse)
@limiter.limit("10/minute")
def invoke_action(
    request: Request,
    id_objet: int,
    action: str = Form(...),
    payload_text: Optional[str] = Form(None),
    payload_url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    current_user: models.Utilisateur = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Déclenche une action sur un équipement. Multipart pour supporter un fichier
    optionnel — les champs texte vides sont acceptés (envoyés comme "").

    Pipeline :
      1. Vérif objet existe + type interactif
      2. Vérif action ∈ catalogue ∧ déclarée par l'objet
      3. Vérif payload correspond au `input_kind` de la spec
      4. Création ligne DeviceTask
      5. Sauvegarde fichier si présent
      6. Auto-wake WoL si nécessaire
      7. Dispatch via dispatcher (Jitsi en interne / HTTP vers agent)
    """
    objet = db.query(models.Objet).filter(models.Objet.id_objet == id_objet).first()
    if not objet:
        raise HTTPException(404, "Objet introuvable")

    if not is_interactive_type(objet.type_objet):
        raise HTTPException(
            400,
            f"Le type '{objet.type_objet}' ne supporte pas les actions interactives.",
        )

    if objet.statut in ("Panne", "Signalé"):
        raise HTTPException(409, f"Objet indisponible (statut : {objet.statut})")

    spec = get_action_spec(objet.type_objet, action)
    if not spec:
        raise HTTPException(400, f"Action '{action}' inconnue pour ce type d'objet.")

    # Validation du payload selon input_kind
    kind = spec["input_kind"]
    payload_path: Optional[str] = None

    if kind == "file":
        if not file:
            raise HTTPException(400, "Fichier requis pour cette action.")
        max_size = spec.get("max_size") or (20 * 1024 * 1024)
        # On lit dans _save_upload, donc on vérifie taille via seek
        file.file.seek(0, 2)
        size = file.file.tell()
        file.file.seek(0)
        if size > max_size:
            raise HTTPException(413, f"Fichier trop volumineux (max {max_size} octets).")
    elif kind == "url":
        if not payload_url or not payload_url.strip():
            raise HTTPException(400, "URL requise pour cette action.")
        if not (payload_url.startswith("http://") or payload_url.startswith("https://")):
            raise HTTPException(400, "URL invalide (schéma http/https attendu).")
        if len(payload_url) > 2048:
            raise HTTPException(400, "URL trop longue (max 2048 caractères).")
    elif kind == "text":
        if not spec.get("optional") and (not payload_text or not payload_text.strip()):
            raise HTTPException(400, "Texte requis pour cette action.")
    elif kind == "none":
        pass
    else:
        raise HTTPException(500, f"Type d'entrée inconnu : {kind}")

    # Création de la tâche
    user_id = current_user.id_utilisateur if current_user.id_utilisateur != 0 else None
    task = models.DeviceTask(
        id_objet=id_objet,
        id_utilisateur=user_id,
        action=spec["key"],
        status="pending",
        payload_text=(payload_url or payload_text or None),
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    # Sauvegarde du fichier (après commit pour avoir task.id_task)
    if file and kind == "file":
        task.payload_path = _save_upload(file, str(task.id_task))
        db.commit()

    # Auto-wake WoL si applicable
    wake_info = auto_wake_if_needed(objet, db)

    # Dispatch
    result = dispatch_task(task, objet, db)
    db.refresh(task)

    if task.status == "failed" or task.status == "timeout":
        # On renvoie 200 avec statut dans le body pour que le front affiche
        # l'erreur proprement plutôt qu'un 5xx générique.
        return schemas.ActionDispatchResponse(
            task_id=task.id_task,
            status=task.status,
            message=task.error or "Échec de l'action",
            auto_wake=wake_info,
            result_url=task.result_url,
        )

    message = f"Action '{spec['key']}' envoyée"
    if task.status == "success":
        message = f"Action '{spec['key']}' terminée"
    elif task.status == "dispatched":
        message = f"Action '{spec['key']}' en cours d'exécution"

    return schemas.ActionDispatchResponse(
        task_id=task.id_task,
        status=task.status,
        message=message,
        auto_wake=wake_info,
        result_url=task.result_url,
    )


@router.get("/tasks/{task_id}", response_model=schemas.TaskStatusResponse)
def get_task_status(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: models.Utilisateur = Depends(auth.get_current_user),
):
    """Polling : le frontend appelle toutes les 2s jusqu'au statut final."""
    task = db.query(models.DeviceTask).filter(models.DeviceTask.id_task == task_id).first()
    if not task:
        raise HTTPException(404, "Tâche introuvable")
    # Isolation : un utilisateur ne voit que ses propres tâches (admin voit tout)
    is_admin = current_user.email == "admin@smartfind.com"
    if not is_admin and task.id_utilisateur and task.id_utilisateur != current_user.id_utilisateur:
        raise HTTPException(403, "Accès interdit")
    return task


@router.post("/objets/agent/callback")
def agent_callback(
    payload: schemas.AgentCallback,
    x_agent_token: Optional[str] = Header(None, alias="X-Agent-Token"),
    db: Session = Depends(get_db),
):
    """
    Endpoint public (non-JWT) appelé par l'agent local pour notifier la fin
    d'une tâche asynchrone. Protégé par un jeton partagé dans l'en-tête.
    """
    if x_agent_token != AGENT_SHARED_TOKEN:
        raise HTTPException(401, "Token agent invalide")

    task = db.query(models.DeviceTask).filter(
        models.DeviceTask.id_task == payload.task_id
    ).first()
    if not task:
        raise HTTPException(404, "Tâche introuvable")

    allowed = {"running", "success", "failed"}
    if payload.status not in allowed:
        raise HTTPException(400, f"Statut invalide : {payload.status}")

    task.status = payload.status
    task.result_url = payload.result_url or task.result_url
    task.error = payload.error or task.error
    if payload.status in ("success", "failed"):
        task.completed_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "task_id": task.id_task, "status": task.status}
