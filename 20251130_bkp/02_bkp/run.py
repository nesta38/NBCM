#!/usr/bin/env python3
"""
NBCM V2.5 - Point d'entrée
NetBackup Compliance Manager
"""
import os
from app import create_app, db
from app.models.user import create_default_admin
from app.services.config_service import init_default_configs
from app.services.scheduler_service import init_scheduler

# Créer l'application
app = create_app()

# Variable globale pour le temps de démarrage
from datetime import datetime
start_time = datetime.now()

# Exposer start_time pour le module admin
import app.routes.admin as admin_module
admin_module.start_time = start_time

def init_app():
    """Initialiser l'application au démarrage"""
    with app.app_context():
        # Créer les tables
        db.create_all()
        
        # Créer l'admin par défaut
        create_default_admin()
        
        # Initialiser les configurations par défaut
        init_default_configs()
        
        print("[INIT] Base de données initialisée")
        print("[INIT] Admin par défaut: admin / admin123")

# Initialiser au démarrage
init_app()

# Démarrer le scheduler
init_scheduler(app)

if __name__ == '__main__':
    # Mode développement
    app.run(host='0.0.0.0', port=5000, debug=True)
