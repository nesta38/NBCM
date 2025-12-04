"""
Service de signalisation pour recharger le scheduler dynamiquement
Utilise Redis pub/sub pour communication inter-processus
"""
import logging
import redis
import threading
from flask import current_app

logger = logging.getLogger(__name__)

class SchedulerReloadService:
    """Service pour signaler au scheduler de recharger ses jobs"""
    
    def __init__(self):
        self.redis_client = None
        self.pubsub = None
        self.listener_thread = None
        self.app = None  # Stocker l'app pour le contexte
        self._initialize_redis()
    
    def _initialize_redis(self):
        """Initialise la connexion Redis"""
        try:
            redis_url = current_app.config.get('REDIS_URL')
            if redis_url:
                self.redis_client = redis.from_url(redis_url, decode_responses=True)
                # Test de connexion
                self.redis_client.ping()
                logger.info("Redis connecté pour scheduler reload service")
            else:
                logger.warning("Redis non configuré - reload scheduler désactivé")
        except Exception as e:
            logger.warning(f"Redis non disponible pour scheduler reload: {e}")
            self.redis_client = None
    
    def signal_reload_backup_schedule(self, backup_type, frequency):
        """
        Envoie un signal pour recharger un backup schedule spécifique
        
        Args:
            backup_type: 'db' ou 'fs'
            frequency: 'daily', 'weekly', ou 'monthly'
        """
        if not self.redis_client:
            logger.warning("Redis non disponible - signal reload ignoré")
            return False
        
        try:
            channel = 'scheduler:reload'
            message = f'backup:{backup_type}:{frequency}'
            
            self.redis_client.publish(channel, message)
            logger.info(f"Signal reload envoyé: {message}")
            return True
            
        except Exception as e:
            logger.error(f"Erreur envoi signal reload: {e}")
            return False
    
    def signal_reload_all_backups(self):
        """Envoie un signal pour recharger TOUS les backup schedules"""
        if not self.redis_client:
            logger.warning("Redis non disponible - signal reload ignoré")
            return False
        
        try:
            channel = 'scheduler:reload'
            message = 'backup:all'
            
            self.redis_client.publish(channel, message)
            logger.info("Signal reload ALL backups envoyé")
            return True
            
        except Exception as e:
            logger.error(f"Erreur envoi signal reload all: {e}")
            return False
    
    def start_listener(self, scheduler_service, app):
        """
        Démarre un thread qui écoute les signaux Redis
        
        Args:
            scheduler_service: Instance du scheduler service avec méthode reload_backup_schedule
            app: Instance Flask app pour le contexte
        """
        if not self.redis_client:
            logger.warning("Redis non disponible - listener non démarré")
            return
        
        # Stocker l'app pour le contexte dans le thread
        self.app = app
        
        try:
            self.pubsub = self.redis_client.pubsub()
            self.pubsub.subscribe('scheduler:reload')
            
            def _listen():
                logger.info("Listener scheduler reload démarré")
                
                for message in self.pubsub.listen():
                    if message['type'] == 'message':
                        data = message['data']
                        logger.info(f"Signal reçu: {data}")
                        
                        # 🔥 IMPORTANT: Utiliser le contexte Flask dans le thread
                        with self.app.app_context():
                            try:
                                if data.startswith('backup:'):
                                    parts = data.split(':')
                                    
                                    if len(parts) == 2 and parts[1] == 'all':
                                        # Recharger tous les backups
                                        logger.info("Rechargement de TOUS les backup schedules")
                                        scheduler_service.reload_all_backup_schedules()
                                        
                                    elif len(parts) == 3:
                                        # Recharger un backup spécifique
                                        backup_type = parts[1]
                                        frequency = parts[2]
                                        logger.info(f"Rechargement backup {backup_type} {frequency}")
                                        scheduler_service.reload_backup_schedule(backup_type, frequency)
                            
                            except Exception as e:
                                logger.error(f"Erreur traitement signal: {e}", exc_info=True)
            
            # Démarrer le thread d'écoute
            self.listener_thread = threading.Thread(target=_listen, daemon=True)
            self.listener_thread.start()
            
            logger.info("Thread listener scheduler reload démarré")
            
        except Exception as e:
            logger.error(f"Erreur démarrage listener: {e}")
    
    def stop_listener(self):
        """Arrête le listener proprement"""
        if self.pubsub:
            try:
                self.pubsub.unsubscribe('scheduler:reload')
                self.pubsub.close()
                logger.info("Listener scheduler reload arrêté")
            except Exception as e:
                logger.error(f"Erreur arrêt listener: {e}")


# Instance globale
_reload_service = None

def get_reload_service():
    """Récupère ou crée l'instance du service de reload"""
    global _reload_service
    if _reload_service is None:
        _reload_service = SchedulerReloadService()
    return _reload_service
