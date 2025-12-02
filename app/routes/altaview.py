"""
NBCM V2.5 - Routes Altaview
Gestion des jobs de backup
"""
import os
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, session
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from sqlalchemy import or_, and_

from app import db
from app.models.jobs import JobAltaview
from app.routes.auth import operator_required
from app.services.import_service import import_altaview_file

altaview_bp = Blueprint('altaview', __name__)


@altaview_bp.route('/')
@login_required
def list():
    """Liste des jobs Altaview avec filtres persistants"""
    # Récupérer les filtres depuis la session ou les paramètres GET
    if request.args.get('reset_filters'):
        session.pop('altaview_filters', None)
        return redirect(url_for('altaview.list'))
    
    # Initialiser les filtres depuis GET ou session
    filters = session.get('altaview_filters', {})
    
    # Mise à jour des filtres depuis les paramètres GET
    if request.args:
        filters['date_from'] = request.args.get('date_from', filters.get('date_from', ''))
        filters['date_to'] = request.args.get('date_to', filters.get('date_to', ''))
        filters['time_from'] = request.args.get('time_from', filters.get('time_from', ''))
        filters['time_to'] = request.args.get('time_to', filters.get('time_to', ''))
        filters['status'] = request.args.get('status', filters.get('status', 'all'))
        filters['policy'] = request.args.get('policy', filters.get('policy', 'all'))
        filters['search'] = request.args.get('search', filters.get('search', ''))
        filters['sort_by'] = request.args.get('sort_by', filters.get('sort_by', 'backup_time'))
        filters['sort_order'] = request.args.get('sort_order', filters.get('sort_order', 'desc'))
        session['altaview_filters'] = filters
    
    # Construire la requête de base
    query = JobAltaview.query
    
    # Appliquer les filtres
    if filters.get('date_from'):
        try:
            date_from = datetime.strptime(filters['date_from'], '%Y-%m-%d')
            # Ajouter l'heure si fournie
            if filters.get('time_from'):
                try:
                    time_parts = filters['time_from'].split(':')
                    date_from = date_from.replace(hour=int(time_parts[0]), minute=int(time_parts[1]))
                except (ValueError, IndexError):
                    pass
            query = query.filter(JobAltaview.backup_time >= date_from)
        except ValueError:
            pass
    
    if filters.get('date_to'):
        try:
            date_to = datetime.strptime(filters['date_to'], '%Y-%m-%d')
            # Ajouter l'heure si fournie, sinon fin de journée
            if filters.get('time_to'):
                try:
                    time_parts = filters['time_to'].split(':')
                    date_to = date_to.replace(hour=int(time_parts[0]), minute=int(time_parts[1]), second=59)
                except (ValueError, IndexError):
                    date_to = date_to.replace(hour=23, minute=59, second=59)
            else:
                date_to = date_to.replace(hour=23, minute=59, second=59)
            query = query.filter(JobAltaview.backup_time <= date_to)
        except ValueError:
            pass
    
    # Filtre status (support codes numériques ET textuels)
    if filters.get('status') and filters['status'] != 'all':
        if filters['status'] == 'success':
            # Statut 0 = Success (uniquement)
            query = query.filter(
                or_(
                    JobAltaview.status == '0',
                    JobAltaview.status.in_(['Success', 'Completed', 'OK'])
                )
            )
        elif filters['status'] == 'warning':
            # Statut 1 = Warning
            query = query.filter(
                or_(
                    JobAltaview.status == '1',
                    JobAltaview.status.in_(['Warning', 'Incomplete', 'Partial Success'])
                )
            )
        elif filters['status'] == 'error':
            # Statut >= 2 = Error (on filtre tous les codes sauf 0 et 1)
            # Pour les codes numériques, on utilise une approche simple
            query = query.filter(
                or_(
                    # Textes d'erreur
                    JobAltaview.status.in_(['Failed', 'Error', 'Failure', 'Fatal', 'Partial']),
                    # Codes numériques >= 2 (on exclut simplement 0 et 1)
                    and_(
                        JobAltaview.status.notin_(['0', '1', 'Success', 'Completed', 'OK', 
                                                   'Warning', 'Incomplete', 'Partial Success']),
                        JobAltaview.status.isnot(None)
                    )
                )
            )
    
    # Filtre policy
    if filters.get('policy') and filters['policy'] != 'all':
        query = query.filter(JobAltaview.policy_name == filters['policy'])
    
    # Filtre recherche (hostname)
    if filters.get('search'):
        search_term = f"%{filters['search']}%"
        query = query.filter(JobAltaview.hostname.ilike(search_term))
    
    # Appliquer le tri
    sort_by = filters.get('sort_by', 'backup_time')
    sort_order = filters.get('sort_order', 'desc')
    
    # Mapping des colonnes triables
    sort_columns = {
        'backup_time': JobAltaview.backup_time,
        'hostname': JobAltaview.hostname,
        'policy_name': JobAltaview.policy_name,
        'status': JobAltaview.status,
        'taille_gb': JobAltaview.taille_gb,
        'duree_minutes': JobAltaview.duree_minutes
    }
    
    if sort_by in sort_columns:
        sort_col = sort_columns[sort_by]
        if sort_order == 'asc':
            query = query.order_by(sort_col.asc())
        else:
            query = query.order_by(sort_col.desc())
    else:
        query = query.order_by(JobAltaview.backup_time.desc())
    
    # Récupérer les jobs filtrés
    jobs = query.limit(2000).all()
    
    # Récupérer la liste des policies pour le filtre
    policies = db.session.query(JobAltaview.policy_name).distinct().order_by(JobAltaview.policy_name).all()
    policies = [p[0] for p in policies if p[0]]
    
    # Statistiques
    stats = {
        'total': JobAltaview.query.count(),
        'filtered': len(jobs),
        'recent': JobAltaview.query.filter(
            JobAltaview.backup_time >= datetime.now() - timedelta(hours=24)
        ).count()
    }
    
    return render_template('altaview/list.html', 
                         jobs=jobs, 
                         stats=stats,
                         filters=filters,
                         policies=policies)


@altaview_bp.route('/import', methods=['GET', 'POST'])
@operator_required
def import_page():
    """Import manuel de fichier Altaview"""
    if request.method == 'POST':
        file = request.files.get('file')
        mode = request.form.get('mode', 'merge')
        
        if file:
            filename = secure_filename(file.filename)
            import_dir = current_app.config.get('ALTAVIEW_AUTO_IMPORT_DIR', '/app/data/altaview_auto_import')
            os.makedirs(import_dir, exist_ok=True)
            filepath = os.path.join(import_dir, filename)
            file.save(filepath)
            
            # Mode remplacement : supprimer les jobs des dernières 24h avant import
            if mode == 'replace':
                date_limite = datetime.now() - timedelta(hours=24)
                deleted = JobAltaview.query.filter(JobAltaview.backup_time >= date_limite).delete()
                db.session.commit()
                current_app.logger.info(f"Mode remplacement: {deleted} jobs supprimés")
            
            # Import immédiat
            try:
                success, stats = import_altaview_file(filepath, filename, current_user.username)
                
                if success:
                    msg = f"Import réussi: {stats.get('nb_ajoutes', 0)} ajoutés"
                    if stats.get('nb_mis_a_jour', 0) > 0:
                        msg += f", {stats['nb_mis_a_jour']} mis à jour"
                    flash(msg, 'success')
                else:
                    flash(f"Erreur import: {stats.get('error', 'Erreur inconnue')}", 'danger')
                
                # Déplacer vers processed
                processed_dir = os.path.join(import_dir, 'processed')
                os.makedirs(processed_dir, exist_ok=True)
                ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                new_path = os.path.join(processed_dir, f"{ts}_{filename}")
                os.rename(filepath, new_path)
                
            except Exception as e:
                current_app.logger.error(f"Erreur import: {e}")
                flash(f"Erreur: {e}", 'danger')
            
            return redirect(url_for('altaview.list'))
    
    return render_template('altaview/import.html')


@altaview_bp.route('/history')
@login_required
def import_history():
    """Historique des imports (IMAP, API, Manuels)"""
    from app.models.jobs import ImportHistory
    
    # Récupérer tous les imports (IMAP, API, manuels)
    imports = ImportHistory.query.filter(
        ImportHistory.type_import.in_(['altaview', 'altaview_api', 'imap'])
    ).order_by(ImportHistory.date_import.desc()).limit(100).all()
    
    return render_template('altaview/import_history.html', imports=imports)
