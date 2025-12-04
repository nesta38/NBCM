"""
NBCM V2.5 - API REST v1
Endpoints pour intégrations externes
"""
from functools import wraps
from flask import Blueprint, jsonify, request, current_app

from app import db
from app.models.user import User
from app.models.cmdb import ReferentielCMDB
from app.models.jobs import JobAltaview, ImportHistory
from app.models.compliance import ArchiveConformite
from app.services.compliance_service import calculer_conformite, get_historique_conformite

api_bp = Blueprint('api', __name__)


def require_api_key(f):
    """Décorateur pour authentification API"""
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        
        if not api_key:
            return jsonify({'error': 'API key required'}), 401
        
        user = User.query.filter_by(api_key=api_key, is_active=True).first()
        
        if not user:
            return jsonify({'error': 'Invalid API key'}), 401
        
        # Ajouter l'utilisateur au contexte
        request.api_user = user
        return f(*args, **kwargs)
    
    return decorated


@api_bp.route('/health')
def health():
    """Health check (sans auth)"""
    return jsonify({
        'status': 'ok',
        'version': '2.5',
        'timestamp': current_app.config.get('now', lambda: None)()
    })


@api_bp.route('/compliance')
@require_api_key
def compliance():
    """Récupérer les données de conformité"""
    conformite = calculer_conformite()
    
    return jsonify({
        'status': 'success',
        'data': conformite
    })


@api_bp.route('/compliance/history')
@require_api_key
def compliance_history():
    """Historique de conformité"""
    days = request.args.get('days', 30, type=int)
    historique = get_historique_conformite(days=days)
    
    return jsonify({
        'status': 'success',
        'data': [h.to_dict() for h in historique],
        'meta': {
            'days': days,
            'count': len(historique)
        }
    })


@api_bp.route('/servers')
@require_api_key
def servers():
    """Liste des serveurs CMDB"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    backup_enabled = request.args.get('backup_enabled')
    search = request.args.get('search', '')
    
    query = ReferentielCMDB.query
    
    if backup_enabled is not None:
        query = query.filter_by(backup_enabled=backup_enabled.lower() == 'true')
    
    if search:
        query = query.filter(ReferentielCMDB.hostname.ilike(f'%{search}%'))
    
    pagination = query.order_by(ReferentielCMDB.hostname).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'status': 'success',
        'data': [s.to_dict() for s in pagination.items],
        'meta': {
            'page': page,
            'per_page': per_page,
            'total': pagination.total,
            'pages': pagination.pages
        }
    })


@api_bp.route('/servers/<int:id>')
@require_api_key
def server_detail(id):
    """Détail d'un serveur"""
    server = ReferentielCMDB.query.get_or_404(id)
    return jsonify({
        'status': 'success',
        'data': server.to_dict()
    })


@api_bp.route('/jobs')
@require_api_key
def jobs():
    """Liste des jobs récents"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)
    hostname = request.args.get('hostname')
    hours = request.args.get('hours', 24, type=int)
    
    from datetime import datetime, timedelta
    query = JobAltaview.query.filter(
        JobAltaview.backup_time >= datetime.now() - timedelta(hours=hours)
    )
    
    if hostname:
        query = query.filter(JobAltaview.hostname.ilike(f'%{hostname}%'))
    
    pagination = query.order_by(JobAltaview.backup_time.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'status': 'success',
        'data': [j.to_dict() for j in pagination.items],
        'meta': {
            'page': page,
            'per_page': per_page,
            'total': pagination.total,
            'pages': pagination.pages,
            'hours': hours
        }
    })


@api_bp.route('/jobs', methods=['POST'])
@require_api_key
def create_jobs():
    """Importer des jobs via API"""
    if not request.api_user.is_operator():
        return jsonify({'error': 'Operator role required'}), 403
    
    data = request.get_json()
    
    if not data or not isinstance(data, list):
        return jsonify({'error': 'Expected JSON array of jobs'}), 400
    
    from app.services.compliance_service import normalize_hostname
    from datetime import datetime
    
    created = 0
    errors = []
    
    for i, job_data in enumerate(data):
        try:
            hostname = job_data.get('hostname')
            backup_time = job_data.get('backup_time')
            
            if not hostname or not backup_time:
                errors.append(f"Job {i}: hostname and backup_time required")
                continue
            
            # Parser la date
            if isinstance(backup_time, str):
                backup_time = datetime.fromisoformat(backup_time.replace('Z', ''))
            
            job = JobAltaview(
                hostname=normalize_hostname(hostname),
                backup_time=backup_time,
                job_id=job_data.get('job_id'),
                policy_name=job_data.get('policy_name'),
                schedule_name=job_data.get('schedule_name'),
                status=job_data.get('status', 'UNKNOWN'),
                taille_gb=job_data.get('taille_gb', 0),
                duree_minutes=job_data.get('duree_minutes', 0)
            )
            db.session.add(job)
            created += 1
            
        except Exception as e:
            errors.append(f"Job {i}: {str(e)}")
    
    db.session.commit()
    
    # Log import
    ImportHistory(
        type_import='api',
        filename='API_POST',
        nb_lignes=created,
        statut='success' if not errors else 'partial',
        message=f'{created} created, {len(errors)} errors',
        utilisateur=request.api_user.username
    ).save()
    
    return jsonify({
        'status': 'success',
        'created': created,
        'errors': errors if errors else None
    }), 201 if created > 0 else 400


@api_bp.route('/archives')
@require_api_key
def archives():
    """Liste des archives"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    pagination = ArchiveConformite.query.order_by(
        ArchiveConformite.date_archivage.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'status': 'success',
        'data': [a.to_dict() for a in pagination.items],
        'meta': {
            'page': page,
            'per_page': per_page,
            'total': pagination.total,
            'pages': pagination.pages
        }
    })


@api_bp.route('/imports')
@require_api_key
def imports():
    """Historique des imports"""
    limit = request.args.get('limit', 50, type=int)
    type_import = request.args.get('type')
    
    query = ImportHistory.query
    
    if type_import:
        query = query.filter_by(type_import=type_import)
    
    imports_list = query.order_by(
        ImportHistory.date_import.desc()
    ).limit(limit).all()
    
    return jsonify({
        'status': 'success',
        'data': [i.to_dict() for i in imports_list]
    })


# Gestion des erreurs API
@api_bp.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Resource not found'}), 404


@api_bp.errorhandler(500)
def server_error(e):
    return jsonify({'error': 'Internal server error'}), 500
