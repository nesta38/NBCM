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

@backup_bp.route('/')
@admin_required
def index():
    """Page de gestion des backups"""
    backup_service = BackupService()
    backups = backup_service.list_backups()
    
    # Vérifier si Redis est actif
    cache_service = CacheService()
    redis_enabled = cache_service.is_enabled()
    
    return render_template(
        'admin/backup.html',
        backups=backups,
        redis_enabled=redis_enabled
    )

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
