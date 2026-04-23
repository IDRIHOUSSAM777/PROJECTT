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
    pos_x: Optional[float] = None
    pos_y: Optional[float] = None
    fonctionnalites: Optional[List[str]] = None
    supports_wol: Optional[bool] = None
    power_state: Optional[str] = None

class ObjetResponse(ObjetBase):
    id_objet: int
    id_salle: Optional[int]
    ip_adress: Optional[str]
    pos_x: Optional[float]
    pos_y: Optional[float]
    statut: str
    url_photo: Optional[str]
    date_integration: Optional[datetime] = None
    fonctionnalites: List[FonctionnaliteBase] = [] # Objets complets
    distance_m: Optional[float] = None
    waiting_count: int = 0
    popularity_score: Optional[float] = None
    relevance_score: Optional[float] = None
    supports_wol: bool = False
    power_state: str = "unknown"
    last_wake_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WakeResponse(BaseModel):
    message: str
    mac_adresse: str
    power_state: str
    triggered_at: datetime

# --- Utilisateurs ---
class UserCreate(BaseModel):
    email: str
    password: str
    nom: str
    prenom: str

class VerifyEmailRequest(BaseModel):
    email: str
    code: str

class ResendOTPRequest(BaseModel):
    email: str

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    email: str
    code: str
    new_password: str

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
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

# --- Historique ---


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
    id_objet: Optional[int] = None

    class Config:
        from_attributes = True

class HistoriqueResponse(BaseModel):
    id_historique: int
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
    name: str # Aliased for Equipment.jsx
    type: Optional[str] = None # Aliased for Equipment.jsx
    marque: Optional[str] = None # Aliased for Equipment.jsx
    
    # Old field names for compatibility (EditEquipment.jsx, etc.)
    nom_model: str 
    type_objet: str
    nom_marque: str
    id_salle: Optional[int] = None
    
    status: str
    mac_adresse: Optional[str] = None
    ip_adress: Optional[str] = None
    localisation: EquipmentLocation
    distance_m: Optional[float] = None
    description: Optional[str] = None
    url_photo: Optional[str] = None
    date_integration: Optional[datetime] = None
    fonctionnalites: List[str] = []
    supports_wol: bool = False
    power_state: str = "unknown"
    last_wake_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# --- Favoris ---
class FavoriResponse(BaseModel):
    id_objet: int
    nom_model: str
    nom_marque: Optional[str] = None
    type_objet: Optional[str] = None
    statut: str
    url_photo: Optional[str] = None
    date_ajout: datetime

    class Config:
        from_attributes = True


# --- Actions utilisateur → équipement ---
class ActionSpec(BaseModel):
    """Spec d'une action disponible, exposée au frontend pour rendu dynamique."""
    key: str
    label_fr: str
    input_kind: str  # none | file | url | text
    accept: Optional[str] = None
    max_size: Optional[int] = None
    placeholder: Optional[str] = None
    optional: Optional[bool] = None
    returns: str = "none"  # none | file | session_url


class TaskStatusResponse(BaseModel):
    id_task: int
    id_objet: int
    action: str
    status: str  # pending | dispatched | running | success | failed | timeout
    payload_path: Optional[str] = None
    payload_text: Optional[str] = None
    result_path: Optional[str] = None
    result_url: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ActionDispatchResponse(BaseModel):
    """Retour immédiat après POST /objets/{id}/action."""
    task_id: int
    status: str
    message: str
    auto_wake: Optional[dict] = None
    result_url: Optional[str] = None  # rempli si action synchrone (visio)


class AgentCallback(BaseModel):
    """Payload envoyé par l'agent local quand une tâche se termine."""
    task_id: int
    status: str  # success | failed | running
    result_url: Optional[str] = None
    error: Optional[str] = None
