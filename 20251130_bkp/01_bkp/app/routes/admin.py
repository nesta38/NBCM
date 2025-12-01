"""
NBCM V2.5 - Routes Administration
Configuration système et maintenance
"""
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from sqlalchemy import text

from app import db
from app.models.cmdb import ReferentielCMDB
from app.models.jobs import JobAltaview, ImportHistory
from app.services.config_service import get_config, set_config
from app.services.scheduler_service import get_scheduler_status, reschedule_archive
from app.services.compliance_service import archiver_conformite_quotidienne
from app.services.import_service import supprimer_doublons_altaview
from app.services.external_import_service import fetch_imap_attachments, fetch_altaview_api
from app.services.email_service import send_test_email
from app.routes.auth import admin_required
from app import start_time

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/')
@admin_required
def index():
    """Page d'administration"""
    # Statut scheduler
    scheduler_status = get_scheduler_status()
    
    # Statut DB
    db_status = "OK"
    try:
        db.session.execute(text('SELECT 1'))
    except Exception as e:
        db_status = f"Erreur: {e}"
    
    # Dernier import
    last_import = ImportHistory.query.filter(
        ImportHistory.type_import.in_(['altaview', 'altaview_api'])
    ).order_by(ImportHistory.date_import.desc()).first()
    
    system_health = {
        'uptime': str(datetime.now() - start_time).split('.')[0],
        'scheduler': scheduler_status.get('running', False),
        'jobs': scheduler_status.get('jobs', []),
        'db': db_status,
        'last_imap': last_import
    }
    
    derniers_imports = ImportHistory.query.order_by(
        ImportHistory.date_import.desc()
    ).limit(20).all()
    
    return render_template(
        'admin/index.html',
        system_health=system_health,
        derniers_imports=derniers_imports
    )


@admin_bp.route('/config_email', methods=['POST'])
@admin_required
def config_email():
    """Configurer l'envoi email"""
    config = {
        'smtp_server': request.form.get('smtp_server'),
        'smtp_port': request.form.get('smtp_port', '587'),
        'smtp_user': request.form.get('smtp_user'),
        'smtp_password': request.form.get('smtp_password'),
        'email_from': request.form.get('email_from'),
        'email_to': request.form.get('email_to'),
        'actif': request.form.get('actif') == 'on'
    }
    set_config('email_rapport', config, 'Configuration Email', current_user.username)
    flash('Configuration email enregistrée.', 'success')
    return redirect(url_for('admin.index'))


@admin_bp.route('/test_email', methods=['POST'])
@admin_required
def test_email():
    """Test envoi email"""
    email_to = request.form.get('email_to')
    if email_to:
        if send_test_email(email_to.split(',')[0].strip()):
            flash('Email de test envoyé.', 'success')
        else:
            flash('Erreur envoi email de test.', 'danger')
    return redirect(url_for('admin.index'))


@admin_bp.route('/config_imap', methods=['POST'])
@admin_required
def config_imap():
    """Configurer l'import IMAP"""
    config = {
        'server': request.form.get('server'),
        'user': request.form.get('user'),
        'password': request.form.get('password'),
        'subject_filter': request.form.get('subject_filter', 'NetBackup'),
        'archive_folder': request.form.get('archive_folder', 'Archives_Altaview'),
        'check_interval': request.form.get('check_interval', '15'),
        'actif': request.form.get('actif') == 'on'
    }
    set_config('email_import', config, 'Configuration IMAP', current_user.username)
    flash('Configuration IMAP enregistrée.', 'success')
    return redirect(url_for('admin.index'))


@admin_bp.route('/test_imap', methods=['POST'])
@admin_required
def test_imap():
    """Test import IMAP"""
    fetch_imap_attachments(force=True)
    flash('Test IMAP lancé (voir logs).', 'info')
    return redirect(url_for('admin.index'))


@admin_bp.route('/config_api', methods=['POST'])
@admin_required
def config_api():
    """Configurer l'API Altaview"""
    config = {
        'url': request.form.get('url'),
        'token': request.form.get('token'),
        'actif': request.form.get('actif') == 'on'
    }
    set_config('altaview_api', config, 'Configuration API', current_user.username)
    flash('Configuration API enregistrée.', 'success')
    return redirect(url_for('admin.index'))


@admin_bp.route('/test_api_import', methods=['POST'])
@admin_required
def test_api():
    """Test import API"""
    if fetch_altaview_api():
        flash('Import API réussi.', 'success')
    else:
        flash('Erreur import API (voir logs).', 'warning')
    return redirect(url_for('admin.index'))


@admin_bp.route('/config_archive', methods=['POST'])
@admin_required
def config_archive():
    """Configurer l'archivage"""
    heure = int(request.form.get('heure', 18))
    minute = int(request.form.get('minute', 0))
    actif = request.form.get('actif') == 'on'
    
    config = {'heure': heure, 'minute': minute, 'actif': actif}
    set_config('archive_config', config, 'Configuration Archivage', current_user.username)
    
    reschedule_archive(heure, minute, actif)
    
    flash(f'Configuration archivage enregistrée ({heure}:{minute:02d}).', 'success')
    return redirect(url_for('admin.index'))


@admin_bp.route('/test_archive', methods=['POST'])
@admin_required
def test_archive():
    """Créer une archive manuelle"""
    result = archiver_conformite_quotidienne(force_now=True)
    
    if result.get('success'):
        flash(f"Archive créée: {result['periode']} - Taux: {result['taux_conformite']}%", 'success')
    elif result.get('skipped'):
        flash(f"Archive ignorée: {result['reason']}", 'info')
    else:
        flash(f"Erreur: {result.get('error', 'Inconnue')}", 'danger')
    
    return redirect(url_for('admin.index'))


@admin_bp.route('/nettoyer', methods=['POST'])
@admin_required
def nettoyer():
    """Nettoyer les anciens jobs"""
    from datetime import timedelta
    count = JobAltaview.query.filter(
        JobAltaview.backup_time < datetime.now() - timedelta(days=180)
    ).delete()
    db.session.commit()
    flash(f'{count} anciens jobs supprimés.', 'success')
    return redirect(url_for('admin.index'))


@admin_bp.route('/config_dedup', methods=['POST'])
@admin_required
def config_dedup():
    """Configurer l'auto-déduplication"""
    config = {'actif': request.form.get('actif') == 'on'}
    set_config('dedup_auto', config, 'Auto-nettoyage doublons', current_user.username)
    flash('Configuration auto-déduplication mise à jour.', 'success')
    return redirect(url_for('admin.index'))


@admin_bp.route('/supprimer_doublons', methods=['POST'])
@admin_required
def supprimer_doublons():
    """Supprimer les doublons manuellement"""
    result = supprimer_doublons_altaview(force=True)
    
    if 'error' in result:
        flash(f"Erreur: {result['error']}", 'danger')
    else:
        flash(f"Doublons supprimés: {result.get('supprimes', 0)}", 'success')
    
    return redirect(url_for('admin.index'))


@admin_bp.route('/purge_cmdb', methods=['POST'])
@admin_required
def purge_cmdb():
    """Purger complètement la CMDB"""
    if request.form.get('confirmation', '').strip().upper() == 'DELETE':
        count = ReferentielCMDB.query.count()
        ReferentielCMDB.query.delete()
        db.session.commit()
        
        ImportHistory(
            type_import='cmdb',
            filename='PURGE_ADMIN',
            nb_lignes=count,
            statut='success',
            message=f'Purge de {count} entrées CMDB',
            utilisateur=current_user.username
        ).save()
        
        flash(f'CMDB purgée: {count} entrées supprimées.', 'success')
    else:
        flash('Code de confirmation incorrect.', 'warning')
    
    return redirect(url_for('admin.index'))


@admin_bp.route('/purge_altaview', methods=['POST'])
@admin_required
def purge_altaview():
    """Purger complètement les jobs Altaview"""
    if request.form.get('confirmation', '').strip().upper() == 'DELETE':
        count = JobAltaview.query.count()
        JobAltaview.query.delete()
        db.session.commit()
        
        ImportHistory(
            type_import='altaview',
            filename='PURGE_ADMIN',
            nb_lignes=count,
            statut='success',
            message=f'Purge de {count} jobs Altaview',
            utilisateur=current_user.username
        ).save()
        
        flash(f'Jobs purgés: {count} entrées supprimées.', 'success')
    else:
        flash('Code de confirmation incorrect.', 'warning')
    
    return redirect(url_for('admin.index'))
