"""
NBCM V3.0 - Application Factory
NetBackup Compliance Manager
"""
import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_caching import Cache
from flask_migrate import Migrate

from config import get_config

# Extensions
db = SQLAlchemy()
login_manager = LoginManager()
cache = Cache()
migrate = Migrate()

# Globals
start_time = datetime.now()


def create_app(config_class=None):
    """Factory pattern pour créer l'application Flask"""
    app = Flask(__name__, 
                template_folder='templates',
                static_folder='static')
    
    # Configuration
    if config_class is None:
        config_class = get_config()
    app.config.from_object(config_class)
    
    # Configuration Redis (cache)
    app.config['REDIS_URL'] = os.environ.get('REDIS_URL')
    
    # Configuration Backup Directory
    app.config['BACKUP_DIR'] = os.environ.get('BACKUP_DIR', 'backups')
    
    # Créer les dossiers nécessaires
    os.makedirs(app.config.get('UPLOAD_FOLDER', 'uploads'), exist_ok=True)
    os.makedirs(app.config.get('ALTAVIEW_AUTO_IMPORT_DIR', '/app/data/altaview_auto_import'), exist_ok=True)
    os.makedirs(os.path.join(app.config.get('ALTAVIEW_AUTO_IMPORT_DIR'), 'processed'), exist_ok=True)
    os.makedirs(app.config.get('LOG_DIR', '/app/data/logs'), exist_ok=True)
    os.makedirs(app.config.get('BACKUP_DIR', 'backups'), exist_ok=True)  # Nouveau : dossier backups
    
    # Initialiser les extensions
    db.init_app(app)
    login_manager.init_app(app)
    cache.init_app(app)
    migrate.init_app(app, db)
    
    # Configuration Login Manager
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Veuillez vous connecter pour accéder à cette page.'
    login_manager.login_message_category = 'warning'
    
    # Configurer le logging
    configure_logging(app)
    
    # Enregistrer les blueprints
    register_blueprints(app)
    
    # Enregistrer les context processors
    register_context_processors(app)
    
    # Enregistrer les filtres Jinja2
    register_template_filters(app)
    
    # Initialiser le scheduler
    if not app.config.get('TESTING'):
        from app.services.scheduler_service import init_scheduler
        init_scheduler(app)
    
    app.logger.info(f"NBCM V3.0 démarré en mode {os.getenv('FLASK_ENV', 'development')}")
    
    return app


def configure_logging(app):
    """Configure le système de logging professionnel"""
    log_dir = app.config.get('LOG_DIR', '/app/data/logs')
    log_file = os.path.join(log_dir, app.config.get('LOG_FILE', 'nbcm.log'))
    
    # Formatter
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s [%(module)s.%(funcName)s:%(lineno)d] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Handler fichier rotatif
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=app.config.get('LOG_MAX_BYTES', 10*1024*1024),
        backupCount=app.config.get('LOG_BACKUP_COUNT', 5),
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    
    # Handler console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.DEBUG if app.debug else logging.INFO)
    
    # Configurer le logger de l'app
    app.logger.handlers.clear()
    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)
    app.logger.setLevel(getattr(logging, app.config.get('LOG_LEVEL', 'INFO')))
    
    # Désactiver les logs werkzeug verbeux en production
    if not app.debug:
        logging.getLogger('werkzeug').setLevel(logging.WARNING)


def register_blueprints(app):
    """Enregistre tous les blueprints"""
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.cmdb import cmdb_bp
    from app.routes.altaview import altaview_bp
    from app.routes.rapport import rapport_bp
    from app.routes.archives import archives_bp
    from app.routes.admin import admin_bp
    from app.routes.recipients import recipients_bp
    from app.routes.api import api_bp
    from app.routes.backup import backup_bp  # NOUVEAU : Backup/Restore
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(cmdb_bp, url_prefix='/cmdb')
    app.register_blueprint(altaview_bp, url_prefix='/altaview')
    app.register_blueprint(rapport_bp, url_prefix='/rapport')
    app.register_blueprint(archives_bp, url_prefix='/archives')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(recipients_bp, url_prefix='/recipients')
    app.register_blueprint(api_bp, url_prefix='/api/v1')
    app.register_blueprint(backup_bp)  # NOUVEAU : Backup/Restore


def register_context_processors(app):
    """Enregistre les context processors globaux"""
    @app.context_processor
    def inject_globals():
        from app.services.config_service import get_config
        from app.services.translations import t, get_user_language
        return {
            'now': datetime.now,
            'get_config': get_config,
            'app_version': 'V3.0',  # MODIFIÉ : V2.5 → V3.0
            't': t,  # Translation function
            'user_lang': get_user_language  # Current user language
        }


def register_template_filters(app):
    """Enregistre les filtres Jinja2 personnalisés"""
    import json
    
    @app.template_filter('from_json')
    def from_json_filter(s):
        try:
            return json.loads(s) if s else []
        except:
            return []
    
    @app.template_filter('format_size')
    def format_size_filter(size_gb):
        if size_gb is None:
            return 'N/A'
        if size_gb < 1:
            return f"{size_gb * 1024:.1f} MB"
        return f"{size_gb:.2f} GB"
    
    @app.template_filter('time_ago')
    def time_ago_filter(dt):
        if not dt:
            return 'N/A'
        diff = datetime.now() - dt
        if diff.days > 0:
            return f"il y a {diff.days}j"
        hours = diff.seconds // 3600
        if hours > 0:
            return f"il y a {hours}h"
        minutes = (diff.seconds % 3600) // 60
        return f"il y a {minutes}min"
