from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_, func
from collections import Counter
from security import anomaly_detection as sec
from typing import List

from data import models
from data import schemas
from data.rate_limit import limiter
from data.redis_client import redis_client
from slowapi.util import get_remote_address
import auth
from data.database import get_db

import hashlib
import hmac
import json
import re
import secrets
import string
import os
import time

import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException as BrevoApiException

# Configuration Brevo — plan gratuit : 300 emails / jour
# Sender vérifié obligatoire (Expéditeurs, domaine, IP)
BREVO_API_KEY = os.getenv("BREVO_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM")  # Doit être vérifié côté Brevo
EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "SmartFind")

_brevo_client = None


def _get_brevo_client():
    """Client Brevo lazy — une seule instance réutilisée."""
    global _brevo_client
    if _brevo_client is None and BREVO_API_KEY:
        config = sib_api_v3_sdk.Configuration()
        config.api_key["api-key"] = BREVO_API_KEY
        _brevo_client = sib_api_v3_sdk.TransactionalEmailsApi(
            sib_api_v3_sdk.ApiClient(config)
        )
    return _brevo_client

# Message générique — ne révèle jamais l'existence ou non d'un compte
GENERIC_INVALID_CODE_MSG = "Code invalide ou expiré"
GENERIC_EMAIL_SENT_MSG = "Si cet email est enregistré, un code a été envoyé."

# Paramètres OTP
OTP_MAX_ATTEMPTS = 5
OTP_TTL_MINUTES = 5
OTP_DIGITS = int(os.getenv("OTP_DIGITS", 8))
OTP_DAILY_FAIL_BUDGET = int(os.getenv("OTP_DAILY_FAIL_BUDGET", 15))

# Pepper serveur pour HMAC — rend les rainbow tables inutilisables
# Fallback uniquement en dev ; en prod, variable obligatoire
OTP_PEPPER = os.getenv("OTP_PEPPER", "dev-only-pepper-change-me").encode("utf-8")

# Flag debug — gate les print() sensibles (codes OTP en console)
DEBUG_MODE = os.getenv("DEBUG") == "1"

# Monitoring SMTP
SMTP_ALERT_THRESHOLD = 5

from datetime import datetime, timedelta


def hash_otp(code: str) -> str:
    """HMAC-SHA256 avec pepper serveur — un leak DB seul ne suffit pas à casser les codes."""
    return hmac.new(OTP_PEPPER, code.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_otp(code: str, stored_hash: str | None) -> bool:
    """Compare en temps constant pour éviter les timing attacks."""
    if not stored_hash:
        return False
    return hmac.compare_digest(hash_otp(code), stored_hash)


def generate_otp() -> str:
    """OTP N chiffres avec secrets (crypto-random). Par défaut 8 chiffres → 10^8 possibilités."""
    return "".join(secrets.choice(string.digits) for _ in range(OTP_DIGITS))


def validate_password(password: str) -> None:
    """Lève HTTPException(400) si le mot de passe est trop faible."""
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Le mot de passe doit contenir au moins 8 caractères")
    if not re.search(r"[A-Za-z]", password):
        raise HTTPException(status_code=400, detail="Le mot de passe doit contenir au moins une lettre")
    if not re.search(r"\d", password):
        raise HTTPException(status_code=400, detail="Le mot de passe doit contenir au moins un chiffre")


# ----- Budget de tentatives cumulé 24h (anti-bypass via /resend-otp) -----

def _daily_fail_key(email: str) -> str:
    return f"otp:daily_failures:{email.lower()}"


def check_daily_failure_budget(email: str) -> None:
    """Bloque si l'utilisateur a dépassé son budget d'échecs sur 24h."""
    try:
        val = redis_client.get(_daily_fail_key(email))
        if val and int(val) >= OTP_DAILY_FAIL_BUDGET:
            raise HTTPException(
                status_code=429,
                detail="Trop de tentatives échouées. Réessayez dans 24 heures.",
            )
    except HTTPException:
        raise
    except Exception as e:
        # Redis indisponible → on fail-open (dispo > sécurité sur ce contrôle secondaire)
        print(f"⚠️ Redis indisponible (check budget) : {e}")


def increment_daily_failures(email: str) -> None:
    """Incrémente le compteur cumulé avec TTL 24h. Persiste cross-/resend-otp."""
    try:
        key = _daily_fail_key(email)
        pipe = redis_client.pipeline()
        pipe.incr(key)
        pipe.expire(key, 86400)  # 24h
        pipe.execute()
    except Exception as e:
        print(f"⚠️ Redis indisponible (incr budget) : {e}")


def reset_daily_failures(email: str) -> None:
    """Réinitialise le compteur après succès."""
    try:
        redis_client.delete(_daily_fail_key(email))
    except Exception:
        pass


# ----- Rate-limit compound key (IP + email) -----

def ip_and_email_key(request: Request) -> str:
    """
    Clé slowapi combinant IP + email du corps JSON pour bloquer à la fois :
    - un botnet qui tape plein d'emails depuis plein d'IPs (côté IP)
    - un attaquant qui change d'IP mais vise un email précis (côté email)
    """
    ip = get_remote_address(request)
    # Le corps n'est pas encore parsé par FastAPI à ce stade ; on retombe sur l'IP seule
    # si on ne peut pas lire l'email. slowapi cumule déjà sur plusieurs endpoints.
    try:
        email = getattr(request.state, "rl_email", None)
        if email:
            return f"{ip}:{email.lower()}"
    except Exception:
        pass
    return ip


# ----- Monitoring SMTP (alerte si trop d'échecs consécutifs) -----

SMTP_FAIL_KEY = "smtp:consecutive_failures"


def _register_smtp_success():
    try:
        redis_client.delete(SMTP_FAIL_KEY)
    except Exception:
        pass


def _register_smtp_failure():
    try:
        count = redis_client.incr(SMTP_FAIL_KEY)
        redis_client.expire(SMTP_FAIL_KEY, 3600)
        if count >= SMTP_ALERT_THRESHOLD:
            print(f"🚨 ALERTE SMTP : {count} échecs consécutifs — vérifier credentials / quota")
    except Exception:
        pass


def send_email(to_email: str, subject: str, html_body: str, max_retries: int = 2) -> bool:
    """
    Envoie un email HTML via l'API Brevo (ex-Sendinblue) avec retry sur 5xx.
    Retourne True si accepté, False sinon.

    Codes Brevo :
        201 Created       → email accepté et queued
        400               → payload invalide (email mal formé, HTML cassé)
        401               → clé API invalide
        402               → quota quotidien atteint
        403               → sender non vérifié
        4xx (hors 429)    → pas de retry
        429 / 5xx / réseau → retry exponentiel
    """
    client = _get_brevo_client()
    if client is None or not EMAIL_FROM:
        print("⚠️  Brevo non configuré (BREVO_API_KEY / EMAIL_FROM manquants).")
        return False

    payload = sib_api_v3_sdk.SendSmtpEmail(
        sender={"email": EMAIL_FROM, "name": EMAIL_FROM_NAME},
        to=[{"email": to_email}],
        subject=subject,
        html_content=html_body,
        tags=["transactional-otp"],
        headers={"X-Entity-Ref-ID": f"otp-{int(time.time())}-{to_email}"},
    )

    last_err = None
    for attempt in range(1, max_retries + 2):
        try:
            response = client.send_transac_email(payload)
            message_id = getattr(response, "message_id", None)
            print(f"✉️  Email envoyé à {to_email} (Brevo id={message_id}, essai {attempt})")
            _register_smtp_success()
            return True

        except BrevoApiException as e:
            status = e.status
            body = (e.body or b"").decode("utf-8", "replace") if isinstance(e.body, bytes) else str(e.body)

            # 4xx sauf 429 → définitif (clé invalide, sender non vérifié, quota)
            if status and 400 <= status < 500 and status != 429:
                print(f"❌ Brevo {status} (erreur client, pas de retry) : {body}")
                _register_smtp_failure()
                return False

            last_err = f"Brevo {status} {body}"
            print(f"⚠️  Brevo {status} essai {attempt}/{max_retries + 1} — retry : {body}")

        except Exception as e:
            last_err = e
            print(f"⚠️  Brevo exception essai {attempt}/{max_retries + 1} : {e}")

        if attempt <= max_retries:
            time.sleep(2 ** (attempt - 1))  # 1s, 2s, 4s

    print(f"❌ Envoi Brevo définitivement échoué pour {to_email} : {last_err}")
    _register_smtp_failure()
    return False


def _debug_log_otp(tag: str, email: str, code: str):
    """Log console de l'OTP — uniquement si DEBUG=1. NE JAMAIS activer en prod."""
    if DEBUG_MODE:
        print(f"📧 [{tag}] Code pour {email} : {code}")

def get_html_template(prenom: str, code: str, is_reset=False):
    title = "Réinitialisation de votre mot de passe" if is_reset else "Vérification de votre adresse email"
    intro = (
        "Nous avons reçu une demande de réinitialisation du mot de passe associé à votre compte."
        if is_reset
        else "Merci d'avoir créé un compte SmartFind. Pour finaliser votre inscription, veuillez confirmer votre adresse email."
    )
    action_text = (
        "Saisissez le code de sécurité ci-dessous dans l'application pour définir un nouveau mot de passe."
        if is_reset
        else "Saisissez le code de sécurité ci-dessous dans l'application pour activer votre compte."
    )
    disclaimer = (
        "Si vous n'êtes pas à l'origine de cette demande, ignorez simplement cet email — votre mot de passe actuel restera inchangé."
        if is_reset
        else "Si vous n'êtes pas à l'origine de cette inscription, vous pouvez ignorer ce message en toute sécurité."
    )

    # Espaces insécables pour éviter un retour à la ligne disgracieux du code OTP
    code_spaced = "&nbsp;".join(list(code))

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
</head>
<body style="margin:0; padding:0; background-color:#f4f6fb; font-family:'Segoe UI', Helvetica, Arial, sans-serif; color:#1e293b;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f6fb; padding:32px 16px;">
        <tr>
            <td align="center">
                <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px; width:100%; background-color:#ffffff; border-radius:12px; overflow:hidden; box-shadow:0 2px 8px rgba(15,23,42,0.06);">
                    <!-- En-tête -->
                    <tr>
                        <td style="background-color:#1e3a8a; padding:28px 32px; text-align:left;">
                            <div style="font-size:20px; font-weight:600; letter-spacing:1px; color:#ffffff;">SMARTFIND</div>
                            <div style="font-size:13px; color:#c7d2fe; margin-top:4px;">Smart Building — Gestion des équipements</div>
                        </td>
                    </tr>

                    <!-- Corps -->
                    <tr>
                        <td style="padding:36px 40px 16px 40px;">
                            <h1 style="font-size:20px; font-weight:600; color:#0f172a; margin:0 0 16px 0;">{title}</h1>
                            <p style="font-size:15px; line-height:1.6; color:#334155; margin:0 0 12px 0;">Bonjour <strong>{prenom}</strong>,</p>
                            <p style="font-size:15px; line-height:1.6; color:#334155; margin:0 0 12px 0;">{intro}</p>
                            <p style="font-size:15px; line-height:1.6; color:#334155; margin:0 0 24px 0;">{action_text}</p>
                        </td>
                    </tr>

                    <!-- Code OTP -->
                    <tr>
                        <td style="padding:0 40px 8px 40px;" align="center">
                            <div style="display:inline-block; background-color:#f1f5f9; border:1px solid #e2e8f0; border-radius:10px; padding:20px 28px;">
                                <div style="font-size:12px; text-transform:uppercase; letter-spacing:1.5px; color:#64748b; margin-bottom:8px;">Code de vérification</div>
                                <div style="font-size:30px; font-weight:700; letter-spacing:6px; color:#1e3a8a; font-family:'Courier New', Consolas, monospace;">{code_spaced}</div>
                            </div>
                        </td>
                    </tr>

                    <!-- Validité -->
                    <tr>
                        <td style="padding:16px 40px 24px 40px;" align="center">
                            <p style="font-size:13px; color:#64748b; margin:0;">Ce code est valable pendant <strong>5 minutes</strong>. Ne le partagez avec personne.</p>
                        </td>
                    </tr>

                    <!-- Disclaimer sécurité -->
                    <tr>
                        <td style="padding:0 40px 32px 40px;">
                            <div style="background-color:#fef3c7; border-left:3px solid #f59e0b; padding:12px 16px; border-radius:4px;">
                                <p style="font-size:13px; line-height:1.5; color:#78350f; margin:0;">{disclaimer}</p>
                            </div>
                        </td>
                    </tr>

                    <!-- Pied de page -->
                    <tr>
                        <td style="background-color:#f8fafc; padding:20px 40px; border-top:1px solid #e2e8f0;" align="center">
                            <p style="font-size:12px; color:#64748b; margin:0 0 4px 0;">Cet email a été envoyé automatiquement, merci de ne pas y répondre.</p>
                            <p style="font-size:12px; color:#94a3b8; margin:0;">&copy; 2026 SmartFind — USTHB. Tous droits réservés.</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""

router = APIRouter(tags=["Auth & Utilisateurs"])

@router.post("/signup", response_model=schemas.UserResponse)
@limiter.limit("3/minute", key_func=ip_and_email_key)
def create_user(
    request: Request,
    user: schemas.UserCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    # Attache l'email à l'état de la requête pour le key_func compound
    request.state.rl_email = user.email

    # Validation du mot de passe en tout premier
    validate_password(user.password)

    verification_code = generate_otp()
    code_hashed = hash_otp(verification_code)
    expiration = datetime.utcnow() + timedelta(minutes=OTP_TTL_MINUTES)
    hashed_pw = auth.get_password_hash(user.password)

    existing_user = db.query(models.Utilisateur).filter(models.Utilisateur.email == user.email).first()

    if existing_user and existing_user.est_verifie:
        raise HTTPException(status_code=400, detail="Email déjà utilisé")

    try:
        if existing_user:
            # Compte existant non-vérifié → upsert + nouveau code
            existing_user.nom = user.nom
            existing_user.prenom = user.prenom
            existing_user.hashed_password = hashed_pw
            existing_user.code_verification = code_hashed
            existing_user.otp_expires_at = expiration
            existing_user.otp_attempts = 0
            db.commit()
            db.refresh(existing_user)
            target_user = existing_user
        else:
            new_user = models.Utilisateur(
                email=user.email,
                hashed_password=hashed_pw,
                nom=user.nom,
                prenom=user.prenom,
                est_verifie=False,
                code_verification=code_hashed,
                otp_expires_at=expiration,
                otp_attempts=0,
            )
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
            target_user = new_user
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Email déjà utilisé")

    _debug_log_otp("SIGNUP", target_user.email, verification_code)

    # Envoi synchrone : avec SendGrid l'API répond en ~200 ms et on peut
    # propager une vraie erreur au client si l'email ne part pas.
    html_content = get_html_template(target_user.prenom, verification_code)
    sent = send_email(
        target_user.email,
        "Vérification de votre compte SmartFind",
        html_content,
    )
    if not sent:
        raise HTTPException(
            status_code=502,
            detail="L'email de vérification n'a pas pu être envoyé. Réessayez dans quelques instants.",
        )

    return target_user

@router.post("/resend-otp")
@limiter.limit("3/minute", key_func=ip_and_email_key)
def resend_otp(
    request: Request,
    req: schemas.ResendOTPRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Renvoie un nouveau code — réponse générique anti-énumération."""
    request.state.rl_email = req.email

    # Budget cumulatif : impossible de bypass la limite /verify-email
    # en spammant /resend-otp pour reset otp_attempts
    check_daily_failure_budget(req.email)

    user = db.query(models.Utilisateur).filter(models.Utilisateur.email == req.email).first()

    # Ne révèle jamais si l'email existe ou si le compte est déjà vérifié
    if user and not user.est_verifie:
        verification_code = generate_otp()
        user.code_verification = hash_otp(verification_code)
        user.otp_expires_at = datetime.utcnow() + timedelta(minutes=OTP_TTL_MINUTES)
        user.otp_attempts = 0
        db.commit()

        _debug_log_otp("RESEND", user.email, verification_code)

        html_content = get_html_template(user.prenom, verification_code)
        background_tasks.add_task(
            send_email,
            user.email,
            "Nouveau code de vérification SmartFind",
            html_content,
        )

    return {"message": GENERIC_EMAIL_SENT_MSG}

@router.post("/forgot-password")
@limiter.limit("3/minute", key_func=ip_and_email_key)
def forgot_password(
    request: Request,
    req: schemas.ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    request.state.rl_email = req.email
    check_daily_failure_budget(req.email)

    user = db.query(models.Utilisateur).filter(models.Utilisateur.email == req.email).first()
    if user:
        code = generate_otp()
        user.code_verification = hash_otp(code)
        user.otp_expires_at = datetime.utcnow() + timedelta(minutes=OTP_TTL_MINUTES)
        user.otp_attempts = 0
        db.commit()

        _debug_log_otp("RESET", user.email, code)

        html_content = get_html_template(user.prenom, code, is_reset=True)
        background_tasks.add_task(
            send_email,
            req.email,
            "Réinitialisation de votre mot de passe",
            html_content,
        )

    return {"message": GENERIC_EMAIL_SENT_MSG}

@router.post("/reset-password")
@limiter.limit("5/minute", key_func=ip_and_email_key)
def reset_password(
    request: Request,
    req: schemas.ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    request.state.rl_email = req.email

    # Validation du mot de passe d'abord (erreur légitime à renvoyer)
    validate_password(req.new_password)

    check_daily_failure_budget(req.email)

    user = db.query(models.Utilisateur).filter(models.Utilisateur.email == req.email).first()

    # Anti-enum : même message pour user inexistant / code mauvais / code expiré
    if not user or not verify_otp(req.code, user.code_verification):
        increment_daily_failures(req.email)
        raise HTTPException(status_code=400, detail=GENERIC_INVALID_CODE_MSG)

    if user.otp_expires_at and datetime.utcnow() > user.otp_expires_at:
        increment_daily_failures(req.email)
        raise HTTPException(status_code=400, detail=GENERIC_INVALID_CODE_MSG)

    user.hashed_password = auth.get_password_hash(req.new_password)
    user.code_verification = None
    user.otp_expires_at = None
    user.otp_attempts = 0
    db.commit()
    reset_daily_failures(req.email)
    return {"message": "Mot de passe réinitialisé avec succès"}

@router.post("/verify-email")
@limiter.limit("10/minute", key_func=ip_and_email_key)
def verify_email(
    request: Request,
    req: schemas.VerifyEmailRequest,
    db: Session = Depends(get_db),
):
    """
    Vérifie un OTP. Réponse générique anti-énumération :
    ne révèle pas si l'email existe, est déjà vérifié, ou si c'est le code
    qui est mauvais. Un seul succès possible.
    """
    request.state.rl_email = req.email

    # Budget cumulatif 24h — persiste malgré /resend-otp
    check_daily_failure_budget(req.email)

    user = db.query(models.Utilisateur).filter(models.Utilisateur.email == req.email).first()

    # Tous les cas d'échec renvoient le même message générique
    if not user or user.est_verifie or user.otp_attempts >= OTP_MAX_ATTEMPTS:
        increment_daily_failures(req.email)
        raise HTTPException(status_code=400, detail=GENERIC_INVALID_CODE_MSG)

    if user.otp_expires_at and datetime.utcnow() > user.otp_expires_at:
        increment_daily_failures(req.email)
        raise HTTPException(status_code=400, detail=GENERIC_INVALID_CODE_MSG)

    if not verify_otp(req.code, user.code_verification):
        user.otp_attempts += 1
        db.commit()
        increment_daily_failures(req.email)
        raise HTTPException(status_code=400, detail=GENERIC_INVALID_CODE_MSG)

    user.est_verifie = True
    user.code_verification = None
    user.otp_expires_at = None
    user.otp_attempts = 0
    db.commit()
    reset_daily_failures(req.email)

    return {"message": "Email vérifié avec succès"}

@router.post("/login", response_model=schemas.Token)
@limiter.limit("10/minute")
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    # Hardcoded Admin Login
    if form_data.username == "admin@smartfind.com" and form_data.password == "admin_2026":
        # Cybersécurité : détection d'une connexion admin depuis une IP inhabituelle.
        # La baseline est initialisée à la première connexion (pas d'alerte).
        client_ip = request.client.host if request.client else ""
        ip_det = sec.check_admin_ip(client_ip)
        if ip_det.get("detected"):
            try:
                db.add(models.Alerte(
                    message=f"[SECURITY] admin_unusual_ip — {ip_det.get('details', {})}",
                    niveau="Critical",
                    source="Security",
                    id_objet=None,
                ))
                db.commit()
            except Exception as e:
                db.rollback()
                print(f"⚠️ Alerte admin_unusual_ip : {e}")
        access_token = auth.create_access_token(data={"sub": "admin@smartfind.com"})
        return {"access_token": access_token, "token_type": "bearer"}

    # Standard User Login
    user = db.query(models.Utilisateur).filter(models.Utilisateur.email == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Identifiants incorrects")

    if not user.est_verifie:
        raise HTTPException(
            status_code=403,
            detail="Email non vérifié. Consultez votre boîte mail pour le code de vérification."
        )

    access_token = auth.create_access_token(data={"sub": user.email})
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
        validate_password(user_update.password)
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


@router.delete("/users/me/history/{historique_id}")
def delete_history_item(
    historique_id: int,
    current_user: models.Utilisateur = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    item = (
        db.query(models.Historique)
        .filter(
            models.Historique.id_historique == historique_id,
            models.Historique.id_utilisateur == current_user.id_utilisateur,
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Entrée d'historique introuvable")
    db.delete(item)
    db.commit()
    return {"message": "Entrée supprimée"}


@router.get("/users/me/recommendations", response_model=List[schemas.ObjetResponse])
def get_recommendations(
    limit: int = 4,
    current_user: models.Utilisateur = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Top objets personnalisés : on agrège les 50 dernières requêtes de
    l'utilisateur et on compte combien de fois chaque objet matche
    (ILIKE sur nom_model / type_objet / nom_marque). Les plus fréquents
    sortent en tête. Zéro ML, aucun id_objet stocké en historique requis.
    """
    limit = max(1, min(limit, 12))

    if getattr(current_user, "id_utilisateur", 0) == 0:
        return []

    recent = (
        db.query(models.Historique.requete_search)
        .filter(
            models.Historique.id_utilisateur == current_user.id_utilisateur,
            models.Historique.requete_search.isnot(None),
            func.length(models.Historique.requete_search) > 0,
        )
        .order_by(models.Historique.date_his.desc())
        .limit(50)
        .all()
    )
    if not recent:
        return []

    tokens_seen = []
    for (q,) in recent:
        for tok in str(q).lower().split():
            tok = tok.strip()
            if len(tok) >= 3 and tok not in tokens_seen:
                tokens_seen.append(tok)
        if len(tokens_seen) >= 40:
            break
    if not tokens_seen:
        return []

    counts = Counter()
    for tok in tokens_seen:
        like = f"%{tok}%"
        matches = (
            db.query(models.Objet.id_objet)
            .filter(
                or_(
                    func.lower(models.Objet.nom_model).like(like),
                    func.lower(models.Objet.type_objet).like(like),
                    func.lower(models.Objet.nom_marque).like(like),
                )
            )
            .all()
        )
        for (oid,) in matches:
            counts[oid] += 1

    if not counts:
        return []

    top_ids = [oid for oid, _ in counts.most_common(limit)]
    objets = (
        db.query(models.Objet)
        .filter(models.Objet.id_objet.in_(top_ids))
        .all()
    )
    order = {oid: idx for idx, oid in enumerate(top_ids)}
    objets.sort(key=lambda o: order.get(o.id_objet, 999))
    return objets
