"""
Service de cache Redis
Permet de stocker temporairement des résultats de calculs coûteux
"""
import json
import redis
from flask import current_app
from functools import wraps

class CacheService:
    """Service de cache Redis"""
    
    def __init__(self):
        redis_url = current_app.config.get('REDIS_URL')
        
        if redis_url:
            try:
                self.redis = redis.from_url(redis_url, decode_responses=True)
                self.enabled = True
            except:
                self.redis = None
                self.enabled = False
        else:
            self.redis = None
            self.enabled = False
    
    def get(self, key):
        """Récupère une valeur du cache"""
        if not self.enabled:
            return None
        
        try:
            value = self.redis.get(key)
            return json.loads(value) if value else None
        except:
            return None
    
    def set(self, key, value, ttl=300):
        """Stocke une valeur dans le cache (TTL par défaut: 5 min)"""
        if not self.enabled:
            return False
        
        try:
            self.redis.setex(key, ttl, json.dumps(value, default=str))
            return True
        except:
            return False
    
    def delete(self, key):
        """Supprime une clé du cache"""
        if not self.enabled:
            return False
        
        try:
            self.redis.delete(key)
            return True
        except:
            return False
    
    def clear_pattern(self, pattern):
        """Supprime toutes les clés matchant un pattern"""
        if not self.enabled:
            return False
        
        try:
            keys = self.redis.keys(pattern)
            if keys:
                self.redis.delete(*keys)
            return True
        except:
            return False
    
    def invalidate_all(self):
        """Invalide tout le cache"""
        if not self.enabled:
            return False
        
        try:
            self.redis.flushdb()
            return True
        except:
            return False
    
    def is_enabled(self):
        """Vérifie si Redis est actif"""
        return self.enabled


def cached(key_prefix, ttl=300):
    """
    Décorateur pour cacher les résultats de fonction
    
    Usage:
        @cached('conformite', ttl=300)
        def calculer_conformite():
            # ... calculs lourds
            return result
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Construire la clé de cache
            args_str = ':'.join(str(arg) for arg in args)
            kwargs_str = ':'.join(f"{k}={v}" for k, v in sorted(kwargs.items()))
            cache_key = f"{key_prefix}:{args_str}:{kwargs_str}"
            
            # Tenter de récupérer du cache
            try:
                cache = CacheService()
                cached_result = cache.get(cache_key)
                
                if cached_result is not None:
                    return cached_result
            except:
                pass
            
            # Calculer et mettre en cache
            result = func(*args, **kwargs)
            
            try:
                cache = CacheService()
                cache.set(cache_key, result, ttl)
            except:
                pass
            
            return result
        return wrapper
    return decorator


def invalidate_cache_on_import():
    """Invalide le cache après un import"""
    try:
        cache = CacheService()
        if cache.is_enabled():
            # Invalider les caches de conformité et stats
            cache.clear_pattern('conformite:*')
            cache.clear_pattern('stats:*')
            cache.clear_pattern('dashboard:*')
            cache.clear_pattern('rapport:*')
            return True
    except:
        pass
    return False
