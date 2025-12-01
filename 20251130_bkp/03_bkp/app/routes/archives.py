"""
NBCM V2.5 - Routes Archives
Gestion des archives quotidiennes
"""
import json
from flask import Blueprint, render_template, redirect, url_for, flash, make_response
from flask_login import login_required

from app import db
from app.models.compliance import ArchiveConformite
from app.services.report_service import generate_pdf_report_archive, generate_excel_report_archive
from app.routes.auth import operator_required

archives_bp = Blueprint('archives', __name__)


@archives_bp.route('/')
@login_required
def index():
    """Liste des archives"""
    archives_list = ArchiveConformite.query.order_by(
        ArchiveConformite.date_archivage.desc()
    ).all()
    
    return render_template('archives/index.html', archives=archives_list)


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
    return redirect(url_for('archives.index'))


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
    return redirect(url_for('archives.index'))


@archives_bp.route('/delete/<int:id>', methods=['POST'])
@operator_required
def delete(id):
    """Supprimer une archive"""
    archive = ArchiveConformite.query.get_or_404(id)
    db.session.delete(archive)
    db.session.commit()
    flash('Archive supprimée.', 'success')
    return redirect(url_for('archives.index'))
