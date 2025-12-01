"""
NBCM V2.5 - Routes Rapport
Génération et export des rapports
"""
import io
import csv
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, make_response, send_file, jsonify
from flask_login import login_required, current_user

from app import db, cache
from app.models.cmdb import ReferentielCMDB
from app.models.jobs import ImportHistory
from app.models.compliance import HistoriqueConformite
from app.services.compliance_service import calculer_conformite, get_historique_conformite
from app.services.report_service import generate_pdf_report, generate_excel_report
from app.services.email_service import send_email_report
from app.services.config_service import get_config

rapport_bp = Blueprint('rapport', __name__)


@rapport_bp.route('/')
@login_required
def index():
    """Page rapport de conformité"""
    conformite = calculer_conformite()
    historique = get_historique_conformite(days=7)
    
    chart_labels = [h.date_calcul.strftime('%d/%m') for h in historique]
    chart_values = [h.taux_conformite for h in historique]
    
    return render_template(
        'rapport/index.html',
        conformite=conformite,
        historique=historique,
        chart_labels=chart_labels,
        chart_values=chart_values
    )


@rapport_bp.route('/pdf')
@login_required
def pdf():
    """Télécharger le rapport PDF"""
    conformite = calculer_conformite()
    pdf_buffer = generate_pdf_report(conformite)
    
    if pdf_buffer:
        response = make_response(pdf_buffer.getvalue())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=rapport_conformite_{datetime.now().strftime("%Y%m%d")}.pdf'
        return response
    
    flash('Erreur lors de la génération du PDF.', 'danger')
    return redirect(url_for('rapport.index'))


@rapport_bp.route('/excel')
@login_required
def excel():
    """Télécharger le rapport Excel"""
    conformite = calculer_conformite()
    excel_buffer = generate_excel_report(conformite)
    
    if excel_buffer:
        response = make_response(excel_buffer.getvalue())
        response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        response.headers['Content-Disposition'] = f'attachment; filename=rapport_conformite_{datetime.now().strftime("%Y%m%d")}.xlsx'
        return response
    
    flash('Erreur lors de la génération Excel.', 'danger')
    return redirect(url_for('rapport.index'))


@rapport_bp.route('/email', methods=['POST'])
@login_required
def email():
    """Envoyer le rapport par email"""
    try:
        config = get_config('email_rapport', {})
        if not config.get('actif') or not config.get('email_to'):
            flash('Configuration email non active.', 'warning')
        else:
            for dest in config['email_to'].split(','):
                send_email_report(dest.strip())
            flash('Rapport envoyé par email.', 'success')
    except Exception as e:
        flash(f'Erreur: {e}', 'danger')
    
    return redirect(url_for('rapport.index'))


@rapport_bp.route('/export_hors_cmdb')
@login_required
def export_hors_cmdb():
    """Export CSV des serveurs hors CMDB"""
    conformite = calculer_conformite()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['hostname', 'Backup yes/no', 'comment'])
    
    for host in conformite['liste_non_references']:
        writer.writerow([host, 'yes', 'Import Auto (Hors CMDB)'])
    
    output.seek(0)
    
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'import_hors_cmdb_{datetime.now().strftime("%Y%m%d")}.csv'
    )


@rapport_bp.route('/import_hors_cmdb_auto', methods=['POST'])
@login_required
def import_hors_cmdb_auto():
    """Import automatique des serveurs hors CMDB"""
    conformite = calculer_conformite()
    liste_hors_cmdb = conformite['liste_non_references']
    
    if not liste_hors_cmdb:
        flash('Aucun serveur à importer.', 'info')
        return redirect(url_for('rapport.index'))
    
    count = 0
    for host in liste_hors_cmdb:
        if not ReferentielCMDB.query.filter_by(hostname=host).first():
            db.session.add(ReferentielCMDB(
                hostname=host,
                backup_enabled=True,
                commentaire='Import Auto (Détecté hors périmètre)',
                modifie_par=current_user.username
            ))
            count += 1
    
    db.session.commit()
    cache.delete('conformite')
    
    if count > 0:
        ImportHistory(
            type_import='cmdb_auto',
            filename='AUTO_DETECT',
            nb_lignes=count,
            statut='success',
            message=f'{count} serveurs ajoutés depuis liste Hors CMDB',
            utilisateur=current_user.username
        ).save()
    
    flash(f'{count} serveurs ajoutés à la CMDB.', 'success')
    return redirect(url_for('rapport.index'))


@rapport_bp.route('/api/check-import')
@login_required
def check_import():
    """API pour vérifier s'il y a eu un nouvel import"""
    from app.services.notification_service import get_last_import_notification
    
    notification = get_last_import_notification()
    
    if notification:
        return jsonify({
            'should_refresh': True,
            'import_type': notification.get('import_type'),
            'timestamp': notification.get('timestamp'),
            'stats': notification.get('stats', {})
        })
    
    return jsonify({'should_refresh': False})
