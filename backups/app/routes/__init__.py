"""
NBCM V2.5 - Routes
Export de tous les blueprints
"""
from app.routes.auth import auth_bp, admin_required, operator_required
from app.routes.dashboard import dashboard_bp
from app.routes.cmdb import cmdb_bp
from app.routes.altaview import altaview_bp
from app.routes.rapport import rapport_bp
from app.routes.archives import archives_bp
from app.routes.admin import admin_bp
from app.routes.recipients import recipients_bp
from app.routes.api import api_bp

__all__ = [
    'auth_bp',
    'dashboard_bp', 
    'cmdb_bp',
    'altaview_bp',
    'rapport_bp',
    'archives_bp',
    'admin_bp',
    'recipients_bp',
    'api_bp',
    'admin_required',
    'operator_required'
]
