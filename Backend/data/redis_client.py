import redis
import os

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

def clear_search_cache():
    """
    Supprime toutes les clés de cache liées à la recherche.
    À appeler dès qu'un statut d'objet change.
    """
    try:
        keys = redis_client.keys("search:*")
        if keys:
            redis_client.delete(*keys)
            print(f"🧹 Cache de recherche vidé ({len(keys)} clés supprimées)")
        
        # Vider aussi le cache des catégories
        redis_client.delete("categories_list")
    except Exception as e:
        print(f"⚠️ Erreur lors du nettoyage du cache Redis: {str(e)}")
