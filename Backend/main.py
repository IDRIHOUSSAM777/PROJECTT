import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from data.database import engine as db_engine, Base, SessionLocal
from data import models
import asyncio
from datetime import datetime
from search.ping_service import check_ip_active
from data.redis_client import clear_search_cache

# Imports des Routers
from routers import users, objets, search, reservations, alertes, iot, public, notifications, admin

# Création des tables
Base.metadata.create_all(bind=db_engine)

app = FastAPI(title="SmartFind API")

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
                        reservation = db.query(models.Reservation).filter(
                            models.Reservation.id_objet == objet.id_objet,
                            models.Reservation.statut_reservation.in_(["ACTIVE", "Active"])
                        ).first()
                        
                        if reservation:
                            objet.statut = "Occupé"
                        else:
                            objet.statut = "Disponible"
                            
                        objet.last_heartbeat = datetime.utcnow()
                        print(f"✅ [PING] {objet.nom_model} ({objet.ip_adress}) est revenu en ligne -> {objet.statut}")

                else: 
                    if objet.statut in ["Disponible", "Occupé"]:
                        ancien_statut = objet.statut
                        objet.statut = "Panne"
                        print(f"❌ [PING] {objet.nom_model} ({objet.ip_adress}) ne répond plus. Statut -> Panne")
                        
                        if ancien_statut == "Occupé":
                            reservations = db.query(models.Reservation).filter(
                                models.Reservation.id_objet == objet.id_objet,
                                models.Reservation.statut_reservation.in_(["ACTIVE", "Active", "WAITING", "Waiting"])
                            ).all()
                            
                            for res in reservations:
                                message_notification = f"⚠️ ALERTE PING: L'équipement que vous avez réservé ({objet.nom_model}) ne répond plus sur le réseau. Il est marqué en Panne."
                                new_notif = models.Notification(
                                    message=message_notification,
                                    type_notification="PANNE_IOT", 
                                    id_utilisateur=res.id_utilisateur,
                                    id_objet=objet.id_objet,
                                    id_reservation=res.id,
                                )
                                db.add(new_notif)

            db.commit()
            db.close()
            clear_search_cache()
            
        except Exception as e:
            print(f"⚠️ Erreur dans le Ping Monitor: {str(e)}")
            
        await asyncio.sleep(60)


@app.on_event("startup")
async def startup_event():
    # TEMPORARILY DISABLED: asyncio.create_task(ping_devices_background_task())
    pass

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
app.include_router(reservations.router)
app.include_router(alertes.router)
app.include_router(iot.router)
app.include_router(public.router)
app.include_router(notifications.router)
app.include_router(admin.router)
