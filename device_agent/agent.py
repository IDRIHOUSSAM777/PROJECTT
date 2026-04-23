"""
Agent local de démonstration pour SmartFind.

À déployer sur chaque équipement interactif (imprimante, scanner, projecteur,
écran). Écoute sur le port 9000 et exécute l'action demandée par le backend.

Protocole (cf. Backend/actions/dispatcher.py) :

  POST /execute
    Headers : X-Agent-Token: <token partagé>
    Body    : {
                "task_id": int,
                "action": "imprimer" | "scanner" | "projeter_image" | ...,
                "payload_url": Optional[str],  # URL du fichier à télécharger
                "payload_text": Optional[str],
                "callback_url": str,           # à appeler en mode async
                "type_objet": str
              }
    Réponse : {"sync": bool, "result_url": Optional[str], "error": Optional[str]}

Lancement :
    DEVICE_AGENT_TOKEN=smartfind-agent-dev-token python agent.py

Variables d'environnement :
    AGENT_PORT               (défaut : 9000)
    DEVICE_AGENT_TOKEN       (défaut : smartfind-agent-dev-token)
    CUPS_PRINTER_NAME        (optionnel : nom d'imprimante CUPS à utiliser)
    SIMULATE                 (1 par défaut — si 0, tente des commandes système réelles)
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel


AGENT_PORT = int(os.getenv("AGENT_PORT", "9000"))
AGENT_TOKEN = os.getenv("DEVICE_AGENT_TOKEN", "smartfind-agent-dev-token")
CUPS_PRINTER = os.getenv("CUPS_PRINTER_NAME")
SIMULATE = os.getenv("SIMULATE", "1") == "1"


app = FastAPI(title="SmartFind Device Agent")


class ExecuteRequest(BaseModel):
    task_id: int
    action: str
    payload_url: Optional[str] = None
    payload_text: Optional[str] = None
    callback_url: str
    type_objet: Optional[str] = None


def _download(url: str, suffix: str = "") -> Path:
    """Télécharge le payload vers un fichier temporaire et retourne le chemin."""
    r = httpx.get(url, timeout=30.0, follow_redirects=True)
    r.raise_for_status()
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="smartfind_")
    os.close(fd)
    Path(path).write_bytes(r.content)
    return Path(path)


def _print_pdf(path: Path) -> None:
    """Imprime via CUPS (`lp`) si disponible, sinon simule."""
    if SIMULATE or not CUPS_PRINTER:
        print(f"[SIM] Impression simulée de {path} ({path.stat().st_size} octets)")
        time.sleep(1)
        return
    subprocess.run(["lp", "-d", CUPS_PRINTER, str(path)], check=True)


def _scan_to_file() -> bytes:
    """Scan via `scanimage` si disponible, sinon renvoie un PNG placeholder."""
    if SIMULATE:
        # PNG 1x1 transparent en démo
        return bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000d49444154789c6360000000000500010d0a2db40000000049454e44ae42"
            "6082"
        )
    result = subprocess.run(
        ["scanimage", "--format=png"], check=True, capture_output=True
    )
    return result.stdout


def _project_or_display(url_or_text: str, kind: str) -> None:
    """Ouvre la ressource côté OS (démo) — en prod, protocole PJLink ou HDMI."""
    print(f"[SIM] {kind} : {url_or_text}")
    if SIMULATE:
        return
    # macOS : `open`, Linux : `xdg-open`, Windows : `start`
    opener = "open" if os.uname().sysname == "Darwin" else "xdg-open"
    subprocess.Popen([opener, url_or_text])


def _async_run(req: ExecuteRequest) -> None:
    """Exécute l'action en arrière-plan puis notifie le backend via callback."""
    status = "success"
    result_url: Optional[str] = None
    error: Optional[str] = None

    try:
        if req.action == "imprimer":
            if not req.payload_url:
                raise ValueError("payload_url manquant pour 'imprimer'")
            f = _download(req.payload_url, suffix=".pdf")
            _print_pdf(f)

        elif req.action == "scanner":
            data = _scan_to_file()
            out = Path(tempfile.gettempdir()) / f"scan_{req.task_id}.png"
            out.write_bytes(data)
            result_url = f"file://{out}"

        elif req.action in ("projeter_image", "projeter_video", "afficher_video"):
            target = req.payload_url or req.payload_text or ""
            if not target:
                raise ValueError("URL requise")
            _project_or_display(target, req.action)

        elif req.action == "afficher_contenu":
            _project_or_display(req.payload_text or "", "affichage")

        else:
            raise ValueError(f"Action inconnue : {req.action}")

    except Exception as e:
        status = "failed"
        error = str(e)

    # Callback vers le backend
    try:
        httpx.post(
            req.callback_url,
            json={
                "task_id": req.task_id,
                "status": status,
                "result_url": result_url,
                "error": error,
            },
            headers={"X-Agent-Token": AGENT_TOKEN},
            timeout=10.0,
        )
    except Exception as e:
        print(f"⚠️ Callback vers {req.callback_url} échoué : {e}")


@app.post("/execute")
def execute(
    req: ExecuteRequest,
    x_agent_token: Optional[str] = Header(None, alias="X-Agent-Token"),
):
    if x_agent_token != AGENT_TOKEN:
        raise HTTPException(401, "Token agent invalide")

    # Visio est géré côté backend, l'agent n'est jamais appelé pour cela
    if req.action == "organiser_meeting":
        raise HTTPException(400, "organiser_meeting est géré par le backend")

    # Mode asynchrone : on accuse réception immédiatement, le callback suivra
    threading.Thread(target=_async_run, args=(req,), daemon=True).start()
    return {"sync": False}


@app.get("/healthz")
def healthz():
    return {"status": "ok", "simulate": SIMULATE}


if __name__ == "__main__":
    import uvicorn
    print(f"🚀 SmartFind agent on :{AGENT_PORT} (SIMULATE={SIMULATE})")
    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT)
