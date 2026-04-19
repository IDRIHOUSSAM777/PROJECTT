"""
WebSocket temps réel — diffusion des changements de statut des objets.

Architecture (cf. rapport §7.3) :
    1. Webhook /iot/status (ou heartbeat) modifie un objet en BDD
    2. Le router publie l'événement sur Redis Pub/Sub canal "channel:statuts"
    3. Cet endpoint WebSocket s'abonne au canal et relaie chaque message
       vers tous les clients connectés (Admin Dashboard, Equipment.jsx, ...)
"""
import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from data.redis_client import redis_client, CHANNEL_STATUTS

router = APIRouter(tags=["Realtime (WebSocket)"])


@router.websocket("/ws/statuts")
async def ws_statuts(websocket: WebSocket):
    """
    Abonnement temps réel aux changements de statut.
    Le client reçoit du JSON : {id_objet, statut, source, timestamp, ...}
    """
    await websocket.accept()
    pubsub = redis_client.pubsub(ignore_subscribe_messages=True)

    try:
        pubsub.subscribe(CHANNEL_STATUTS)
        await websocket.send_text(json.dumps({"event": "subscribed", "channel": CHANNEL_STATUTS}))

        while True:
            # get_message() de redis-py est SYNCHRONE et bloque la boucle asyncio.
            # On l'exécute dans un thread pour ne pas paralyser uvicorn quand
            # plusieurs clients WebSocket sont connectés en parallèle.
            message = await asyncio.to_thread(pubsub.get_message, timeout=0.5)
            if message and message.get("type") == "message":
                data = message.get("data")
                if isinstance(data, bytes):
                    data = data.decode("utf-8", errors="ignore")
                await websocket.send_text(data)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"⚠️ WS /ws/statuts erreur : {str(e)}")
    finally:
        try:
            pubsub.unsubscribe(CHANNEL_STATUTS)
            pubsub.close()
        except Exception:
            pass
