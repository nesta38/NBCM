"""
Routes pour la gestion des backups/restaurations
Accessible uniquement par les administrateurs
"""
from flask import Blueprint, render_template, request, flash, redirect, url_for, send_from_directory
from flask_login import login_required, current_user
from app.services.backup_service import BackupService
from app.services.cache_service import CacheService
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

@backup_bp.route('/')
@admin_required
def index():
    """Page d'accueil - Vue d'ensemble backups"""
    return render_template('admin/backup_index.html', **_get_backup_data())

# ============================================================================
# SAUVEGARDES
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
# PLANIFICATION DB
# ============================================================================

@backup_bp.route('/schedule/db/daily')
@admin_required
def schedule_db_daily():
    """Planification sauvegarde DB quotidienne"""
    return render_template('admin/backup_schedule_db_daily.html', **_get_backup_data())

@backup_bp.route('/schedule/db/weekly')
@admin_required
def schedule_db_weekly():
    """Planification sauvegarde DB hebdomadaire"""
    return render_template('admin/backup_schedule_db_weekly.html', **_get_backup_data())

@backup_bp.route('/schedule/db/monthly')
@admin_required
def schedule_db_monthly():
    """Planification sauvegarde DB mensuelle"""
    return render_template('admin/backup_schedule_db_monthly.html', **_get_backup_data())

# ============================================================================
# PLANIFICATION FS
# ============================================================================

@backup_bp.route('/schedule/fs/daily')
@admin_required
def schedule_fs_daily():
    """Planification sauvegarde FS quotidienne"""
    return render_template('admin/backup_schedule_fs_daily.html', **_get_backup_data())

@backup_bp.route('/schedule/fs/weekly')
@admin_required
def schedule_fs_weekly():
    """Planification sauvegarde FS hebdomadaire"""
    return render_template('admin/backup_schedule_fs_weekly.html', **_get_backup_data())

@backup_bp.route('/schedule/fs/monthly')
@admin_required
def schedule_fs_monthly():
    """Planification sauvegarde FS mensuelle"""
    return render_template('admin/backup_schedule_fs_monthly.html', **_get_backup_data())

@backup_bp.route('/create', methods=['POST'])
@admin_required
def create():
    """Créer une nouvelle sauvegarde"""
    description = request.form.get('description', '').strip()
    
    backup_service = BackupService()
    result = backup_service.create_backup(description)
    
    if result['success']:
        flash(f"✅ Sauvegarde créée : {result['filename']} ({result['size'] / 1024:.1f} KB)", 'success')
    else:
        flash(f"❌ Erreur lors de la sauvegarde : {result['error']}", 'danger')
    
    return redirect(url_for('backup.index'))

@backup_bp.route('/restore/<filename>', methods=['POST'])
@admin_required
def restore(filename):
    """Restaurer une sauvegarde"""
    # Confirmation obligatoire
    confirm = request.form.get('confirm')
    if confirm != 'RESTORE':
        flash('⚠️ Restauration annulée : confirmation requise', 'warning')
        return redirect(url_for('backup.index'))
    
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
    
    return redirect(url_for('backup.index'))

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
    
    return redirect(url_for('backup.index'))

@backup_bp.route('/download/<filename>')
@admin_required
def download(filename):
    """Télécharger une sauvegarde"""
    backup_service = BackupService()
    return send_from_directory(
        backup_service.backup_dir,
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
