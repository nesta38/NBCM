"""
NBCM V3.0 - Configuration
NetBackup Compliance Manager
"""
import os
from datetime import timedelta

class Config:
    """Configuration de base"""
    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production-abc123')
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:////app/data/db/netbackup_compliance.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
    
    # Upload
    UPLOAD_FOLDER = 'uploads'
    MAX_CONTENT_LENGTH = 32 * 1024 * 1024  # 32 MB
    
    # Directories
    ALTAVIEW_AUTO_IMPORT_DIR = os.getenv('ALTAVIEW_AUTO_IMPORT_DIR', '/app/data/altaview_auto_import')
    LOG_DIR = os.getenv('LOG_DIR', '/app/data/logs')
    BACKUP_DIR = os.getenv('BACKUP_DIR', 'backups')  # NOUVEAU : Dossier backups
    
    # Redis Cache (optionnel)
    REDIS_URL = os.getenv('REDIS_URL')  # NOUVEAU : Redis URL
    
    # Cache (SimpleCache par défaut - pas besoin de Redis)
    CACHE_TYPE = 'SimpleCache'
    CACHE_DEFAULT_TIMEOUT = 300
    
    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_SECURE = os.getenv('FLASK_ENV') == 'production'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = 'nbcm.log'
    LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
    LOG_BACKUP_COUNT = 5
    
    # API
    API_RATE_LIMIT = os.getenv('API_RATE_LIMIT', '100/hour')
    
    # Compliance
    DEFAULT_RETENTION_DAYS = 180
    DEFAULT_COMPLIANCE_PERIOD_HOURS = 24


class DevelopmentConfig(Config):
    """Configuration développement"""
    DEBUG = True
    CACHE_TYPE = 'simple'


class ProductionConfig(Config):
    """Configuration production"""
    DEBUG = False
    CACHE_TYPE = 'SimpleCache'  # SimpleCache par défaut, Redis optionnel
    SESSION_COOKIE_SECURE = True


class TestingConfig(Config):
    """Configuration tests"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    CACHE_TYPE = 'simple'
    WTF_CSRF_ENABLED = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}


def get_config():
    """Retourne la configuration selon l'environnement"""
    env = os.getenv('FLASK_ENV', 'development')
    return config.get(env, config['default'])
