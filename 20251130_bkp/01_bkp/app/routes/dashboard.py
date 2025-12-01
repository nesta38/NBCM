"""
NBCM V2.5 - Routes Dashboard
Page principale avec KPIs et graphiques
"""
from datetime import datetime, timedelta
from flask import Blueprint, render_template, jsonify
from flask_login import login_required

from app.models.jobs import ImportHistory
from app.services.compliance_service import (
    calculer_conformite,
    get_historique_conformite,
    get_trend_data
)

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@login_required
def index():
    """Page d'accueil - Dashboard principal"""
    # Calculer la conformité
    conformite = calculer_conformite()
    
    # Statistiques
    stats = {
        'total_cmdb': conformite['total_cmdb'],
        'backup_enabled': conformite['total_backup_enabled'],
        'total_jobs': conformite['total_jobs'],
        'derniere_import_cmdb': ImportHistory.query.filter_by(
            type_import='cmdb'
        ).order_by(ImportHistory.date_import.desc()).first(),
        'derniere_import_altaview': ImportHistory.query.filter_by(
            type_import='altaview'
        ).order_by(ImportHistory.date_import.desc()).first()
    }
    
    # Historique 30 jours pour le graphique
    historique = get_historique_conformite(days=30)
    chart_labels = [h.date_calcul.strftime('%d/%m %H:%M') for h in historique]
    chart_values = [h.taux_conformite for h in historique]
    
    # Données de tendance pour les sparklines
    trend_data = get_trend_data(days=7)
    
    # Données pour la jauge ApexCharts
    gauge_data = {
        'value': conformite['taux_conformite'],
        'color': '#38ef7d' if conformite['taux_conformite'] >= 95 else (
            '#ffc107' if conformite['taux_conformite'] >= 90 else '#dc3545'
        )
    }
    
    return render_template(
        'dashboard/index.html',
        conformite=conformite,
        stats=stats,
        historique=historique,
        chart_labels=chart_labels,
        chart_values=chart_values,
        trend_data=trend_data,
        gauge_data=gauge_data
    )


@dashboard_bp.route('/api/check-import')
@login_required
def check_import():
    """API pour vérifier s'il y a eu un nouvel import"""
    from app.services.notification_service import get_last_import_notification
    
    notification = get_last_import_notification()
    
    if notification:
        return jsonify({
            'should_refresh': True,
            'import_type': notification.get('import_type'),
            'timestamp': notification.get('timestamp'),
            'stats': notification.get('stats', {})
        })
    
    return jsonify({'should_refresh': False})
