from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import List

from data import models
from data import schemas
import auth
from data.database import get_db

router = APIRouter(tags=["Auth & Utilisateurs"])

import random
import string

@router.post("/signup", response_model=schemas.UserResponse)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.query(models.Utilisateur).filter(models.Utilisateur.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email déjà utilisé")
    
    hashed_pw = auth.get_password_hash(user.password)
    verification_code = ''.join(random.choices(string.digits, k=6))
    
    new_user = models.Utilisateur(
        email=user.email, 
        hashed_password=hashed_pw, 
        nom=user.nom, 
        prenom=user.prenom,
        est_verifie=False,
        code_verification=verification_code
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Simulation de l'envoi d'email
    print(f"📧 [EMAIL SIMULATION] Envoi de l'OTP {verification_code} à {user.email}")
    
    return new_user

@router.post("/verify-email")
def verify_email(req: schemas.VerifyEmailRequest, db: Session = Depends(get_db)):
    user = db.query(models.Utilisateur).filter(models.Utilisateur.email == req.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    
    if user.est_verifie:
        raise HTTPException(status_code=400, detail="Email déjà vérifié")
        
    if user.code_verification != req.code:
        raise HTTPException(status_code=400, detail="Code incorrect")
        
    user.est_verifie = True
    user.code_verification = None
    db.commit()
    
    return {"message": "Email vérifié avec succès"}

@router.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.Utilisateur).filter(models.Utilisateur.email == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Identifiants incorrects")
        
    if not user.est_verifie:
        raise HTTPException(status_code=403, detail="Veuillez d'abord vérifier votre email avec le code envoyé.")
    access_token = auth.create_access_token(data={"sub": user.email, "role": user.role})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/users/me", response_model=schemas.UserResponse)
async def read_users_me(current_user: models.Utilisateur = Depends(auth.get_current_user)):
    """
    Renvoie les infos de l'utilisateur connecté.
    Nécessite un token valide.
    """
    return current_user

@router.put("/users/me", response_model=schemas.UserResponse)
def update_profile(
    user_update: schemas.UserUpdate, 
    current_user: models.Utilisateur = Depends(auth.get_current_user), 
    db: Session = Depends(get_db)
):
    if user_update.nom:
        current_user.nom = user_update.nom
    if user_update.prenom:
        current_user.prenom = user_update.prenom

    if user_update.password:
        if not user_update.current_password:
            raise HTTPException(status_code=400, detail="Mot de passe actuel requis")
        if not auth.verify_password(user_update.current_password, current_user.hashed_password):
            raise HTTPException(status_code=400, detail="Mot de passe actuel incorrect")
        if len(user_update.password) < 6:
            raise HTTPException(status_code=400, detail="Le nouveau mot de passe doit contenir au moins 6 caractères")
        current_user.hashed_password = auth.get_password_hash(user_update.password)

    db.commit()
    db.refresh(current_user)
    return current_user

@router.get("/users/me/history", response_model=List[schemas.HistoriqueResponse])
def get_history(current_user: models.Utilisateur = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return db.query(models.Historique)\
        .filter(models.Historique.id_utilisateur == current_user.id_utilisateur)\
        .order_by(models.Historique.date_his.desc())\
        .all()

@router.get("/users/me/reservations", response_model=List[schemas.ReservationResponse])
def get_reservations(current_user: models.Utilisateur = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return db.query(models.Reservation)\
        .filter(models.Reservation.id_utilisateur == current_user.id_utilisateur)\
        .order_by(models.Reservation.date_reservation.desc())\
        .all()
