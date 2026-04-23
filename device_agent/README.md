# SmartFind Device Agent

Agent local de démonstration. À lancer sur chaque équipement interactif
(imprimante, scanner, projecteur, écran). Écoute sur le port 9000 et
exécute les actions demandées par le backend SmartFind.

## Installation

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Lancement

```bash
# Mode simulation (par défaut) — imprime seulement des logs
python agent.py

# Impression réelle via CUPS :
SIMULATE=0 CUPS_PRINTER_NAME=HP_LaserJet python agent.py

# Variables disponibles :
#   AGENT_PORT               (défaut 9000)
#   DEVICE_AGENT_TOKEN       (doit matcher celui du backend)
#   CUPS_PRINTER_NAME        nom imprimante CUPS à utiliser
#   SIMULATE                 "1" (défaut) = simulation ; "0" = commandes réelles
```

## Protocole

Le backend envoie :

```
POST http://<ip-equipement>:9000/execute
Headers: X-Agent-Token: <token partagé>
Body:    { task_id, action, payload_url, payload_text, callback_url, type_objet }
```

L'agent répond immédiatement `{ "sync": false }` et traite l'action en
arrière-plan, puis appelle `callback_url` avec le résultat final
(`status`, `result_url`, `error`).

## Actions prises en charge

- `imprimer` — télécharge le PDF via `payload_url` et appelle `lp -d`
- `scanner` — appelle `scanimage` (ou PNG placeholder en simu)
- `projeter_image`, `projeter_video`, `afficher_video` — `open` / `xdg-open`
- `afficher_contenu` — log texte (pour démo écran intelligent)

> `organiser_meeting` est géré côté backend (URL Jitsi) et n'atteint
> jamais l'agent.
