"""
NBCM V2.5 - Routes CMDB
Gestion du référentiel serveurs
"""
import io
import os
import csv
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app import db, cache
from app.models.cmdb import ReferentielCMDB, CMDBHistory
from app.models.jobs import ImportHistory
from app.services.import_service import import_cmdb_file
from app.routes.auth import operator_required

cmdb_bp = Blueprint('cmdb', __name__)


@cmdb_bp.route('/')
@login_required
def list():
    """Liste des serveurs CMDB"""
    filtre_backup = request.args.get('filtre_backup', 'tous')
    search = request.args.get('search', '')
    
    query = ReferentielCMDB.query
    
    if filtre_backup == 'actif':
        query = query.filter_by(backup_enabled=True)
    elif filtre_backup == 'inactif':
        query = query.filter_by(backup_enabled=False)
    
    if search:
        query = query.filter(ReferentielCMDB.hostname.ilike(f'%{search}%'))
    
    serveurs = query.order_by(ReferentielCMDB.hostname).all()
    
    return render_template(
        'cmdb/list.html',
        serveurs=serveurs,
        filtre_backup=filtre_backup,
        search=search
    )


@cmdb_bp.route('/import', methods=['GET', 'POST'])
@operator_required
def import_page():
    """Import de fichier CMDB"""
    if request.method == 'POST':
        file = request.files.get('file')
        mode = request.form.get('mode', 'merge')
        
        if file:
            try:
                filename = secure_filename(file.filename)
                import_dir = current_app.config.get('UPLOAD_FOLDER', 'uploads')
                filepath = os.path.join(import_dir, filename)
                file.save(filepath)
                
                success, stats = import_cmdb_file(
                    filepath, 
                    filename, 
                    mode=mode,
                    user=current_user.username
                )
                
                os.remove(filepath)  # Nettoyer
                
                if success:
                    flash(f'Import réussi: {stats.get("added", 0)} ajoutés, {stats.get("updated", 0)} mis à jour', 'success')
                else:
                    flash(f'Erreur: {stats.get("error", "Inconnue")}', 'danger')
                    
                return redirect(url_for('cmdb.list'))
                
            except Exception as e:
                current_app.logger.error(f"Erreur import CMDB: {e}", exc_info=True)
                flash(f'Erreur: {e}', 'danger')
    
    return render_template('cmdb/import.html')


@cmdb_bp.route('/export')
@login_required
def export():
    """Export CSV du référentiel CMDB"""
    serveurs = ReferentielCMDB.query.order_by(ReferentielCMDB.hostname).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['hostname', 'Backup yes/no', 'comment', 'environnement', 'criticite', 'application'])
    
    for s in serveurs:
        writer.writerow([
            s.hostname,
            'yes' if s.backup_enabled else 'no',
            s.commentaire or '',
            s.environnement or '',
            s.criticite or '',
            s.application or ''
        ])
    
    output.seek(0)
    
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'cmdb_export_{datetime.now().strftime("%Y%m%d")}.csv'
    )


@cmdb_bp.route('/toggle/<int:id>', methods=['POST'])
@operator_required
def toggle(id):
    """Basculer l'état backup d'un serveur"""
    serveur = ReferentielCMDB.query.get_or_404(id)
    old_value = serveur.backup_enabled
    serveur.backup_enabled = not serveur.backup_enabled
    serveur.modifie_par = current_user.username
    
    CMDBHistory.log_change(
        serveur.id, 'update', 'backup_enabled',
        old_value, serveur.backup_enabled, current_user.username
    )
    
    db.session.commit()
    cache.delete('conformite')
    
    return redirect(url_for(
        'cmdb.list',
        filtre_backup=request.args.get('filtre_backup', 'tous'),
        search=request.args.get('search', '')
    ))


@cmdb_bp.route('/commentaire/<int:id>', methods=['POST'])
@operator_required
def update_commentaire(id):
    """Mettre à jour le commentaire d'un serveur"""
    serveur = ReferentielCMDB.query.get_or_404(id)
    old_value = serveur.commentaire
    serveur.commentaire = request.form.get('commentaire')
    serveur.modifie_par = current_user.username
    
    CMDBHistory.log_change(
        serveur.id, 'update', 'commentaire',
        old_value, serveur.commentaire, current_user.username
    )
    
    db.session.commit()
    flash('Commentaire mis à jour.', 'success')
    
    return redirect(url_for(
        'cmdb.list',
        filtre_backup=request.args.get('filtre_backup', 'tous'),
        search=request.args.get('search', '')
    ))


@cmdb_bp.route('/desactiver/<int:id>', methods=['POST'])
@operator_required
def desactiver(id):
    """Désactiver temporairement un serveur"""
    serveur = ReferentielCMDB.query.get_or_404(id)
    duree_jours = int(request.form.get('duree_jours', 30))
    raison = request.form.get('raison', '')
    
    serveur.desactiver_temporairement(duree_jours, raison, current_user.username)
    
    CMDBHistory.log_change(
        serveur.id, 'update', 'desactivation_temporaire',
        None, f'{duree_jours} jours: {raison}', current_user.username
    )
    
    db.session.commit()
    cache.delete('conformite')
    
    flash(f'Serveur désactivé pour {duree_jours} jours.', 'success')
    
    return redirect(url_for(
        'cmdb.list',
        filtre_backup=request.args.get('filtre_backup', 'tous'),
        search=request.args.get('search', '')
    ))


@cmdb_bp.route('/reactiver/<int:id>', methods=['POST'])
@operator_required
def reactiver(id):
    """Réactiver un serveur (FIX BUG V2.2 - réinitialisation complète)"""
    serveur = ReferentielCMDB.query.get_or_404(id)
    
    # FIX: Réinitialiser TOUS les champs de désactivation
    serveur.reactiver(current_user.username)
    
    CMDBHistory.log_change(
        serveur.id, 'update', 'reactivation',
        'désactivé', 'actif', current_user.username
    )
    
    db.session.commit()
    cache.delete('conformite')
    
    flash('Serveur réactivé.', 'success')
    
    return redirect(url_for(
        'cmdb.list',
        filtre_backup=request.args.get('filtre_backup', 'tous'),
        search=request.args.get('search', '')
    ))


@cmdb_bp.route('/add', methods=['GET', 'POST'])
@operator_required
def add():
    """Ajouter un serveur manuellement"""
    if request.method == 'POST':
        hostname = request.form.get('hostname', '').strip()
        
        if not hostname:
            flash('Le hostname est requis.', 'danger')
        elif ReferentielCMDB.query.filter_by(hostname=hostname).first():
            flash('Ce serveur existe déjà.', 'warning')
        else:
            serveur = ReferentielCMDB(
                hostname=hostname,
                backup_enabled=request.form.get('backup_enabled') == 'on',
                commentaire=request.form.get('commentaire', ''),
                environnement=request.form.get('environnement', ''),
                criticite=request.form.get('criticite', ''),
                application=request.form.get('application', ''),
                modifie_par=current_user.username
            )
            db.session.add(serveur)
            db.session.commit()
            cache.delete('conformite')
            
            flash(f'Serveur {hostname} ajouté.', 'success')
            return redirect(url_for('cmdb.list'))
    
    return render_template('cmdb/add.html')


@cmdb_bp.route('/delete/<int:id>', methods=['POST'])
@operator_required
def delete(id):
    """Supprimer un serveur"""
    serveur = ReferentielCMDB.query.get_or_404(id)
    hostname = serveur.hostname
    
    db.session.delete(serveur)
    db.session.commit()
    cache.delete('conformite')
    
    flash(f'Serveur {hostname} supprimé.', 'success')
    
    return redirect(url_for('cmdb.list'))
