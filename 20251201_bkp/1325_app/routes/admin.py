"""
NBCM V3.0 - Routes Administration
Configuration système et maintenance - Architecture multi-pages
"""
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import current_user
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

admin_bp = Blueprint('admin', __name__)

# Variable pour suivre le temps de démarrage
start_time = None


# ============================================================================
# DIAGNOSTIC & MONITORING
# ============================================================================

@admin_bp.route('/scheduler/status')
@admin_required
def scheduler_status():
    """Statut détaillé du scheduler"""
    scheduler_status = get_scheduler_status()
    
    return render_template('admin/scheduler_status.html', 
                         scheduler_status=scheduler_status)


@admin_bp.route('/scheduler/reload', methods=['POST'])
@admin_required
def scheduler_reload():
    """Force le rechargement du scheduler (redémarrage requis)"""
    flash('⚠️ Pour recharger le scheduler, redémarrez l\'application : docker-compose restart nbcm', 'warning')
    return redirect(request.referrer or url_for('admin.index'))


# ============================================================================
# SMTP - Configuration et Planification
# ============================================================================

@admin_bp.route('/smtp')
@admin_required
def smtp():
    """Configuration SMTP"""
    email_config = get_config('email_rapport', {})
    return render_template('admin/smtp.html', email_config=email_config)


@admin_bp.route('/smtp/schedule')
@admin_required
def smtp_schedule():
    """Planification envoi emails vers destinataires"""
    email_config = get_config('email_rapport', {})
    scheduler_status = get_scheduler_status()
    
    return render_template(
        'admin/smtp_schedule.html',
        email_config=email_config,
        scheduler_status=scheduler_status
    )


@admin_bp.route('/smtp/config', methods=['POST'])
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
    return redirect(url_for('admin.smtp'))


@admin_bp.route('/smtp/test', methods=['POST'])
@admin_required
def test_email():
    """Test envoi email"""
    email_to = request.form.get('email_to')
    if email_to:
        if send_test_email(email_to.split(',')[0].strip()):
            flash('Email de test envoyé.', 'success')
        else:
            flash('Erreur envoi email de test.', 'danger')
    return redirect(url_for('admin.smtp'))


# ============================================================================
# IMAP - Configuration et Historique
# ============================================================================

@admin_bp.route('/imap')
@admin_required
def imap():
    """Configuration IMAP"""
    imap_config = get_config('email_import', {})
    return render_template('admin/imap.html', imap_config=imap_config)


@admin_bp.route('/imap/history')
@admin_required
def imap_history():
    """Historique des imports IMAP"""
    # Récupérer les imports IMAP/Altaview
    imports = ImportHistory.query.filter(
        ImportHistory.type_import.in_(['altaview', 'altaview_api', 'imap'])
    ).order_by(ImportHistory.date_import.desc()).limit(100).all()
    
    return render_template('admin/imap_history.html', imports=imports)


@admin_bp.route('/imap/config', methods=['POST'])
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
    return redirect(url_for('admin.imap'))


@admin_bp.route('/imap/test', methods=['POST'])
@admin_required
def test_imap():
    """Test import IMAP"""
    fetch_imap_attachments(force=True)
    flash('Test IMAP lancé (voir logs).', 'info')
    return redirect(url_for('admin.imap'))


# ============================================================================
# API Altaview - Configuration
# ============================================================================

@admin_bp.route('/api')
@admin_required
def api():
    """Configuration API Altaview"""
    api_config = get_config('altaview_api', {})
    return render_template('admin/api.html', api_config=api_config)


@admin_bp.route('/api/config', methods=['POST'])
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
    return redirect(url_for('admin.api'))


@admin_bp.route('/api/test', methods=['POST'])
@admin_required
def test_api():
    """Test import API"""
    if fetch_altaview_api():
        flash('Import API réussi.', 'success')
    else:
        flash('Erreur import API (voir logs).', 'warning')
    return redirect(url_for('admin.api'))


# ============================================================================
# MAINTENANCE DB - Purges et nettoyage base de données
# ============================================================================

def _get_db_stats():
    """Helper pour récupérer les statistiques DB"""
    return {
        'cmdb_count': ReferentielCMDB.query.count(),
        'jobs_count': JobAltaview.query.count(),
        'jobs_old_count': JobAltaview.query.filter(
            JobAltaview.backup_time < datetime.now() - timedelta(days=180)
        ).count(),
        'dedup_active': get_config('dedup_auto', {}).get('actif', False)
    }

@admin_bp.route('/maintenance/db')
@admin_required
def maintenance_db():
    """Vue d'ensemble maintenance DB"""
    return render_template('admin/maintenance_db_index.html', stats=_get_db_stats())

@admin_bp.route('/maintenance/db/purge-cmdb')
@admin_required
def maintenance_db_purge_cmdb():
    """Page purge CMDB"""
    return render_template('admin/maintenance_db_purge_cmdb.html', stats=_get_db_stats())

@admin_bp.route('/maintenance/db/purge-jobs')
@admin_required
def maintenance_db_purge_jobs():
    """Page purge Jobs"""
    return render_template('admin/maintenance_db_purge_jobs.html', stats=_get_db_stats())

@admin_bp.route('/maintenance/db/cleanup-old')
@admin_required
def maintenance_db_cleanup_old():
    """Page nettoyage jobs anciens"""
    return render_template('admin/maintenance_db_cleanup_old.html', stats=_get_db_stats())

@admin_bp.route('/maintenance/db/deduplication')
@admin_required
def maintenance_db_deduplication():
    """Page déduplication"""
    return render_template('admin/maintenance_db_deduplication.html', stats=_get_db_stats())


@admin_bp.route('/maintenance/db/purge_cmdb', methods=['POST'])
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
    
    return redirect(url_for('admin.maintenance_db_purge_cmdb'))


@admin_bp.route('/maintenance/db/purge_jobs', methods=['POST'])
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
    
    return redirect(url_for('admin.maintenance_db_purge_jobs'))


@admin_bp.route('/maintenance/db/cleanup-old/execute', methods=['POST'])
@admin_required
def cleanup_old_jobs():
    """Nettoyer les anciens jobs"""
    count = JobAltaview.query.filter(
        JobAltaview.backup_time < datetime.now() - timedelta(days=180)
    ).delete()
    db.session.commit()
    flash(f'{count} anciens jobs supprimés.', 'success')
    return redirect(url_for('admin.maintenance_db_cleanup_old'))


@admin_bp.route('/maintenance/db/dedup/config', methods=['POST'])
@admin_required
def config_dedup():
    """Configurer l'auto-déduplication"""
    config = {'actif': request.form.get('actif') == 'on'}
    set_config('dedup_auto', config, 'Auto-nettoyage doublons', current_user.username)
    flash('Configuration auto-déduplication mise à jour.', 'success')
    return redirect(url_for('admin.maintenance_db'))


@admin_bp.route('/maintenance/db/dedup/run', methods=['POST'])
@admin_required
def supprimer_doublons():
    """Supprimer les doublons manuellement"""
    result = supprimer_doublons_altaview(force=True)
    
    if 'error' in result:
        flash(f"Erreur: {result['error']}", 'danger')
    else:
        flash(f"Doublons supprimés: {result.get('supprimes', 0)}", 'success')
    
    return redirect(url_for('admin.maintenance_db_deduplication'))


# ============================================================================
# MAINTENANCE FS - Nettoyage système de fichiers
# ============================================================================

@admin_bp.route('/maintenance/fs')
@admin_required
def maintenance_fs():
    """Maintenance système de fichiers"""
    from app.services.cleanup_service import cleanup_service
    stats = cleanup_service.get_directory_stats()
    
    return render_template('admin/maintenance_fs.html', stats=stats)


@admin_bp.route('/maintenance/fs/cleanup', methods=['POST'])
@admin_required
def cleanup_now():
    """Déclencher le nettoyage manuellement"""
    from app.services.cleanup_service import cleanup_service
    
    result = cleanup_service.cleanup_old_files()
    
    if result['status'] == 'success':
        if result['deleted'] > 0:
            flash(
                f"Nettoyage effectué : {result['deleted']} fichiers supprimés "
                f"({result['size_freed_mb']} MB libérés)",
                'success'
            )
        else:
            flash('Nettoyage effectué : Aucun fichier à supprimer', 'info')
    else:
        flash(f"Erreur : {result.get('message', 'Erreur inconnue')}", 'danger')
    
    return redirect(url_for('admin.maintenance_fs'))


@admin_bp.route('/maintenance/fs/cleanup/stats', methods=['GET'])
@admin_required
def cleanup_stats():
    """Statistiques du répertoire processed/ (API JSON)"""
    from app.services.cleanup_service import cleanup_service
    stats = cleanup_service.get_directory_stats()
    return jsonify(stats)


# ============================================================================
# ARCHIVES - Planification archivage
# ============================================================================

@admin_bp.route('/archive/schedule')
@admin_required
def archive_schedule():
    """Planification archivage automatique"""
    arch_config = get_config('archive_config', {'heure': 18, 'minute': 0, 'actif': True})
    scheduler_status = get_scheduler_status()
    
    return render_template(
        'admin/archive_schedule.html',
        arch_config=arch_config,
        scheduler_status=scheduler_status
    )


@admin_bp.route('/archive/config', methods=['POST'])
@admin_required
def config_archive():
    """Configurer l'archivage"""
    heure = int(request.form.get('heure', 18))
    minute = int(request.form.get('minute', 0))
    actif = request.form.get('actif') == 'on'
    
    config = {'heure': heure, 'minute': minute, 'actif': actif}
    set_config('archive_config', config, 'Configuration Archivage', current_user.username)
    
    reschedule_archive(heure, minute, actif)
    
    flash(f'⚠️ Configuration archivage enregistrée ({heure}:{minute:02d}). Redémarrez l\'application pour appliquer : docker-compose restart nbcm', 'warning')
    return redirect(url_for('admin.archive_schedule'))


@admin_bp.route('/archive/test', methods=['POST'])
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
    
    return redirect(url_for('admin.archive_schedule'))


# ============================================================================
# PAGE D'ACCUEIL ADMIN
# ============================================================================

@admin_bp.route('/')
@admin_required
def index():
    """Page d'accueil admin avec statut système"""
    global start_time
    
    # Informations système
    system_info = {
        'uptime': str(datetime.now() - start_time) if start_time else 'N/A',
        'scheduler': get_scheduler_status(),
        'db_stats': _get_db_stats()
    }
    
    return render_template('admin/index.html', system_info=system_info)
