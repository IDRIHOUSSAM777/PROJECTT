from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from data.database import get_db
from data import models

# Configuration (A mettre dans un fichier .env en production)
SECRET_KEY = "ta_cle_secrete_super_longue_et_aleatoire"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# Fonction pour protéger les routes (Dépendance)
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    if email == "admin@smartfind.com":
        # On utilise un objet fictif pour l'admin (id=0), il n'existe pas en BDD
        return models.Utilisateur(id_utilisateur=0, email="admin@smartfind.com", nom="System", prenom="Admin")
        
    user = db.query(models.Utilisateur).filter(models.Utilisateur.email == email).first()
    if user is None:
        raise credentials_exception
            
    return user



# On crée une instance OAuth2 qui ne déclenche pas d'erreur 401 si le token manque (auto_error=False)
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="login", auto_error=False)

async def get_current_user_optional(
    token: Optional[str] = Depends(oauth2_scheme_optional),
    db: Session = Depends(get_db)
) -> Optional[models.Utilisateur]:
    """
    Récupère l'utilisateur courant s'il est connecté,
    sinon retourne None (sans lever d'erreur 401).
    """
    if not token:
        return None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            return None
    except JWTError:
        return None
        
    if email == "admin@smartfind.com":
        return models.Utilisateur(id_utilisateur=0, email="admin@smartfind.com", nom="System", prenom="Admin")
        
    user = db.query(models.Utilisateur).filter(models.Utilisateur.email == email).first()
    return user

def get_current_admin(current_user: models.Utilisateur = Depends(get_current_user)):
    if current_user.email != "admin@smartfind.com":
        raise HTTPException(status_code=403, detail="Privilèges Administrateur requis")
    return current_user