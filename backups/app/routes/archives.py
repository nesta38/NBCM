"""
NBCM V2.5 - Routes Archives
Gestion des archives quotidiennes et manuelles
"""
import json
from flask import Blueprint, render_template, redirect, url_for, flash, make_response, request
from flask_login import login_required

from app import db
from app.models.compliance import ArchiveConformite
from app.services.report_service import generate_pdf_report_archive, generate_excel_report_archive
from app.services.compliance_service import archiver_conformite_quotidienne
from app.routes.auth import operator_required

archives_bp = Blueprint('archives', __name__)


# ============================================================================
# ARCHIVES QUOTIDIENNES - Historique des archives automatiques
# ============================================================================

@archives_bp.route('/quotidiennes')
@login_required
def quotidiennes():
    """
    Affiche l'historique des archives quotidiennes automatiques
    (Menu jaune dans la sidebar)
    """
    archives_list = ArchiveConformite.query.order_by(
        ArchiveConformite.date_archivage.desc()
    ).all()
    
    return render_template('archives/quotidiennes.html', archives=archives_list)


# ============================================================================
# ARCHIVAGE MANUEL - Création manuelle d'archives
# ============================================================================

@archives_bp.route('/manuel')
@login_required
def manuel():
    """
    Interface de création manuelle d'archives
    (Menu rouge dans la sidebar)
    """
    # Récupérer les dernières archives pour l'affichage
    recent_archives = ArchiveConformite.query.order_by(
        ArchiveConformite.date_archivage.desc()
    ).limit(5).all()
    
    return render_template('archives/manuel.html', recent_archives=recent_archives)


@archives_bp.route('/manuel/create', methods=['POST'])
@operator_required
def create_manuel():
    """Créer une archive manuelle maintenant"""
    result = archiver_conformite_quotidienne(force_now=True)
    
    if result.get('success'):
        flash(f"Archive créée avec succès : {result['periode']} - Taux de conformité : {result['taux_conformite']}%", 'success')
    elif result.get('skipped'):
        flash(f"Archive non créée : {result['reason']}", 'info')
    else:
        flash(f"Erreur lors de la création : {result.get('error', 'Erreur inconnue')}", 'danger')
    
    return redirect(url_for('archives.manuel'))


# ============================================================================
# ROUTE LEGACY - Redirection pour compatibilité
# ============================================================================

@archives_bp.route('/')
@login_required
def index():
    """
    Route legacy - redirige vers archives quotidiennes
    Pour compatibilité avec les anciens liens
    """
    return redirect(url_for('archives.quotidiennes'))


# ============================================================================
# ACTIONS COMMUNES - PDF, Excel, Suppression
# ============================================================================

@archives_bp.route('/<int:id>/pdf')
@login_required
def pdf(id):
    """Télécharger le PDF d'une archive"""
    archive = ArchiveConformite.query.get_or_404(id)
    
    conformite = {
        'total_cmdb': archive.total_cmdb,
        'total_backup_enabled': archive.total_backup_enabled,
        'total_attendus': archive.total_backup_enabled,
        'total_jobs': archive.total_jobs,
        'conformes': archive.nb_conformes,
        'non_conformes': archive.nb_non_conformes,
        'non_references': archive.nb_non_references,
        'taux_conformite': archive.taux_conformite,
        'liste_conformes': archive.get_liste_conformes(),
        'liste_non_conformes': archive.get_liste_non_conformes(),
        'liste_non_references': archive.get_liste_non_references(),
        'date_debut_periode': archive.date_debut_periode,
        'date_fin_periode': archive.date_fin_periode
    }
    
    pdf_buffer = generate_pdf_report_archive(conformite, archive)
    
    if pdf_buffer:
        response = make_response(pdf_buffer.getvalue())
        response.headers['Content-Type'] = 'application/pdf'
        filename = f'archive_{archive.date_debut_periode.strftime("%Y%m%d")}_to_{archive.date_fin_periode.strftime("%Y%m%d")}.pdf'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        return response
    
    flash('Erreur génération PDF.', 'danger')
    return redirect(request.referrer or url_for('archives.quotidiennes'))


@archives_bp.route('/<int:id>/excel')
@login_required
def excel(id):
    """Télécharger l'Excel d'une archive"""
    archive = ArchiveConformite.query.get_or_404(id)
    
    conformite = {
        'total_cmdb': archive.total_cmdb,
        'total_backup_enabled': archive.total_backup_enabled,
        'total_jobs': archive.total_jobs,
        'taux_conformite': archive.taux_conformite,
        'liste_conformes': archive.get_liste_conformes(),
        'liste_non_conformes': archive.get_liste_non_conformes(),
        'liste_non_references': archive.get_liste_non_references(),
    }
    
    excel_buffer = generate_excel_report_archive(conformite, archive)
    
    if excel_buffer:
        response = make_response(excel_buffer.getvalue())
        response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        filename = f'archive_{archive.date_debut_periode.strftime("%Y%m%d")}_to_{archive.date_fin_periode.strftime("%Y%m%d")}.xlsx'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        return response
    
    flash('Erreur génération Excel.', 'danger')
    return redirect(request.referrer or url_for('archives.quotidiennes'))


@archives_bp.route('/delete/<int:id>', methods=['POST'])
@operator_required
def delete(id):
    """Supprimer une archive"""
    archive = ArchiveConformite.query.get_or_404(id)
    db.session.delete(archive)
    db.session.commit()
    flash('Archive supprimée avec succès.', 'success')
    return redirect(request.referrer or url_for('archives.quotidiennes'))
