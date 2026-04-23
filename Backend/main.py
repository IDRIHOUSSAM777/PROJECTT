import os
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from data.rate_limit import limiter
from data.database import engine as db_engine, Base, SessionLocal
from data import models
import asyncio
from datetime import datetime
from search.ping_service import check_ip_active
from data.redis_client import clear_search_cache, redis_client, publish_status_change

# Cadence du watcher TTL (cf. rapport §7.3.2). Doit être < HEARTBEAT_TTL (90s)
# pour détecter une panne dans les 30s qui suivent l'expiration de la clé Redis.
HEARTBEAT_WATCHER_INTERVAL = 30

# Imports des Routers
from routers import users, objets, search, alertes, iot, public, admin, favoris, realtime, power, actions as device_actions, chat

# Création des tables
Base.metadata.create_all(bind=db_engine)

# Migration additive pour les colonnes Wake-on-LAN (create_all ne met pas à jour
# les tables existantes). Idempotent grâce à IF NOT EXISTS.
def _ensure_wol_columns():
    from sqlalchemy import text
    statements = [
        "ALTER TABLE objets ADD COLUMN IF NOT EXISTS supports_wol BOOLEAN DEFAULT FALSE",
        "ALTER TABLE objets ADD COLUMN IF NOT EXISTS power_state VARCHAR DEFAULT 'unknown'",
        "ALTER TABLE objets ADD COLUMN IF NOT EXISTS last_wake_at TIMESTAMP NULL",
    ]
    with db_engine.begin() as conn:
        for sql in statements:
            try:
                conn.execute(text(sql))
            except Exception as e:
                print(f"⚠️ ALTER objets a échoué ({sql}) : {e}")

_ensure_wol_columns()

# Migration additive : colonne "vu" sur la table alertes (lecture par l'admin).
def _ensure_alerte_columns():
    from sqlalchemy import text
    with db_engine.begin() as conn:
        try:
            conn.execute(text("ALTER TABLE alertes ADD COLUMN IF NOT EXISTS vu BOOLEAN DEFAULT FALSE"))
        except Exception as e:
            print(f"⚠️ ALTER alertes.vu a échoué : {e}")

_ensure_alerte_columns()

app = FastAPI(title="SmartFind API")

# Rate limiter partagé (stocke l'état dans Redis en prod via REDIS_URL si défini)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- BACKGROUND MONITORING (PING) ---
async def ping_devices_background_task():
    """
    Tâche d'arrière-plan qui s'exécute toutes les 60 secondes pour vérifier 
    l'état du réseau des objets via Ping.
    """
    print("🚀 Démarrage du Ping Monitor en arrière-plan...")
    await asyncio.sleep(5)
    
    while True:
        try:
            db = SessionLocal()
            
            objets_avec_ip = db.query(models.Objet).filter(
                models.Objet.ip_adress.isnot(None),
                models.Objet.ip_adress != ""
            ).all()

            for objet in objets_avec_ip:
                is_active = await check_ip_active(objet.ip_adress)
                
                if is_active:
                    if objet.statut in ["Panne", "Signalé"]:
                        objet.statut = "Disponible"
                            
                        objet.last_heartbeat = datetime.utcnow()
                        print(f"✅ [PING] {objet.nom_model} ({objet.ip_adress}) est revenu en ligne -> {objet.statut}")

                else: 
                    if objet.statut in ["Disponible", "Occupé"]:
                        ancien_statut = objet.statut
                        objet.statut = "Panne"
                        print(f"❌ [PING] {objet.nom_model} ({objet.ip_adress}) ne répond plus. Statut -> Panne")
                        
                        # NOTE L'objet est en panne. Plus de gestion de réservation possible ici.
                        print(f"❌ [PING] {objet.nom_model} ({objet.ip_adress}) ne répond plus. Statut -> Panne")

            db.commit()
            db.close()
            clear_search_cache()
            
        except Exception as e:
            print(f"⚠️ Erreur dans le Ping Monitor: {str(e)}")
            
        await asyncio.sleep(60)


async def heartbeat_ttl_watcher():
    """
    Watcher Redis (rapport §7.3.2 Protocole 1) : pour chaque objet pourvu d'une
    MAC, vérifie l'existence de la clé "heartbeat:{mac}". Si elle a expiré
    (TTL dépassé) alors que l'objet est marqué Disponible/Occupé, on bascule
    son statut en Panne, on crée une alerte (anti-doublon) et on diffuse le
    changement sur Pub/Sub.
    """
    print("🚀 Démarrage du Heartbeat TTL Watcher...")
    await asyncio.sleep(5)

    while True:
        try:
            db = SessionLocal()
            objets_iot = db.query(models.Objet).filter(
                models.Objet.mac_adresse.isnot(None),
                models.Objet.mac_adresse != "",
            ).all()

            transitions = []
            for objet in objets_iot:
                key = f"heartbeat:{objet.mac_adresse}"
                alive = False
                try:
                    alive = redis_client.exists(key) == 1
                except Exception as e:
                    print(f"⚠️ Redis exists() échoué pour {key}: {str(e)}")
                    continue

                if not alive and objet.statut in ("Disponible", "Occupé"):
                    objet.statut = "Panne"
                    transitions.append(objet.id_objet)

                    existante = db.query(models.Alerte).filter(
                        models.Alerte.id_objet == objet.id_objet,
                        models.Alerte.est_resolu == False,
                        models.Alerte.source == "IoT",
                    ).first()
                    if not existante:
                        print(f"🚨 [HEARTBEAT] Création d'une alerte pour l'objet {objet.id_objet}")
                        db.add(models.Alerte(
                            message="Heartbeat absent : objet considéré hors-ligne (TTL Redis expiré)",
                            niveau="Critical",
                            source="IoT",
                            id_objet=objet.id_objet,
                        ))
                    print(f"❌ [HEARTBEAT-TTL] {objet.nom_model} ({objet.mac_adresse}) → Panne")

            if transitions:
                db.commit()
                clear_search_cache()
                for id_objet in transitions:
                    publish_status_change(id_objet, "Panne", source="heartbeat-ttl")
            db.close()
        except Exception as e:
            print(f"⚠️ Erreur dans le Heartbeat TTL Watcher : {str(e)}")

        await asyncio.sleep(HEARTBEAT_WATCHER_INTERVAL)


@app.on_event("startup")
async def startup_event():
    # Le ping ICMP reste désactivé : le watcher TTL ci-dessous le remplace
    # pour les objets équipés d'une MAC (Protocole 1 du rapport).
    asyncio.create_task(heartbeat_ttl_watcher())

# --- CONFIGURATION DU CORS (LIAISON FRONT-BACK) ---
origins = [
    "http://localhost:5173",    
    "http://127.0.0.1:5173",    
    "http://localhost:3000",    
    "*"                         
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,      
    allow_credentials=True,     
    allow_methods=["*"],        
    allow_headers=["*"],        
)

if not os.path.exists("uploads"):
    os.makedirs("uploads")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# --- INCLUSION DES ROUTERS ---
app.include_router(users.router)
app.include_router(objets.router)
app.include_router(search.router)
app.include_router(alertes.router)
app.include_router(iot.router)
app.include_router(public.router)
app.include_router(admin.router)
app.include_router(favoris.router)
app.include_router(realtime.router)
app.include_router(power.router)
app.include_router(device_actions.router)
app.include_router(chat.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
