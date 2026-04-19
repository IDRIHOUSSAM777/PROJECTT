import json
import redis
import os
from datetime import datetime

# Configuration Redis
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))

# Instance globale
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    decode_responses=True
)

# Canal Pub/Sub pour la diffusion temps réel des changements de statut
CHANNEL_STATUTS = "channel:statuts"


def publish_status_change(id_objet: int, statut: str, source: str = "system", extra: dict | None = None):
    """
    Publie un événement de changement de statut sur le canal Redis Pub/Sub.
    Les WebSocket clients (admin dashboard, etc.) reçoivent ces messages en temps réel.
    """
    try:
        payload = {
            "id_objet": id_objet,
            "statut": statut,
            "source": source,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        if extra:
            payload.update(extra)
        redis_client.publish(CHANNEL_STATUTS, json.dumps(payload))
    except Exception as e:
        print(f"⚠️ Pub/Sub erreur publish_status_change: {str(e)}")


def publish_event(channel: str, payload: dict):
    """
    Publication générique sur un canal arbitraire (alertes, actions WoT, etc.).
    """
    try:
        redis_client.publish(channel, json.dumps(payload))
    except Exception as e:
        print(f"⚠️ Pub/Sub erreur publish_event ({channel}): {str(e)}")

def clear_search_cache():
    """
    Supprime toutes les clés de cache liées à la recherche.
    À appeler dès qu'un statut d'objet, une réservation ou l'inventaire change.
    Invalide aussi les statistiques BM25 (N, avgdl, doc_freq) et le vocabulaire NLP.
    """
    try:
        keys = redis_client.keys("search:*")
        if keys:
            redis_client.delete(*keys)
            print(f"🧹 Cache de recherche vidé ({len(keys)} clés supprimées)")

        # Stats BM25 (N, avgdl, doc_freq) — doivent refléter le corpus courant
        redis_client.delete("bm25:corpus_stats:v2")

        # Vocabulaire NLP (types/marques/salles/fonctionnalités)
        redis_client.delete("nlp_domain_vocabulary")

        # Catégories
        redis_client.delete("categories_list")
        
        # Semantic search embeddings
        redis_client.delete("semantic:embeddings:v1")
    except Exception as e:
        print(f"⚠️ Erreur lors du nettoyage du cache Redis: {str(e)}")
