"""
NBCM V2.5 - Service Email
Envoi des rapports par email
"""
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formatdate
from datetime import datetime
from flask import current_app

from app import db
from app.models.compliance import Recipient
from app.services.config_service import get_config
from app.services.compliance_service import calculer_conformite
from app.services.report_service import generate_pdf_report, generate_excel_report


def send_email_report(recipient_email, recipient_name=None):
    """
    Envoie un rapport de conformité par email.
    """
    try:
        config = get_config('email_rapport', {})
        
        if not config.get('actif'):
            current_app.logger.warning("Envoi email désactivé")
            return False
        
        conformite = calculer_conformite()
        
        msg = MIMEMultipart()
        msg['From'] = config['email_from']
        msg['To'] = recipient_email
        msg['Subject'] = f"NetBackup Report - {datetime.now().strftime('%d/%m/%Y')}"
        msg['Date'] = formatdate(localtime=True)
        
        body = f"""Hello,

Here is the backup compliance report for {datetime.now().strftime('%d/%m/%Y')}.

Statistics:
- Compliance Rate: {conformite['taux_conformite']}%
- Compliant Servers: {conformite['conformes']} / {conformite['total_attendus']}
- Failed Servers: {conformite['non_conformes']}
- Out of CMDB: {conformite['non_references']}

Regards,
NetBackup Compliance Manager
"""
        msg.attach(MIMEText(body, 'plain'))
        
        pdf = generate_pdf_report(conformite)
        if pdf:
            p = MIMEBase('application', 'pdf')
            p.set_payload(pdf.getvalue())
            encoders.encode_base64(p)
            p.add_header('Content-Disposition', 'attachment; filename="report.pdf"')
            msg.attach(p)
        
        excel = generate_excel_report(conformite)
        if excel:
            x = MIMEBase('application', 'vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            x.set_payload(excel.getvalue())
            encoders.encode_base64(x)
            x.add_header('Content-Disposition', 'attachment; filename="report.xlsx"')
            msg.attach(x)
        
        server = smtplib.SMTP(config['smtp_server'], int(config['smtp_port']))
        server.starttls()
        server.login(config['smtp_user'], config['smtp_password'])
        server.send_message(msg)
        server.quit()
        
        # Mettre à jour last_sent pour le recipient
        recipient = Recipient.query.filter_by(email=recipient_email).first()
        if recipient:
            recipient.last_sent = datetime.now()
            db.session.commit()
        
        current_app.logger.info(f"[EMAIL] Sent successfully to {recipient_email}")
        return True
        
    except Exception as e:
        current_app.logger.error(f"[EMAIL] Error sending: {e}")
        return False


def send_test_email(recipient_email):
    """
    Envoie un email de test.
    """
    try:
        config = get_config('email_rapport', {})
        
        msg = MIMEMultipart()
        msg['From'] = config['email_from']
        msg['To'] = recipient_email
        msg['Subject'] = f"NetBackup Test - {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        msg['Date'] = formatdate(localtime=True)
        
        body = f"""Hello,

This is a test email from NetBackup Compliance Manager.

Configuration:
- SMTP Server: {config.get('smtp_server')}
- Port: {config.get('smtp_port')}
- Date: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

Regards,
NBCM
"""
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(config['smtp_server'], int(config['smtp_port']))
        server.starttls()
        server.login(config['smtp_user'], config['smtp_password'])
        server.send_message(msg)
        server.quit()
        
        current_app.logger.info(f"[EMAIL] Test sent successfully to {recipient_email}")
        return True
        
    except Exception as e:
        current_app.logger.error(f"[EMAIL] Error sending test: {e}")
        return False


def check_scheduled_emails():
    """
    Vérifie et envoie les emails programmés.
    """
    try:
        now = datetime.now().strftime("%H:%M")
        
        recipients = Recipient.query.filter_by(
            active=True,
            schedule_time=now
        ).all()
        
        for recipient in recipients:
            current_app.logger.info(f"Envoi programmé à {recipient.email}")
            send_email_report(recipient.email, recipient.name)
            
    except Exception as e:
        current_app.logger.error(f"Erreur vérification emails programmés: {e}")
