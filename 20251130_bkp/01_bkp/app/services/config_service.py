"""
NBCM V2.5 - Service Configuration
Gestion des paramètres système
"""
import json
from datetime import datetime

from app import db
from app.models.compliance import Configuration


def get_config(cle, defaut=None):
    """Récupère une valeur de configuration"""
    config = Configuration.query.filter_by(cle=cle).first()
    if config:
        try:
            return json.loads(config.valeur)
        except:
            return config.valeur
    return defaut


def set_config(cle, valeur, description=None, updated_by='system'):
    """Définit une valeur de configuration"""
    config = Configuration.query.filter_by(cle=cle).first()
    if not config:
        config = Configuration(cle=cle)
    
    if isinstance(valeur, (dict, list)):
        config.valeur = json.dumps(valeur)
    else:
        config.valeur = str(valeur)
    
    if description:
        config.description = description
    
    config.updated_at = datetime.now()
    config.updated_by = updated_by
    
    db.session.add(config)
    db.session.commit()
    return config


def delete_config(cle):
    """Supprime une configuration"""
    config = Configuration.query.filter_by(cle=cle).first()
    if config:
        db.session.delete(config)
        db.session.commit()
        return True
    return False


def get_all_configs():
    """Retourne toutes les configurations"""
    configs = Configuration.query.all()
    return {c.cle: c.get_value() for c in configs}


def init_default_configs():
    """Initialise les configurations par défaut"""
    defaults = {
        'retention_jours': (180, 'Durée de rétention des données en jours'),
        'auto_cleanup': (True, 'Nettoyage automatique activé'),
        'dedup_auto': ({'actif': True}, 'Auto-nettoyage des doublons'),
        'archive_config': ({'heure': 18, 'minute': 0, 'actif': True}, 'Configuration archivage'),
        'compliance_period_hours': (24, 'Période de conformité en heures'),
        'app_theme': ('default', 'Thème de l\'application'),
        'maintenance_mode': (False, 'Mode maintenance activé'),
    }
    
    for cle, (valeur, description) in defaults.items():
        if get_config(cle) is None:
            set_config(cle, valeur, description)
