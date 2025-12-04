"""
NBCM V2.5 - Service Email
Envoi des rapports par email avec protection anti-doublon
"""
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formatdate
from datetime import datetime, timedelta
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
        
        current_app.logger.info(f"[EMAIL] ✅ Sent successfully to {recipient_email}")
        return True
        
    except Exception as e:
        current_app.logger.error(f"[EMAIL] ❌ Error sending: {e}")
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
        
        current_app.logger.info(f"[EMAIL] ✅ Test sent successfully to {recipient_email}")
        return True
        
    except Exception as e:
        current_app.logger.error(f"[EMAIL] ❌ Error sending test: {e}")
        return False


def check_scheduled_emails():
    """
    Vérifie et envoie les emails programmés.
    
    PROTECTION ANTI-DOUBLON :
    - Utilise un lock Redis pour éviter l'exécution simultanée
    - Vérifie last_sent pour ne pas renvoyer dans les 5 minutes
    """
    # 🔒 LOCK REDIS pour éviter l'exécution simultanée par plusieurs workers
    from app.services.lock_service import get_lock_service
    
    lock_service = get_lock_service()
    lock_key = 'scheduled_emails_check'
    
    # Essayer d'acquérir le lock (expire après 60 secondes)
    if not lock_service.acquire_lock(lock_key, ttl=60):
        current_app.logger.debug("[EMAIL] ⏭️ Vérification déjà en cours par un autre worker")
        return
    
    try:
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        
        # Trouver les destinataires programmés pour cette heure
        recipients = Recipient.query.filter_by(
            active=True,
            schedule_time=current_time
        ).all()
        
        current_app.logger.info(f"[EMAIL] 🔍 Vérification programmée à {current_time} - {len(recipients)} destinataire(s) trouvé(s)")
        
        for recipient in recipients:
            # 🛡️ VÉRIFICATION ANTI-DOUBLON : Ne pas renvoyer si envoyé il y a moins de 5 minutes
            if recipient.last_sent:
                time_since_last = now - recipient.last_sent
                if time_since_last < timedelta(minutes=5):
                    current_app.logger.info(
                        f"[EMAIL] ⏭️ SKIP {recipient.email} - Déjà envoyé il y a {time_since_last.seconds // 60} min"
                    )
                    continue
            
            # Envoyer l'email
            current_app.logger.info(f"[EMAIL] 📧 Envoi programmé à {recipient.email} ({recipient.name})")
            success = send_email_report(recipient.email, recipient.name)
            
            if success:
                current_app.logger.info(f"[EMAIL] ✅ Email envoyé avec succès à {recipient.email}")
            else:
                current_app.logger.error(f"[EMAIL] ❌ Échec envoi à {recipient.email}")
    
    except Exception as e:
        current_app.logger.error(f"[EMAIL] ❌ Erreur vérification emails programmés: {e}", exc_info=True)
    
    finally:
        # 🔓 LIBÉRER LE LOCK
        lock_service.release_lock(lock_key)
        current_app.logger.debug("[EMAIL] 🔓 Lock libéré")
