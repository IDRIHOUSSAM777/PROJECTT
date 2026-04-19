"""
Rate limiter partagé (slowapi).

Par défaut, l'état est stocké en mémoire du process. Si REDIS_URL est défini,
le backend passe sur Redis — indispensable en prod multi-workers pour que la
limite soit effective cross-process.
"""
import os
from slowapi import Limiter
from slowapi.util import get_remote_address

REDIS_URL = os.getenv("REDIS_URL")

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=REDIS_URL if REDIS_URL else "memory://",
    default_limits=[],
)
