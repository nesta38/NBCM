"""
NBCM V2.5 - Service Import
Import des données CMDB et Altaview avec détection automatique du format
"""
import os
import io
import csv
import re
import time
from datetime import datetime
from flask import current_app

from app import db, cache
from app.models.cmdb import ReferentielCMDB, CMDBHistory
from app.models.jobs import JobAltaview, ImportHistory
from app.services.compliance_service import normalize_hostname


def detect_csv_format(content, sample_size=2048):
    """
    Détecte automatiquement le format d'un fichier CSV.
    
    Returns:
        dict: {
            'delimiter': str,
            'encoding': str,
            'header_line': int,
            'has_header': bool
        }
    """
    # Prendre un échantillon
    sample = content[:sample_size] if len(content) > sample_size else content
    
    # Détecter le délimiteur
    delimiters = [';', ',', '\t', '|']
    delimiter_counts = {}
    
    for d in delimiters:
        delimiter_counts[d] = sample.count(d)
    
    # Le délimiteur le plus fréquent
    delimiter = max(delimiter_counts, key=delimiter_counts.get)
    
    # Si pas de délimiteur clair, essayer de détecter via les lignes
    if delimiter_counts[delimiter] == 0:
        lines = sample.split('\n')[:5]
        for d in delimiters:
            if all(d in line for line in lines if line.strip()):
                delimiter = d
                break
        else:
            delimiter = ','  # Par défaut
    
    # Détecter la ligne d'en-tête (ignorer les commentaires)
    lines = content.split('\n')
    header_line = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith('#') and not stripped.startswith('//'):
            header_line = i
            break
    
    # Détecter si la première ligne est un header
    first_data_line = lines[header_line] if header_line < len(lines) else ''
    has_header = not any(c.isdigit() for c in first_data_line.split(delimiter)[0][:10])
    
    return {
        'delimiter': delimiter,
        'encoding': 'utf-8',  # Détecté en amont
        'header_line': header_line,
        'has_header': has_header
    }


def detect_encoding(raw_content):
    """
    Détecte l'encodage d'un contenu binaire.
    """
    encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252', 'iso-8859-1']
    
    for encoding in encodings:
        try:
            raw_content.decode(encoding)
            return encoding
        except (UnicodeDecodeError, AttributeError):
            continue
    
    return 'utf-8'


def parse_date(date_str):
    """
    Parse une date avec support de multiples formats.
    """
    if not date_str:
        return None
    
    date_str = date_str.strip().strip('"').strip("'")
    
    formats = [
        '%Y-%m-%d %H:%M:%S',
        '%d/%m/%Y %H:%M:%S',
        '%m/%d/%Y %H:%M:%S',
        '%Y/%m/%d %H:%M:%S',
        '%b %d, %Y %I:%M:%S %p',
        '%d-%m-%Y %H:%M:%S',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d %H:%M',
        '%d/%m/%Y %H:%M',
        '%Y-%m-%d',
        '%d/%m/%Y',
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    # Essayer le format timestamp Unix
    try:
        ts = float(date_str)
        if ts > 1e12:  # Millisecondes
            ts = ts / 1000
        return datetime.fromtimestamp(ts)
    except:
        pass
    
    return None


def parse_size(size_str, is_already_gb=False):
    """
    Parse une taille avec détection de l'unité.
    Retourne la taille en GB.
    
    Args:
        size_str: La valeur de taille
        is_already_gb: Si True, la valeur est déjà en GB (pas de conversion)
    """
    if not size_str:
        return 0.0
    
    size_str = str(size_str).strip().strip('"').strip("'")
    
    # Nettoyer les séparateurs de milliers
    # "35,327,254" -> "35327254" (séparateurs US)
    # Mais "3,5" reste "3.5" (décimal européen)
    if ',' in size_str:
        parts = size_str.replace(' ', '').split(',')
        # Si toutes les parties après la première ont 3 chiffres -> séparateur de milliers
        if len(parts) > 1 and all(len(p) == 3 and p.isdigit() for p in parts[1:]):
            size_str = size_str.replace(',', '')
        else:
            # Sinon c'est un séparateur décimal
            size_str = size_str.replace(',', '.')
    
    # Pattern: nombre + unité optionnelle
    match = re.match(r'([\d.]+)\s*(KB|MB|GB|TB|K|M|G|T|B)?', size_str, re.IGNORECASE)
    
    if not match:
        try:
            return float(size_str)
        except:
            return 0.0
    
    value = float(match.group(1))
    unit = (match.group(2) or '').upper()
    
    # Si on sait déjà que c'est en GB, pas de conversion
    if is_already_gb and not unit:
        return value
    
    # Conversion en GB selon l'unité
    if unit in ['KB', 'K']:
        return value / (1024 * 1024)
    elif unit in ['MB', 'M']:
        return value / 1024
    elif unit in ['GB', 'G']:
        return value
    elif unit in ['TB', 'T']:
        return value * 1024
    elif unit == 'B':
        return value / (1024 * 1024 * 1024)
    else:
        # Pas d'unité détectée - retourner tel quel (on suppose GB par défaut)
        return value


def import_altaview_file(filepath, filename, user='auto-import'):
    """
    Importe un fichier Altaview (CSV) avec détection automatique du format.
    """
    start_time = time.time()
    
    try:
        # Lire le contenu brut
        with open(filepath, 'rb') as f:
            raw_content = f.read()
        
        # Détecter l'encodage
        encoding = detect_encoding(raw_content)
        content = raw_content.decode(encoding, errors='ignore')
        
        # Supprimer les lignes de commentaire
        lines = [line for line in content.splitlines() if not line.strip().startswith('#')]
        clean_content = '\n'.join(lines)
        
        # Détecter le format
        csv_format = detect_csv_format(clean_content)
        delimiter = csv_format['delimiter']
        
        current_app.logger.info(
            f"Import {filename}: encodage={encoding}, délimiteur='{delimiter}'"
        )
        
        # Parser le CSV
        stream = io.StringIO(clean_content)
        reader = csv.DictReader(stream, delimiter=delimiter)
        
        stats = {
            'nb_ajoutes': 0,
            'nb_mis_a_jour': 0,
            'nb_errors': 0
        }
        
        for row in reader:
            try:
                # Extraction du hostname
                hostname = (
                    row.get('hostname', '').strip() or
                    row.get('client', '').strip() or
                    row.get('asset_displayable_name', '').strip() or
                    row.get('Client', '').strip() or
                    row.get('clientName', '').strip()
                )
                
                if not hostname:
                    continue
                
                # Extraction de la date
                backup_time_str = (
                    row.get('backup_time', '').strip() or
                    row.get('date', '').strip() or
                    row.get('start_date', '').strip() or
                    row.get('Start Date', '').strip() or
                    row.get('startDate', '').strip()
                )
                
                backup_time = parse_date(backup_time_str)
                if not backup_time:
                    stats['nb_errors'] += 1
                    continue
                
                # Extraction de la taille
                taille_str = (
                    row.get('taille_gb', '') or
                    row.get('size_gb', '') or
                    row.get('size', '') or
                    row.get('Size', '') or
                    row.get('sizeGB', '') or
                    '0'
                )
                # Si la colonne contient "gb" dans le nom, la valeur est déjà en GB
                is_gb = any(k.lower() in ['taille_gb', 'size_gb', 'sizegb'] for k in row.keys() if row.get(k) == taille_str)
                taille_gb = parse_size(taille_str, is_already_gb=True)
                
                # Extraction du status
                status = (
                    row.get('status', '') or
                    row.get('Status', '') or
                    row.get('statusCode', '') or
                    'UNKNOWN'
                ).strip()
                
                # Extraction du job_id
                job_id = (
                    row.get('job_id', '') or
                    row.get('Job ID', '') or
                    row.get('jobId', '') or
                    row.get('last_job_id', '') or
                    ''
                ).strip()
                # Nettoyer les séparateurs de milliers dans le job_id
                if ',' in job_id:
                    job_id = job_id.replace(',', '')
                
                # Extraction de la policy
                policy_name = (
                    row.get('policy_name', '') or
                    row.get('Policy', '') or
                    row.get('policyName', '') or
                    ''
                ).strip()
                
                schedule_name = (
                    row.get('schedule_name', '') or
                    row.get('Schedule', '') or
                    row.get('scheduleName', '') or
                    ''
                ).strip()
                
                # Durée (peut être en minutes ou au format HH:MM:SS)
                duree_str = (
                    row.get('duree_minutes', '') or
                    row.get('duration', '') or
                    row.get('Duration', '') or
                    row.get('max_duration', '') or
                    '0'
                )
                try:
                    duree_str = str(duree_str).strip().strip('"').strip("'")
                    # Format HH:MM:SS
                    if ':' in duree_str:
                        parts = duree_str.split(':')
                        if len(parts) == 3:
                            # HH:MM:SS -> minutes
                            duree = int(parts[0]) * 60 + int(parts[1]) + int(parts[2]) // 60
                        elif len(parts) == 2:
                            # MM:SS -> minutes
                            duree = int(parts[0]) + int(parts[1]) // 60
                        else:
                            duree = 0
                    else:
                        duree = int(float(duree_str.replace(',', '')))
                except:
                    duree = 0
                
                # Vérification des doublons
                normalized_host = normalize_hostname(hostname)
                
                # Vérifier si un job identique existe déjà
                existing_job = None
                
                # Par job_id si disponible (identifiant unique)
                if job_id:
                    existing_job = JobAltaview.query.filter_by(job_id=job_id).first()
                
                # Si pas trouvé par job_id, chercher par combinaison hostname + backup_time
                if not existing_job:
                    existing_job = JobAltaview.query.filter_by(
                        backup_time=backup_time,
                        hostname=normalized_host,
                        policy_name=policy_name
                    ).first()
                
                if existing_job:
                    # MISE À JOUR avec les nouvelles valeurs (garder les données les plus récentes)
                    existing_job.status = status
                    existing_job.taille_gb = round(taille_gb, 6)
                    existing_job.duree_minutes = duree
                    existing_job.schedule_name = schedule_name
                    if job_id and not existing_job.job_id:
                        existing_job.job_id = job_id
                    existing_job.date_import = datetime.now()
                    stats['nb_mis_a_jour'] += 1
                else:
                    # Créer le job
                    job = JobAltaview(
                        hostname=normalized_host,
                        backup_time=backup_time,
                        job_id=job_id,
                        policy_name=policy_name,
                        schedule_name=schedule_name,
                        status=status,
                        taille_gb=round(taille_gb, 6),
                        duree_minutes=duree
                    )
                    db.session.add(job)
                    stats['nb_ajoutes'] += 1
                
            except Exception as e:
                current_app.logger.warning(f"Erreur ligne: {e}")
                stats['nb_errors'] += 1
        
        db.session.commit()
        
        # Invalider le cache
        cache.delete('conformite')
        
        # Calculer la durée
        duration = time.time() - start_time
        
        # Construire le message
        msg_parts = [f"{stats['nb_ajoutes']} ajoutés"]
        if stats['nb_mis_a_jour'] > 0:
            msg_parts.append(f"{stats['nb_mis_a_jour']} mis à jour")
        if stats['nb_errors'] > 0:
            msg_parts.append(f"{stats['nb_errors']} erreurs")
        
        message = ", ".join(msg_parts)
        
        current_app.logger.info(f"Import {filename}: {message} en {duration:.2f}s")
        
        # Historique
        ImportHistory(
            type_import='altaview',
            filename=filename,
            nb_lignes=stats['nb_ajoutes'] + stats['nb_mis_a_jour'],
            statut='success',
            message=message,
            utilisateur=user,
            nb_created=stats['nb_ajoutes'],
            nb_updated=stats['nb_mis_a_jour'],
            nb_skipped=0,
            nb_errors=stats['nb_errors'],
            duration_seconds=duration
        ).save()
        
        # Notifier le changement pour le refresh auto
        try:
            from app.services.notification_service import notify_import_completed
            notify_import_completed('altaview', stats)
        except Exception as e:
            current_app.logger.warning(f"Erreur notification: {e}")
        
        return True, stats
        
    except Exception as e:
        current_app.logger.error(f"Erreur import CSV {filename}: {e}", exc_info=True)
        return False, {'error': str(e)}


def import_cmdb_file(filepath, filename, mode='merge', user='admin'):
    """
    Importe un fichier CMDB.
    
    Args:
        mode: 'merge' (ajouter/màj) ou 'replace' (tout remplacer)
    """
    start_time = time.time()
    
    try:
        with open(filepath, 'rb') as f:
            raw_content = f.read()
        
        encoding = detect_encoding(raw_content)
        content = raw_content.decode(encoding, errors='ignore')
        
        csv_format = detect_csv_format(content)
        delimiter = csv_format['delimiter']
        
        stream = io.StringIO(content)
        reader = csv.DictReader(stream, delimiter=delimiter)
        
        stats = {'added': 0, 'updated': 0, 'skipped': 0}
        
        if mode == 'replace':
            ReferentielCMDB.query.delete()
            db.session.commit()
        
        for row in reader:
            hostname = (
                row.get('hostname', '').strip() or
                row.get('Hostname', '').strip() or
                row.get('server', '').strip() or
                row.get('Server', '').strip()
            )
            
            if not hostname:
                continue
            
            # Backup enabled
            backup_str = str(
                row.get('Backup yes/no', '') or
                row.get('backup', '') or
                row.get('Backup', '') or
                row.get('backup_enabled', '') or
                'yes'
            ).lower().strip()
            
            backup_enabled = backup_str in ['yes', 'oui', '1', 'true', 'y', 'o']
            
            # Commentaire
            comment = (
                row.get('comment', '') or
                row.get('Comment', '') or
                row.get('commentaire', '') or
                row.get('Commentaire', '') or
                row.get('notes', '') or
                ''
            ).strip()
            
            # Environnement
            env = (
                row.get('environnement', '') or
                row.get('Environnement', '') or
                row.get('environment', '') or
                row.get('env', '') or
                ''
            ).strip()
            
            # Vérifier si existe
            existing = ReferentielCMDB.query.filter_by(hostname=hostname).first()
            
            if existing:
                if mode == 'merge':
                    # Mettre à jour
                    existing.backup_enabled = backup_enabled
                    if comment:
                        existing.commentaire = comment
                    if env:
                        existing.environnement = env
                    existing.modifie_par = user
                    stats['updated'] += 1
                else:
                    stats['skipped'] += 1
            else:
                # Créer
                serveur = ReferentielCMDB(
                    hostname=hostname,
                    backup_enabled=backup_enabled,
                    commentaire=comment,
                    environnement=env,
                    modifie_par=user
                )
                db.session.add(serveur)
                stats['added'] += 1
        
        db.session.commit()
        cache.delete('conformite')
        
        duration = time.time() - start_time
        message = f"{stats['added']} ajoutés, {stats['updated']} mis à jour"
        
        ImportHistory(
            type_import='cmdb',
            filename=filename,
            nb_lignes=stats['added'] + stats['updated'],
            statut='success',
            message=message,
            utilisateur=user,
            nb_created=stats['added'],
            nb_updated=stats['updated'],
            nb_skipped=stats['skipped'],
            duration_seconds=duration
        ).save()
        
        return True, stats
        
    except Exception as e:
        current_app.logger.error(f"Erreur import CMDB {filename}: {e}", exc_info=True)
        return False, {'error': str(e)}


def supprimer_doublons_altaview(force=False):
    """
    Supprime les jobs en doublon.
    """
    try:
        from app.services.config_service import get_config
        
        if not force:
            config = get_config('dedup_auto', {})
            if not config.get('actif', True):
                return {'total': 0, 'supprimes': 0, 'skipped': True}
        
        current_app.logger.info("Démarrage suppression des doublons...")
        
        # Requête pour trouver les doublons
        from sqlalchemy import text
        query = text("""
            SELECT backup_time, hostname, policy_name, status, taille_gb, 
                   COUNT(*) as cnt, GROUP_CONCAT(id ORDER BY id) as ids
            FROM job_altaview 
            GROUP BY backup_time, hostname, policy_name, status, taille_gb 
            HAVING COUNT(*) > 1
        """)
        
        result = db.session.execute(query)
        doublons = result.fetchall()
        
        if not doublons:
            return {'total': 0, 'supprimes': 0}
        
        total_supprimes = 0
        for row in doublons:
            ids_str = row[6] if len(row) > 6 else str(row[-1])
            ids = [int(x) for x in str(ids_str).split(',')]
            ids_to_delete = ids[1:]  # Garder le premier
            
            if ids_to_delete:
                JobAltaview.query.filter(
                    JobAltaview.id.in_(ids_to_delete)
                ).delete(synchronize_session=False)
                total_supprimes += len(ids_to_delete)
        
        db.session.commit()
        
        current_app.logger.info(f"Doublons supprimés: {total_supprimes}")
        
        return {'total': len(doublons), 'supprimes': total_supprimes}
        
    except Exception as e:
        current_app.logger.error(f"Erreur suppression doublons: {e}", exc_info=True)
        db.session.rollback()
        return {'error': str(e)}
