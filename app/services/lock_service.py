"""
NBCM V2.5 - Service de Lock Redis
Gestion des verrous distribués pour éviter les exécutions simultanées
"""
import redis
from flask import current_app
from datetime import datetime


class LockService:
    """
    Service de gestion des locks Redis pour coordination multi-worker.
    """
    
    def __init__(self):
        self.redis_client = None
        self._init_redis()
    
    def _init_redis(self):
        """Initialise la connexion Redis."""
        try:
            redis_url = current_app.config.get('REDIS_URL', 'redis://:redis2025@localhost:6379/0')
            self.redis_client = redis.from_url(redis_url, decode_responses=True)
            
            # Test de connexion
            self.redis_client.ping()
            current_app.logger.info("[LOCK] ✅ Redis connecté pour les locks")
            
        except Exception as e:
            current_app.logger.warning(f"[LOCK] ⚠️ Redis non disponible: {e}")
            self.redis_client = None
    
    def acquire_lock(self, lock_key, ttl=60):
        """
        Essaie d'acquérir un lock.
        
        Args:
            lock_key: Nom du lock
            ttl: Durée de vie du lock en secondes (60s par défaut)
        
        Returns:
            bool: True si le lock est acquis, False sinon
        """
        if not self.redis_client:
            # Si Redis n'est pas disponible, on autorise (mode dégradé)
            current_app.logger.warning(f"[LOCK] ⚠️ Redis indisponible, lock '{lock_key}' autorisé en mode dégradé")
            return True
        
        try:
            # SET NX (Set if Not eXists) avec expiration
            lock_value = f"{datetime.now().isoformat()}"
            acquired = self.redis_client.set(
                f"lock:{lock_key}",
                lock_value,
                nx=True,  # Only set if key doesn't exist
                ex=ttl    # Expire after TTL seconds
            )
            
            if acquired:
                current_app.logger.debug(f"[LOCK] 🔒 Lock '{lock_key}' acquis (TTL: {ttl}s)")
            else:
                current_app.logger.debug(f"[LOCK] 🔒 Lock '{lock_key}' déjà détenu par un autre process")
            
            return acquired
            
        except Exception as e:
            current_app.logger.error(f"[LOCK] ❌ Erreur acquisition lock '{lock_key}': {e}")
            # En cas d'erreur, autoriser (mode dégradé)
            return True
    
    def release_lock(self, lock_key):
        """
        Libère un lock.
        
        Args:
            lock_key: Nom du lock à libérer
        """
        if not self.redis_client:
            return
        
        try:
            deleted = self.redis_client.delete(f"lock:{lock_key}")
            
            if deleted:
                current_app.logger.debug(f"[LOCK] 🔓 Lock '{lock_key}' libéré")
            else:
                current_app.logger.debug(f"[LOCK] 🔓 Lock '{lock_key}' n'existait pas (déjà expiré)")
                
        except Exception as e:
            current_app.logger.error(f"[LOCK] ❌ Erreur libération lock '{lock_key}': {e}")
    
    def check_lock(self, lock_key):
        """
        Vérifie si un lock existe.
        
        Args:
            lock_key: Nom du lock
            
        Returns:
            bool: True si le lock existe, False sinon
        """
        if not self.redis_client:
            return False
        
        try:
            exists = self.redis_client.exists(f"lock:{lock_key}")
            return bool(exists)
        except Exception as e:
            current_app.logger.error(f"[LOCK] ❌ Erreur vérification lock '{lock_key}': {e}")
            return False


# Singleton
_lock_service = None


def get_lock_service():
    """
    Retourne l'instance singleton du LockService.
    """
    global _lock_service
    
    if _lock_service is None:
        _lock_service = LockService()
    
    return _lock_service
