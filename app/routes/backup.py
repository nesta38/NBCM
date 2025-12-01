"""
Routes pour la gestion des backups/restaurations
Accessible uniquement par les administrateurs
Support du rechargement dynamique du scheduler via Redis pub/sub
"""
from datetime import datetime
from flask import Blueprint, render_template, request, flash, redirect, url_for, send_from_directory
from flask_login import login_required, current_user
from app.services.backup_service import BackupService
from app.services.cache_service import CacheService
from app.services.config_service import get_config, set_config
from functools import wraps

backup_bp = Blueprint('backup', __name__, url_prefix='/admin/backup')

def admin_required(f):
    """Décorateur pour restreindre l'accès aux administrateurs"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash('Accès réservé aux administrateurs', 'danger')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated_function

def _get_backup_data():
    """Helper pour récupérer les données de backup"""
    backup_service = BackupService()
    cache_service = CacheService()
    return {
        'backups': backup_service.list_backups(),
        'redis_enabled': cache_service.is_enabled()
    }

def _get_schedule_data(backup_type, frequency):
    """Helper pour récupérer les données de planification"""
    config_key = f'backup_schedule_{backup_type}_{frequency}'
    schedule_config = get_config(config_key, {})
    
    # Calculer la prochaine exécution (approximation)
    next_run = 'Non planifiée'
    if schedule_config.get('enabled', False):
        try:
            time_str = schedule_config.get('time', '03:00')
            if frequency == 'weekly':
                days = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']
                day_idx = int(schedule_config.get('day_of_week', 6))
                next_run = f"Chaque {days[day_idx]} à {time_str}"
            elif frequency == 'monthly':
                day_num = schedule_config.get('day_of_month', 1)
                next_run = f"Le {day_num} de chaque mois à {time_str}"
            else:  # daily
                next_run = f"Tous les jours à {time_str}"
        except:
            next_run = 'Erreur de calcul'
    
    data = _get_backup_data()
    data['schedule_config'] = schedule_config
    data['next_run'] = next_run
    return data

@backup_bp.route('/')
@admin_required
def index():
    """Page d'accueil - Vue d'ensemble backups"""
    return render_template('admin/backup_index.html', **_get_backup_data())

# ============================================================================
# SAUVEGARDES MANUELLES
# ============================================================================

@backup_bp.route('/backups/db')
@admin_required
def backups_db():
    """Sauvegardes manuelles DB"""
    return render_template('admin/backup_backups_db.html', **_get_backup_data())

@backup_bp.route('/backups/fs')
@admin_required
def backups_fs():
    """Sauvegardes manuelles FS"""
    return render_template('admin/backup_backups_fs.html', **_get_backup_data())

# ============================================================================
# RESTAURATIONS
# ============================================================================

@backup_bp.route('/restore/db')
@admin_required
def restore_db():
    """Restaurations DB"""
    return render_template('admin/backup_restore_db.html', **_get_backup_data())

@backup_bp.route('/restore/fs')
@admin_required
def restore_fs():
    """Restaurations FS"""
    return render_template('admin/backup_restore_fs.html', **_get_backup_data())

# ============================================================================
# PLANIFICATION DB - Routes GET
# ============================================================================

@backup_bp.route('/schedule/db/daily')
@admin_required
def schedule_db_daily():
    """Planification sauvegarde DB quotidienne"""
    return render_template('admin/backup_schedule_db_daily.html', **_get_schedule_data('db', 'daily'))

@backup_bp.route('/schedule/db/weekly')
@admin_required
def schedule_db_weekly():
    """Planification sauvegarde DB hebdomadaire"""
    return render_template('admin/backup_schedule_db_weekly.html', **_get_schedule_data('db', 'weekly'))

@backup_bp.route('/schedule/db/monthly')
@admin_required
def schedule_db_monthly():
    """Planification sauvegarde DB mensuelle"""
    return render_template('admin/backup_schedule_db_monthly.html', **_get_schedule_data('db', 'monthly'))

# ============================================================================
# PLANIFICATION FS - Routes GET
# ============================================================================

@backup_bp.route('/schedule/fs/daily')
@admin_required
def schedule_fs_daily():
    """Planification sauvegarde FS quotidienne"""
    return render_template('admin/backup_schedule_fs_daily.html', **_get_schedule_data('fs', 'daily'))

@backup_bp.route('/schedule/fs/weekly')
@admin_required
def schedule_fs_weekly():
    """Planification sauvegarde FS hebdomadaire"""
    return render_template('admin/backup_schedule_fs_weekly.html', **_get_schedule_data('fs', 'weekly'))

@backup_bp.route('/schedule/fs/monthly')
@admin_required
def schedule_fs_monthly():
    """Planification sauvegarde FS mensuelle"""
    return render_template('admin/backup_schedule_fs_monthly.html', **_get_schedule_data('fs', 'monthly'))

# ============================================================================
# PLANIFICATION DB - Routes POST (Configuration)
# ============================================================================

@backup_bp.route('/schedule/db/<frequency>/configure', methods=['POST'])
@admin_required
def configure_schedule_db(frequency):
    """Configure la planification DB (daily/weekly/monthly) avec rechargement automatique"""
    if frequency not in ['daily', 'weekly', 'monthly']:
        flash('❌ Fréquence invalide', 'danger')
        return redirect(url_for('backup.index'))
    
    config = {
        'time': request.form.get('schedule_time'),
        'retention': int(request.form.get('retention', 7)),
        'enabled': request.form.get('enabled') == 'on'
    }
    
    # Ajouter les paramètres spécifiques
    if frequency == 'weekly':
        config['day_of_week'] = request.form.get('day_of_week', '6')
    elif frequency == 'monthly':
        config['day_of_month'] = request.form.get('day_of_month', '1')
    
    # Sauvegarder la configuration
    config_key = f'backup_schedule_db_{frequency}'
    set_config(config_key, config, f'Planification Backup DB {frequency}', current_user.username)
    
    # 🔥 NOUVEAU: Envoyer signal Redis pour recharger le scheduler SANS REDÉMARRAGE
    try:
        from app.services.scheduler_reload_service import get_reload_service
        reload_service = get_reload_service()
        
        if reload_service.signal_reload_backup_schedule('db', frequency):
            flash(f'✅ Configuration DB {frequency} enregistrée et scheduler rechargé automatiquement', 'success')
        else:
            flash(f'✅ Configuration DB {frequency} enregistrée (Redis non disponible - redémarrage requis)', 'warning')
    except Exception as e:
        flash(f'✅ Configuration DB {frequency} enregistrée (redémarrage requis pour appliquer)', 'warning')
    
    return redirect(url_for(f'backup.schedule_db_{frequency}'))

# ============================================================================
# PLANIFICATION FS - Routes POST (Configuration)
# ============================================================================

@backup_bp.route('/schedule/fs/<frequency>/configure', methods=['POST'])
@admin_required
def configure_schedule_fs(frequency):
    """Configure la planification FS (daily/weekly/monthly) avec rechargement automatique"""
    if frequency not in ['daily', 'weekly', 'monthly']:
        flash('❌ Fréquence invalide', 'danger')
        return redirect(url_for('backup.index'))
    
    config = {
        'time': request.form.get('schedule_time'),
        'retention': int(request.form.get('retention', 7)),
        'directories': request.form.get('directories', ''),
        'compression': request.form.get('compression') == 'on',
        'enabled': request.form.get('enabled') == 'on'
    }
    
    # Ajouter les paramètres spécifiques
    if frequency == 'weekly':
        config['day_of_week'] = request.form.get('day_of_week', '6')
    elif frequency == 'monthly':
        config['day_of_month'] = request.form.get('day_of_month', '1')
    
    # Sauvegarder la configuration
    config_key = f'backup_schedule_fs_{frequency}'
    set_config(config_key, config, f'Planification Backup FS {frequency}', current_user.username)
    
    # 🔥 NOUVEAU: Envoyer signal Redis pour recharger le scheduler SANS REDÉMARRAGE
    try:
        from app.services.scheduler_reload_service import get_reload_service
        reload_service = get_reload_service()
        
        if reload_service.signal_reload_backup_schedule('fs', frequency):
            flash(f'✅ Configuration FS {frequency} enregistrée et scheduler rechargé automatiquement', 'success')
        else:
            flash(f'✅ Configuration FS {frequency} enregistrée (Redis non disponible - redémarrage requis)', 'warning')
    except Exception as e:
        flash(f'✅ Configuration FS {frequency} enregistrée (redémarrage requis pour appliquer)', 'warning')
    
    return redirect(url_for(f'backup.schedule_fs_{frequency}'))

# ============================================================================
# ACTIONS - Création, Restauration, Suppression
# ============================================================================

@backup_bp.route('/create', methods=['POST'])
@admin_required
def create():
    """Créer une nouvelle sauvegarde DB"""
    description = request.form.get('description', '').strip()
    
    backup_service = BackupService()
    result = backup_service.create_backup(description)
    
    if result['success']:
        flash(f"✅ Sauvegarde DB créée : {result['filename']} ({result['size'] / 1024:.1f} KB)", 'success')
    else:
        flash(f"❌ Erreur lors de la sauvegarde DB : {result['error']}", 'danger')
    
    return redirect(request.referrer or url_for('backup.backups_db'))

@backup_bp.route('/create-fs', methods=['POST'])
@admin_required
def create_fs():
    """Créer une nouvelle sauvegarde FS"""
    description = request.form.get('description', '').strip()
    
    backup_service = BackupService()
    result = backup_service.create_fs_backup(description)
    
    if result['success']:
        flash(f"✅ Sauvegarde FS créée : {result['filename']} ({result['size'] / (1024*1024):.1f} MB)", 'success')
    else:
        flash(f"❌ Erreur lors de la sauvegarde FS : {result['error']}", 'danger')
    
    return redirect(request.referrer or url_for('backup.backups_fs'))

@backup_bp.route('/restore/<filename>', methods=['POST'])
@admin_required
def restore(filename):
    """Restaurer une sauvegarde DB"""
    # Confirmation obligatoire
    confirm = request.form.get('confirm')
    if confirm != 'RESTORE':
        flash('⚠️ Restauration annulée : confirmation requise', 'warning')
        return redirect(url_for('backup.restore_db'))
    
    backup_service = BackupService()
    result = backup_service.restore_backup(filename)
    
    if result['success']:
        flash('✅ Base de données restaurée avec succès', 'success')
        
        # Invalider tout le cache Redis
        cache_service = CacheService()
        if cache_service.is_enabled():
            cache_service.invalidate_all()
            flash('🔄 Cache Redis invalidé', 'info')
    else:
        flash(f"❌ Erreur lors de la restauration : {result['error']}", 'danger')
    
    return redirect(url_for('backup.restore_db'))

@backup_bp.route('/restore-fs/<filename>', methods=['POST'])
@admin_required
def restore_fs_extract(filename):
    """Restaurer une sauvegarde FS (extraction)"""
    # Confirmation obligatoire
    confirm = request.form.get('confirm')
    if confirm != 'EXTRACT':
        flash('⚠️ Extraction annulée : confirmation requise', 'warning')
        return redirect(url_for('backup.restore_fs'))
    
    backup_service = BackupService()
    result = backup_service.restore_fs_backup(filename)
    
    if result['success']:
        flash('✅ Archive FS extraite avec succès - Redémarrez l\'application', 'success')
    else:
        flash(f"❌ Erreur lors de l'extraction : {result['error']}", 'danger')
    
    return redirect(url_for('backup.restore_fs'))

@backup_bp.route('/delete/<filename>', methods=['POST'])
@admin_required
def delete(filename):
    """Supprimer une sauvegarde"""
    backup_service = BackupService()
    result = backup_service.delete_backup(filename)
    
    if result['success']:
        flash(f'✅ Sauvegarde supprimée : {filename}', 'success')
    else:
        flash(f"❌ Erreur lors de la suppression : {result['error']}", 'danger')
    
    return redirect(request.referrer or url_for('backup.index'))

@backup_bp.route('/download/<filename>')
@admin_required
def download(filename):
    """Télécharger une sauvegarde"""
    backup_service = BackupService()
    
    # Chercher le fichier dans les deux répertoires
    if (backup_service.backup_db_dir / filename).exists():
        directory = backup_service.backup_db_dir
    elif (backup_service.backup_fs_dir / filename).exists():
        directory = backup_service.backup_fs_dir
    else:
        flash('❌ Fichier introuvable', 'danger')
        return redirect(request.referrer or url_for('backup.index'))
    
    return send_from_directory(
        directory,
        filename,
        as_attachment=True
    )

@backup_bp.route('/clear-cache', methods=['POST'])
@admin_required
def clear_cache():
    """Vider le cache Redis"""
    cache_service = CacheService()
    
    if not cache_service.is_enabled():
        flash('⚠️ Redis n\'est pas activé', 'warning')
        return redirect(url_for('backup.index'))
    
    if cache_service.invalidate_all():
        flash('✅ Cache Redis vidé avec succès', 'success')
    else:
        flash('❌ Erreur lors du vidage du cache', 'danger')
    
    return redirect(url_for('backup.index'))
