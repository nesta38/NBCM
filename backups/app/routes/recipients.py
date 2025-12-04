"""
NBCM V2.5 - Routes Recipients
Gestion des destinataires de rapports
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app import db
from app.models.compliance import Recipient
from app.routes.auth import operator_required

recipients_bp = Blueprint('recipients', __name__)


@recipients_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    """Liste et ajout de destinataires"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        schedule_time = request.form.get('schedule_time', '08:00')
        
        if not name or not email:
            flash('Nom et email requis.', 'danger')
        elif Recipient.query.filter_by(email=email).first():
            flash('Cet email existe déjà.', 'warning')
        else:
            recipient = Recipient(
                name=name,
                email=email,
                schedule_time=schedule_time,
                active=True
            )
            db.session.add(recipient)
            db.session.commit()
            flash(f'Destinataire {name} ajouté.', 'success')
    
    recipients = Recipient.query.order_by(Recipient.name).all()
    return render_template('recipients/index.html', recipients=recipients)


@recipients_bp.route('/toggle/<int:id>', methods=['POST'])
@operator_required
def toggle(id):
    """Activer/désactiver un destinataire"""
    recipient = Recipient.query.get_or_404(id)
    recipient.active = not recipient.active
    db.session.commit()
    flash(f"Destinataire {'activé' if recipient.active else 'désactivé'}.", 'success')
    return redirect(url_for('recipients.index'))


@recipients_bp.route('/delete/<int:id>')
@operator_required
def delete(id):
    """Supprimer un destinataire"""
    recipient = Recipient.query.get_or_404(id)
    name = recipient.name
    db.session.delete(recipient)
    db.session.commit()
    flash(f'Destinataire {name} supprimé.', 'success')
    return redirect(url_for('recipients.index'))


@recipients_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@operator_required
def edit(id):
    """Modifier un destinataire"""
    recipient = Recipient.query.get_or_404(id)
    
    if request.method == 'POST':
        recipient.name = request.form.get('name', '').strip()
        recipient.email = request.form.get('email', '').strip()
        recipient.schedule_time = request.form.get('schedule_time', '08:00')
        recipient.report_format = request.form.get('report_format', 'both')
        recipient.include_details = request.form.get('include_details') == 'on'
        db.session.commit()
        flash('Destinataire mis à jour.', 'success')
        return redirect(url_for('recipients.index'))
    
    return render_template('recipients/edit.html', recipient=recipient)
