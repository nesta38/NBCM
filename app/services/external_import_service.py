"""
NBCM V2.5 - Service Import Externe
Import depuis IMAP et API Altaview
"""
import os
import imaplib
import email
import secrets
import requests
from datetime import datetime
from email.header import decode_header
from flask import current_app

from app import db
from app.models.jobs import JobAltaview, ImportHistory
from app.services.config_service import get_config
from app.services.import_service import import_altaview_file, normalize_hostname


def check_altaview_auto_import():
    """
    Vérifie et traite les fichiers CSV dans le dossier d'import automatique.
    Utilise un mécanisme de lock pour éviter les traitements multiples.
    """
    import shutil
    
    try:
        import_dir = current_app.config.get('ALTAVIEW_AUTO_IMPORT_DIR', '/app/data/altaview_auto_import')
        processed_dir = os.path.join(import_dir, 'processed')
        processing_dir = os.path.join(import_dir, 'processing')
        
        if not os.path.exists(import_dir):
            os.makedirs(import_dir, exist_ok=True)
            return
        
        os.makedirs(processed_dir, exist_ok=True)
        os.makedirs(processing_dir, exist_ok=True)
        
        for filename in os.listdir(import_dir):
            if not filename.lower().endswith('.csv'):
                continue
            
            filepath = os.path.join(import_dir, filename)
            
            # Vérifier que c'est bien un fichier (pas un dossier)
            if not os.path.isfile(filepath):
                continue
            
            # Déplacer vers processing pour "locker" le fichier
            processing_path = os.path.join(processing_dir, filename)
            
            try:
                # Essayer de déplacer le fichier (atomique)
                shutil.move(filepath, processing_path)
            except FileNotFoundError:
                # Fichier déjà pris par un autre worker
                current_app.logger.debug(f"Fichier {filename} déjà en cours de traitement")
                continue
            except Exception as e:
                current_app.logger.debug(f"Impossible de locker {filename}: {e}")
                continue
            
            current_app.logger.info(f"Traitement fichier: {filename}")
            
            try:
                success, stats = import_altaview_file(processing_path, filename, 'auto-import')
                
                # Déplacer le fichier traité vers processed
                ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                if success:
                    new_name = f"{ts}_{filename}"
                else:
                    new_name = f"ERROR_{ts}_{filename}"
                
                shutil.move(processing_path, os.path.join(processed_dir, new_name))
                current_app.logger.info(f"Fichier traité: {new_name}")
                
            except Exception as e:
                current_app.logger.error(f"Erreur traitement {filename}: {e}")
                # En cas d'erreur, remettre le fichier dans import_dir
                try:
                    shutil.move(processing_path, filepath)
                except:
                    pass
                
    except Exception as e:
        current_app.logger.error(f"Erreur auto-import: {e}", exc_info=True)


def fetch_imap_attachments(force=False):
    """
    Récupère les pièces jointes des emails IMAP.
    """
    try:
        config = get_config('email_import', {})
        
        if not config.get('actif'):
            return
        
        interval = int(config.get('check_interval', 15))
        if interval < 1:
            interval = 1
        
        # Ne vérifier qu'à l'intervalle configuré (sauf si forcé)
        if not force and datetime.now().minute % interval != 0:
            return
        
        current_app.logger.info(f"IMAP: Démarrage cycle ({'FORCE' if force else 'AUTO'} - {interval}min)")
        
        server = config.get('server')
        user = config.get('user')
        password = config.get('password')
        archive_folder = config.get('archive_folder', 'Archives_Altaview')
        subject_filter = config.get('subject_filter', 'NetBackup')
        
        if not server or not user:
            current_app.logger.warning("IMAP: Configuration incomplète")
            return
        
        # Connexion IMAP
        mail = imaplib.IMAP4_SSL(server)
        mail.login(user, password)
        
        # Créer le dossier d'archive si nécessaire
        try:
            mail.create(archive_folder)
        except:
            pass
        
        mail.select("inbox")
        
        # Rechercher les emails non lus avec le filtre
        status, msgs = mail.search(None, f'(UNSEEN SUBJECT "{subject_filter}")')
        
        import_dir = current_app.config.get('ALTAVIEW_AUTO_IMPORT_DIR', '/app/data/altaview_auto_import')
        processed_count = 0
        
        for email_id in msgs[0].split():
            processed = False
            try:
                res, data = mail.fetch(email_id, "(RFC822)")
                msg = email.message_from_bytes(data[0][1])
                
                if msg.is_multipart():
                    for part in msg.walk():
                        filename = part.get_filename()
                        if filename:
                            # Décoder le nom du fichier
                            header = decode_header(filename)[0]
                            if isinstance(header[0], bytes):
                                filename = header[0].decode(header[1] or 'utf-8')
                            
                            # Vérifier l'extension
                            if filename.lower().endswith(('.csv', '.txt', '.xlsx')):
                                new_name = f"altaview_imap_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                                filepath = os.path.join(import_dir, new_name)
                                
                                with open(filepath, 'wb') as f:
                                    f.write(part.get_payload(decode=True))
                                
                                current_app.logger.info(f"IMAP: Fichier sauvegardé: {new_name}")
                                processed = True
                                processed_count += 1
                
                # Archiver ou supprimer l'email traité
                if processed:
                    result = mail.copy(email_id, archive_folder)
                    if result[0] == 'OK':
                        mail.store(email_id, '+FLAGS', '\\Deleted')
                    else:
                        mail.store(email_id, '+FLAGS', '\\Deleted')
                        
            except Exception as e:
                current_app.logger.error(f"IMAP: Erreur traitement email {email_id}: {e}")
        
        mail.expunge()
        mail.logout()
        
        if processed_count > 0:
            current_app.logger.info(f"IMAP: {processed_count} fichier(s) récupéré(s)")
            
    except Exception as e:
        current_app.logger.error(f"IMAP: Erreur: {e}", exc_info=True)


def fetch_altaview_api():
    """
    Importe les données depuis l'API Altaview/Veritas Analytics.
    Télécharge un fichier CSV/TXT et utilise la fonction d'import standard.
    """
    try:
        config = get_config('altaview_api', {})
        
        if not config.get('actif'):
            current_app.logger.debug("API: Import désactivé")
            return False
        
        api_url = config.get('url', '').strip()
        token = config.get('token', '').strip()
        
        if not api_url or not token:
            current_app.logger.warning("API: Configuration incomplète (URL ou token manquant)")
            return False
        
        current_app.logger.info("API: Démarrage import depuis Veritas Analytics...")
        
        # Headers pour l'API Veritas Analytics
        headers = {
            'Authorization': token,  # Token direct, pas "Bearer"
            'Accept': '*/*'
        }
        
        # Appel API avec timeout
        try:
            response = requests.get(api_url, headers=headers, timeout=60)
            response.raise_for_status()  # Lève une exception si erreur HTTP
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"API: Erreur connexion - {e}")
            return False
        
        # Vérifier que nous avons bien reçu du contenu
        if not response.text or len(response.text) < 10:
            current_app.logger.warning("API: Réponse vide ou invalide")
            return False
        
        current_app.logger.info(f"API: Fichier récupéré ({len(response.text)} octets)")
        
        # Sauvegarder le fichier dans le répertoire d'import
        import_dir = current_app.config.get('ALTAVIEW_AUTO_IMPORT_DIR', '/app/data/altaview_auto_import')
        os.makedirs(import_dir, exist_ok=True)
        
        # Nom du fichier avec timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'altaview_api_{timestamp}.csv'
        filepath = os.path.join(import_dir, filename)
        
        # Écrire le contenu dans le fichier
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(response.text)
        
        current_app.logger.info(f"API: Fichier sauvegardé: {filename}")
        
        # Utiliser la fonction d'import standard pour traiter le fichier
        success, stats = import_altaview_file(filepath, filename, 'api-auto')
        
        if success:
            current_app.logger.info(f"API: Import réussi - {stats.get('nb_ajoutes', 0)} ajoutés, {stats.get('nb_mis_a_jour', 0)} mis à jour")
            
            # Déplacer le fichier dans processed
            processed_dir = os.path.join(import_dir, 'processed')
            os.makedirs(processed_dir, exist_ok=True)
            
            import shutil
            processed_path = os.path.join(processed_dir, filename)
            shutil.move(filepath, processed_path)
            
            return True
        else:
            current_app.logger.error(f"API: Erreur import - {stats.get('error', 'Erreur inconnue')}")
            
            # Garder le fichier en erreur pour analyse
            error_filename = f'ERROR_{filename}'
            error_path = os.path.join(import_dir, 'processed', error_filename)
            os.makedirs(os.path.dirname(error_path), exist_ok=True)
            
            import shutil
            shutil.move(filepath, error_path)
            
            return False
        
    except Exception as e:
        current_app.logger.error(f"API: Erreur générale: {e}", exc_info=True)
        return False
