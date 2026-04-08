from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

# --- IoT ---
class HeartbeatSchema(BaseModel):
    mac_adresse: str
    statut: str

# --- Fonctionnalités ---
class FonctionnaliteBase(BaseModel):
    id: int
    nom: str
    class Config:
        from_attributes = True

# --- Objets ---
class ObjetBase(BaseModel):
    nom_model: str
    type_objet: str
    nom_marque: str
    mac_adresse: str

class ObjetCreate(ObjetBase):
    id_salle: int
    ip_adress: Optional[str] = None
    pos_x: Optional[float] = None
    pos_y: Optional[float] = None
    description: Optional[str] = None
    fonctionnalites: List[str] = [] # Liste de noms (ex: ["Wifi", "Scanner"])

class ObjetUpdate(BaseModel):
    nom_model: Optional[str] = None
    statut: Optional[str] = None
    description: Optional[str] = None
    nom_marque: Optional[str] = None
    type_objet: Optional[str] = None
    mac_adresse: Optional[str] = None
    ip_adress: Optional[str] = None
    id_salle: Optional[int] = None
    fonctionnalites: Optional[List[str]] = None

class ObjetResponse(ObjetBase):
    id_objet: int
    id_salle: Optional[int]
    ip_adress: Optional[str]
    pos_x: Optional[float]
    pos_y: Optional[float]
    statut: str
    url_photo: Optional[str]
    fonctionnalites: List[FonctionnaliteBase] = [] # Objets complets
    distance_m: Optional[float] = None
    waiting_count: int = 0
    popularity_score: Optional[float] = None
    relevance_score: Optional[float] = None

    class Config:
        from_attributes = True

# --- Utilisateurs ---
class UserCreate(BaseModel):
    email: str
    password: str
    nom: str
    prenom: str

class VerifyEmailRequest(BaseModel):
    email: str
    code: str

class UserUpdate(BaseModel):
    nom: Optional[str] = None
    prenom: Optional[str] = None
    current_password: Optional[str] = None
    password: Optional[str] = None

class UserResponse(BaseModel):
    id_utilisateur: int
    email: str
    nom: str
    prenom: str
    role: str # Important pour le frontend
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

# --- Réservation & Historique ---
class ReservationResponse(BaseModel):
    id: int
    date_reservation: datetime
    statut_reservation: str
    objet: ObjetResponse # On imbrique l'objet pour l'affichage
    class Config:
        from_attributes = True


# --- Alertes ---
class AlerteCreate(BaseModel):
    message: str
    niveau: str = "Warning"

class AlerteResponse(BaseModel):
    id_alerte: int
    message: str
    niveau: str
    source: str
    date_alerte: datetime
    est_resolu: bool
    
    # Pour afficher les noms au lieu des ID (Plus lisible)
    nom_objet: str 
    nom_signaleur: Optional[str] = "Système IoT" 

    class Config:
        from_attributes = True

class HistoriqueResponse(BaseModel):
    date_his: datetime
    requete_search: str
    class Config:
        from_attributes = True


class CategoryResponse(BaseModel):
    nom: str
    count: int # Le nombre d'objets dans cette catégorie (ex: 5 Imprimantes)
    
    class Config:
        from_attributes = True
# --- Equipment Details & Reservation Queue ---
class EquipmentLocation(BaseModel):
    building: Optional[str] = None
    floor: Optional[int] = None
    room: Optional[str] = None


class EquipmentDetailsResponse(BaseModel):
    id: int
    name: str
    type: Optional[str] = None
    marque: Optional[str] = None
    status: str
    mac_adresse: Optional[str] = None
    ip_adress: Optional[str] = None
    localisation: EquipmentLocation
    distance_m: Optional[float] = None
    description: Optional[str] = None
    url_photo: Optional[str] = None
    fonctionnalites: List[str] = []

    queue_count: int = 0
    active_reservation_id: Optional[int] = None
    my_reservation_id: Optional[int] = None
    my_reservation_status: Optional[str] = None


class QueueInfoResponse(BaseModel):
    object_id: int
    waiting_count: int
    active_reservation_id: Optional[int] = None


class ReservationCreateRequest(BaseModel):
    object_id: int
    user_id: Optional[int] = None


class ReservationActionResponse(BaseModel):
    message: str
    reservation_id: Optional[int] = None
    reservation_status: Optional[str] = None
    queue_count: int = 0
    object_status: Optional[str] = None


class NotificationResponse(BaseModel):
    id_notification: int
    message: str
    type_notification: str
    est_lu: bool
    date_notification: datetime
    id_objet: Optional[int] = None
    id_reservation: Optional[int] = None

    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    items: List[NotificationResponse]
    unread_count: int


class NotificationUpdateResponse(BaseModel):
    message: str
    unread_count: int

