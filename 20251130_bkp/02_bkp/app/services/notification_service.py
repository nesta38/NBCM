"""
NBCM V2.5 - Service de Notifications
Système de notification pour le refresh automatique des pages
"""
import os
import json
from datetime import datetime
from flask import current_app


def get_notification_file():
    """Retourne le chemin du fichier de notification"""
    data_dir = current_app.config.get('DATA_DIR', '/app/data')
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, 'import_notification.json')


def notify_import_completed(import_type='altaview', stats=None):
    """
    Notifie qu'un import a été complété.
    Crée/met à jour un fichier de notification que les pages peuvent vérifier.
    
    Args:
        import_type: Type d'import (altaview, cmdb, etc.)
        stats: Statistiques de l'import
    """
    try:
        notification = {
            'timestamp': datetime.now().isoformat(),
            'import_type': import_type,
            'stats': stats or {},
            'should_refresh': True
        }
        
        notification_file = get_notification_file()
        with open(notification_file, 'w') as f:
            json.dump(notification, f)
        
        current_app.logger.info(f"Notification d'import créée: {import_type}")
        
    except Exception as e:
        current_app.logger.error(f"Erreur création notification: {e}")


def get_last_import_notification():
    """
    Récupère la dernière notification d'import.
    
    Returns:
        dict: Notification ou None si pas de notification
    """
    try:
        notification_file = get_notification_file()
        
        if not os.path.exists(notification_file):
            return None
        
        with open(notification_file, 'r') as f:
            notification = json.load(f)
        
        # Vérifier que la notification n'est pas trop ancienne (> 5 minutes)
        from datetime import timedelta
        timestamp = datetime.fromisoformat(notification['timestamp'])
        if datetime.now() - timestamp > timedelta(minutes=5):
            return None
        
        return notification
        
    except Exception as e:
        current_app.logger.error(f"Erreur lecture notification: {e}")
        return None


def clear_import_notification():
    """Efface la notification d'import"""
    try:
        notification_file = get_notification_file()
        if os.path.exists(notification_file):
            os.remove(notification_file)
    except Exception as e:
        current_app.logger.error(f"Erreur suppression notification: {e}")
