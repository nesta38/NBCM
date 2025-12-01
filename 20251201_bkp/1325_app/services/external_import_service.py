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
    Importe les données depuis l'API Altaview.
    """
    try:
        config = get_config('altaview_api', {})
        
        if not config.get('actif'):
            return False
        
        base_url = config.get('url', '').strip()
        token = config.get('token')
        
        if not base_url or not token:
            current_app.logger.warning("API: Configuration incomplète")
            return False
        
        current_app.logger.info("API: Démarrage import...")
        
        # Nettoyer l'URL
        clean_url = base_url.rstrip('/').replace('/run', '').replace('/results', '')
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        # Essayer différentes méthodes
        attempts = [
            ('GET', clean_url),
            ('GET', f"{clean_url}/results"),
            ('POST', f"{clean_url}/run")
        ]
        
        data = None
        
        for method, url in attempts:
            try:
                if method == 'POST':
                    response = requests.post(url, headers=headers, json={}, timeout=30)
                else:
                    response = requests.get(url, headers=headers, timeout=30)
                
                if response.status_code == 200:
                    json_data = response.json()
                    if isinstance(json_data, list) or (isinstance(json_data, dict) and ('data' in json_data or 'rows' in json_data)):
                        data = json_data
                        current_app.logger.info(f"API: Connexion OK via {method} {url}")
                        break
            except requests.RequestException as e:
                current_app.logger.debug(f"API: Tentative {method} {url} échouée: {e}")
                continue
        
        if not data:
            current_app.logger.warning("API: Aucune donnée récupérée")
            return False
        
        # Extraire les jobs
        jobs_list = []
        if isinstance(data, list):
            jobs_list = data
        elif isinstance(data, dict):
            if 'data' in data:
                jobs_list = data['data']
            elif 'rows' in data:
                jobs_list = data['rows']
            elif 'reportData' in data:
                jobs_list = data['reportData'].get('rows', [])
        
        nb_ajoutes = 0
        
        for row in jobs_list:
            try:
                hostname = (
                    row.get('hostname') or
                    row.get('client') or
                    row.get('clientName') or
                    row.get('assetName')
                )
                
                if not hostname:
                    continue
                
                # Date
                date_raw = row.get('backup_time') or row.get('startDate') or row.get('date')
                backup_time = datetime.now()
                
                if date_raw:
                    if isinstance(date_raw, (int, float)):
                        # Timestamp Unix (millisecondes)
                        backup_time = datetime.fromtimestamp(date_raw / 1000.0)
                    else:
                        try:
                            backup_time = datetime.fromisoformat(
                                str(date_raw).replace('Z', '').replace('T', ' ')[:19]
                            )
                        except:
                            pass
                
                # Taille
                size_raw = str(row.get('sizeGB') or row.get('taille_gb') or row.get('size') or 0).strip()
                
                import re
                match = re.match(r'([\d.]+)\s*(KB|MB|GB|K|M|G)?', size_raw, re.IGNORECASE)
                if match:
                    value = float(match.group(1).replace(',', ''))
                    unit = match.group(2).upper() if match.group(2) else None
                    
                    if unit in ['KB', 'K']:
                        size_gb = value / (1024 * 1024)
                    elif unit in ['MB', 'M']:
                        size_gb = value / 1024
                    elif unit in ['GB', 'G']:
                        size_gb = value
                    else:
                        size_gb = value
                        if size_gb > 100000:
                            size_gb /= (1024 * 1024 * 1024)
                else:
                    size_gb = 0.0
                
                # Créer le job
                job = JobAltaview(
                    hostname=normalize_hostname(hostname),
                    backup_time=backup_time,
                    job_id=str(row.get('jobId') or row.get('job_id') or secrets.token_hex(4)),
                    policy_name=str(row.get('policyName') or row.get('policy_name') or ''),
                    schedule_name=str(row.get('scheduleName') or row.get('schedule_name') or ''),
                    status=str(row.get('statusCode') or row.get('status') or 'UNKNOWN'),
                    taille_gb=round(size_gb, 2),
                    duree_minutes=int(row.get('duration') or row.get('duree_minutes') or 0)
                )
                db.session.add(job)
                nb_ajoutes += 1
                
            except Exception as e:
                current_app.logger.debug(f"API: Erreur traitement ligne: {e}")
                continue
        
        db.session.commit()
        
        ImportHistory(
            type_import='altaview_api',
            filename='API_AUTO',
            nb_lignes=nb_ajoutes,
            statut='success',
            message=f'{nb_ajoutes} jobs importés',
            utilisateur='api-auto'
        ).save()
        
        current_app.logger.info(f"API: {nb_ajoutes} jobs importés")
        return True
        
    except Exception as e:
        current_app.logger.error(f"API: Erreur: {e}", exc_info=True)
        return False
