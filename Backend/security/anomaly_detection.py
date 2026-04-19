"""
Détection d'anomalies comportementales + équipements illicites.

Règles simples, impact sécurité fort :

  1. MAC conflict          : un IP connu se met à présenter une MAC différente
  2. Subnet interdit       : un heartbeat arrive d'une IP hors whitelist
  3. Heartbeat rate        : > N heartbeats par MAC dans une fenêtre glissante
  4. Status flapping       : un objet change de statut > N fois en M secondes
  5. Admin IP inhabituelle : connexion admin depuis une IP jamais vue

Toutes les règles s'appuient sur Redis (compteurs TTL / Sets) pour être
cross-workers et évitent toute allocation persistante côté Postgres.
"""
from __future__ import annotations

import ipaddress
import os
import time
from typing import Iterable, Optional

from data.redis_client import redis_client

# ----------------------------------------------------------------------------
# Configuration — surchargeable via .env
# ----------------------------------------------------------------------------
def _parse_subnets(raw: str) -> list:
    nets = []
    for item in (raw or "").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            nets.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            print(f"⚠️ ALLOWED_SUBNETS : réseau invalide ignoré : {item}")
    return nets


ALLOWED_SUBNETS = _parse_subnets(
    os.getenv("ALLOWED_SUBNETS", "127.0.0.0/8,10.0.0.0/8,192.168.0.0/16,172.16.0.0/12")
)

HEARTBEAT_RATE_WINDOW = int(os.getenv("HEARTBEAT_RATE_WINDOW", "60"))      # secondes
HEARTBEAT_RATE_MAX = int(os.getenv("HEARTBEAT_RATE_MAX", "30"))            # max par fenêtre

STATUS_FLAP_WINDOW = int(os.getenv("STATUS_FLAP_WINDOW", "10"))            # secondes
STATUS_FLAP_MAX = int(os.getenv("STATUS_FLAP_MAX", "10"))                  # max transitions

ADMIN_KNOWN_IPS_KEY = "security:admin:known_ips"


def _is_ip_in_allowed_subnet(ip: str) -> bool:
    if not ip:
        return False
    if not ALLOWED_SUBNETS:
        # whitelist vide = tout autorisé (ne pas bloquer par erreur)
        return True
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in ALLOWED_SUBNETS)


# ----------------------------------------------------------------------------
# 1. MAC ↔ IP conflict (rogue device)
# ----------------------------------------------------------------------------
def check_mac_conflict(ip: str, mac: str) -> dict:
    """Si une IP connue présente soudainement une MAC différente, c'est un
    indicateur fort d'usurpation ARP / rogue device sur le réseau."""
    if not ip or not mac:
        return {"detected": False}
    key = f"security:ip_mac:{ip}"
    try:
        previous = redis_client.get(key)
    except Exception:
        return {"detected": False}

    if isinstance(previous, bytes):
        previous = previous.decode("utf-8", "ignore")

    try:
        # garder 7 jours : le temps de garder une trace sans polluer Redis
        redis_client.setex(key, 7 * 24 * 3600, mac)
    except Exception:
        pass

    if previous and previous.lower() != mac.lower():
        return {
            "detected": True,
            "reason": "mac_conflict",
            "details": {"ip": ip, "previous_mac": previous, "current_mac": mac},
        }
    return {"detected": False}


# ----------------------------------------------------------------------------
# 2. Subnet whitelist
# ----------------------------------------------------------------------------
def check_subnet_allowed(ip: str) -> dict:
    if not ip:
        return {"detected": False}
    if _is_ip_in_allowed_subnet(ip):
        return {"detected": False}
    return {
        "detected": True,
        "reason": "unauthorized_subnet",
        "details": {"ip": ip, "allowed": [str(n) for n in ALLOWED_SUBNETS]},
    }


# ----------------------------------------------------------------------------
# 3. Heartbeat rate (DoS / capteur qui spamme)
# ----------------------------------------------------------------------------
def check_heartbeat_rate(mac: str) -> dict:
    if not mac:
        return {"detected": False}
    key = f"security:hb_rate:{mac}"
    try:
        count = redis_client.incr(key)
        if count == 1:
            redis_client.expire(key, HEARTBEAT_RATE_WINDOW)
    except Exception:
        return {"detected": False}

    if count > HEARTBEAT_RATE_MAX:
        return {
            "detected": True,
            "reason": "heartbeat_rate_exceeded",
            "details": {
                "mac": mac,
                "count": int(count),
                "window_seconds": HEARTBEAT_RATE_WINDOW,
                "threshold": HEARTBEAT_RATE_MAX,
            },
        }
    return {"detected": False}


# ----------------------------------------------------------------------------
# 4. Status flapping
# ----------------------------------------------------------------------------
def check_status_flapping(id_objet: int, new_status: str, old_status: Optional[str]) -> dict:
    if new_status == old_status or id_objet is None:
        return {"detected": False}
    key = f"security:flap:{id_objet}"
    try:
        count = redis_client.incr(key)
        if count == 1:
            redis_client.expire(key, STATUS_FLAP_WINDOW)
    except Exception:
        return {"detected": False}

    if count > STATUS_FLAP_MAX:
        return {
            "detected": True,
            "reason": "status_flapping",
            "details": {
                "id_objet": id_objet,
                "transitions": int(count),
                "window_seconds": STATUS_FLAP_WINDOW,
                "threshold": STATUS_FLAP_MAX,
            },
        }
    return {"detected": False}


# ----------------------------------------------------------------------------
# 5. Admin IP inhabituelle
# ----------------------------------------------------------------------------
def check_admin_ip(ip: str) -> dict:
    """Retourne detected=True la première fois qu'un admin se connecte
    depuis une IP jamais vue. L'IP est ensuite mémorisée."""
    if not ip:
        return {"detected": False}
    try:
        is_new = redis_client.sadd(ADMIN_KNOWN_IPS_KEY, ip) == 1
    except Exception:
        return {"detected": False}

    if not is_new:
        return {"detected": False}

    try:
        total = redis_client.scard(ADMIN_KNOWN_IPS_KEY) or 0
    except Exception:
        total = 0

    # Première IP jamais vue → pas d'alerte, on initialise la baseline.
    if total <= 1:
        return {"detected": False}

    return {
        "detected": True,
        "reason": "admin_unusual_ip",
        "details": {"ip": ip, "known_ip_count": int(total)},
    }
