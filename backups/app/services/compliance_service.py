"""
NBCM V2.5 - Service Conformité
Calcul et gestion de la conformité des backups
"""
import json
from datetime import datetime, timedelta
from collections import defaultdict
from flask import current_app

from app import db, cache
from app.models.cmdb import ReferentielCMDB
from app.models.jobs import JobAltaview
from app.models.compliance import HistoriqueConformite, ArchiveConformite
from app.services.config_service import get_config


def normalize_hostname(hostname):
    """
    Normalise un hostname pour la comparaison.
    Amélioration: gestion des cas spéciaux NetBackup.
    """
    if not hostname:
        return ""
    
    normalized = hostname.lower().strip()
    
    # Supprimer le domaine
    if '.' in normalized:
        normalized = normalized.split('.')[0]
    
    # Supprimer les préfixes email
    if '@' in normalized:
        normalized = normalized.split('@')[0]
    
    # Supprimer les suffixes de backup courants
    suffixes = ['_bkp', '_backup', '_prod', '_test', '_dev', '_dr', '_snap', '_clone']
    for suffix in suffixes:
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)]
    
    # Supprimer les préfixes de backup
    prefixes = ['bkp_', 'backup_']
    for prefix in prefixes:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
    
    return normalized


@cache.cached(timeout=60, key_prefix='conformite')
def calculer_conformite(periode_heures=24):
    """
    Calcule la conformité des backups.
    Résultat mis en cache pendant 60 secondes.
    """
    try:
        date_limite = datetime.now() - timedelta(hours=periode_heures)
        
        # Récupérer les serveurs actifs (non désactivés temporairement)
        serveurs_actifs = [
            s for s in ReferentielCMDB.query.filter_by(backup_enabled=True).all()
            if not s.est_desactive_temporairement()
        ]
        
        # Récupérer les jobs récents
        jobs_recents = JobAltaview.query.filter(
            JobAltaview.backup_time >= date_limite
        ).all()
        
        # Construire le mapping des jobs valides par hostname normalisé
        jobs_valides_par_host = defaultdict(list)
        for job in jobs_recents:
            # Un job est valide si:
            # - Status 0 ou 1 (OK ou Warning acceptable)
            # - Taille > 0
            try:
                status_num = int(job.status) if job.status and job.status.isdigit() else -1
                status_ok = status_num in [0, 1] or (job.status and job.status.upper() in ['SUCCESS', ''])
            except:
                status_ok = job.status.upper() in ['SUCCESS', ''] if job.status else True
            
            taille_ok = job.taille_gb and job.taille_gb > 0
            
            if status_ok and taille_ok:
                host_norm = normalize_hostname(job.hostname)
                jobs_valides_par_host[host_norm].append(job)
        
        # Mapping des hostnames CMDB normalisés
        hostnames_cmdb_norm = {
            normalize_hostname(s.hostname): s.hostname 
            for s in serveurs_actifs
        }
        
        # Classifier les serveurs
        conformes = []
        non_conformes = []
        non_references = []
        
        for serveur in serveurs_actifs:
            host_norm = normalize_hostname(serveur.hostname)
            if host_norm in jobs_valides_par_host and len(jobs_valides_par_host[host_norm]) > 0:
                conformes.append(serveur.hostname)
            else:
                non_conformes.append(serveur.hostname)
        
        # Serveurs hors CMDB (backup effectué mais pas dans le référentiel)
        for host_norm in jobs_valides_par_host.keys():
            if host_norm not in hostnames_cmdb_norm:
                # Prendre le premier hostname original
                non_references.append(jobs_valides_par_host[host_norm][0].hostname)
        
        # Calcul du taux
        total = len(serveurs_actifs)
        taux = (len(conformes) / total * 100) if total > 0 else 0
        
        # Enregistrer dans l'historique
        hist = HistoriqueConformite(
            total_cmdb=ReferentielCMDB.query.count(),
            total_backup_enabled=len(serveurs_actifs),
            total_jobs=len(jobs_recents),
            nb_conformes=len(conformes),
            nb_non_conformes=len(non_conformes),
            nb_non_references=len(non_references),
            taux_conformite=round(taux, 1),
            details_json=json.dumps({
                'conformes': conformes[:50],
                'periode_heures': periode_heures
            })
        )
        db.session.add(hist)
        db.session.commit()
        
        current_app.logger.info(
            f"Conformité calculée: {round(taux, 1)}% "
            f"({len(conformes)}/{total} serveurs conformes)"
        )
        
        return {
            'total_cmdb': ReferentielCMDB.query.count(),
            'total_backup_enabled': len(serveurs_actifs),
            'total_attendus': total,
            'total_jobs': len(jobs_recents),
            'conformes': len(conformes),
            'non_conformes': len(non_conformes),
            'non_references': len(non_references),
            'taux_conformite': round(taux, 1),
            'liste_conformes': sorted(conformes),
            'liste_non_conformes': sorted(non_conformes),
            'liste_non_references': sorted(non_references),
            'date_calcul': datetime.now().isoformat()
        }
        
    except Exception as e:
        current_app.logger.error(f"Erreur calcul conformité: {e}", exc_info=True)
        return {
            'total_cmdb': 0,
            'total_backup_enabled': 0,
            'total_attendus': 0,
            'total_jobs': 0,
            'conformes': 0,
            'non_conformes': 0,
            'non_references': 0,
            'taux_conformite': 0,
            'liste_conformes': [],
            'liste_non_conformes': [],
            'liste_non_references': [],
            'error': str(e)
        }


def invalidate_conformite_cache():
    """Invalide le cache de conformité"""
    cache.delete('conformite')


def get_jobs_map(hours=24):
    """
    Retourne un mapping des jobs par hostname normalisé.
    """
    date_limite = datetime.now() - timedelta(hours=hours)
    jobs = JobAltaview.query.filter(
        JobAltaview.backup_time >= date_limite
    ).order_by(JobAltaview.backup_time.desc()).all()
    
    jobs_map = defaultdict(list)
    for job in jobs:
        norm_name = normalize_hostname(job.hostname)
        jobs_map[norm_name].append(job)
    
    return jobs_map


def get_historique_conformite(days=30):
    """Récupère l'historique de conformité pour N jours"""
    date_limite = datetime.now() - timedelta(days=days)
    return HistoriqueConformite.query.filter(
        HistoriqueConformite.date_calcul >= date_limite
    ).order_by(HistoriqueConformite.date_calcul.asc()).all()


def get_trend_data(days=7):
    """
    Calcule les données de tendance pour les sparklines.
    """
    historique = get_historique_conformite(days)
    
    if not historique:
        return {
            'labels': [],
            'values': [],
            'trend': 0,
            'variation': 0
        }
    
    labels = [h.date_calcul.strftime('%d/%m %H:%M') for h in historique]
    values = [h.taux_conformite for h in historique]
    
    # Calcul de la variation
    if len(values) >= 2:
        variation = values[-1] - values[0]
        trend = 1 if variation > 0 else (-1 if variation < 0 else 0)
    else:
        variation = 0
        trend = 0
    
    return {
        'labels': labels,
        'values': values,
        'trend': trend,
        'variation': round(variation, 1)
    }


def archiver_conformite_quotidienne(force_now=False):
    """
    Archive la conformité quotidienne.
    Avec lock distribué Redis pour éviter les doublons.
    """
    from app.services.lock_service import acquire_lock, release_lock
    
    # 🔒 Acquérir un lock distribué pour éviter les doublons
    lock_key = 'archive_daily_lock'
    lock_acquired = acquire_lock(lock_key, timeout=300)  # Lock de 5 minutes max
    
    if not lock_acquired:
        current_app.logger.warning("Archive déjà en cours (lock actif), ignorée")
        return {'skipped': True, 'reason': 'Archive already running (locked)'}
    
    try:
        current_app.logger.info(f"Démarrage archivage ({'MANUEL' if force_now else 'AUTO'})...")
        maintenant = datetime.now()
        
        if force_now:
            date_fin = maintenant
            date_debut = maintenant - timedelta(hours=24)
        else:
            config = get_config('archive_config', {'heure': 18, 'minute': 0})
            heure_cible = int(config.get('heure', 18))
            minute_cible = int(config.get('minute', 0))
            
            date_fin = maintenant.replace(hour=heure_cible, minute=minute_cible, second=0, microsecond=0)
            date_debut = date_fin - timedelta(days=1)
            
            if maintenant < date_fin:
                date_fin = date_fin - timedelta(days=1)
                date_debut = date_debut - timedelta(days=1)
            
            # Vérifier si archive existe déjà
            existe = ArchiveConformite.query.filter(
                ArchiveConformite.date_debut_periode == date_debut,
                ArchiveConformite.date_fin_periode == date_fin
            ).first()
            
            if existe:
                current_app.logger.info("Archive déjà existante, ignorée")
                return {'skipped': True, 'reason': 'Archive already exists'}
        
        current_app.logger.info(
            f"Période: {date_debut.strftime('%d/%m/%Y %H:%M')} -> {date_fin.strftime('%d/%m/%Y %H:%M')}"
        )
        
        # Récupérer les données
        serveurs_actifs = [
            s for s in ReferentielCMDB.query.filter_by(backup_enabled=True).all()
            if not s.est_desactive_temporairement()
        ]
        
        jobs_periode = JobAltaview.query.filter(
            JobAltaview.backup_time >= date_debut,
            JobAltaview.backup_time <= date_fin
        ).all()
        
        # Calcul
        hostnames_sauvegardes_norm = {
            normalize_hostname(job.hostname): job.hostname 
            for job in jobs_periode
        }
        hostnames_cmdb_norm = {
            normalize_hostname(s.hostname): s.hostname 
            for s in serveurs_actifs
        }
        
        conformes = []
        non_conformes = []
        non_references = []
        
        for s in serveurs_actifs:
            if normalize_hostname(s.hostname) in hostnames_sauvegardes_norm:
                conformes.append(s.hostname)
            else:
                non_conformes.append(s.hostname)
        
        for h_norm, h_orig in hostnames_sauvegardes_norm.items():
            if h_norm not in hostnames_cmdb_norm:
                non_references.append(h_orig)
        
        total = len(serveurs_actifs)
        taux = (len(conformes) / total * 100) if total > 0 else 0
        
        # Créer l'archive
        archive = ArchiveConformite(
            date_archivage=maintenant,
            date_debut_periode=date_debut,
            date_fin_periode=date_fin,
            total_cmdb=ReferentielCMDB.query.count(),
            total_backup_enabled=len(serveurs_actifs),
            total_jobs=len(jobs_periode),
            nb_conformes=len(conformes),
            nb_non_conformes=len(non_conformes),
            nb_non_references=len(non_references),
            taux_conformite=round(taux, 1),
            liste_conformes=json.dumps(sorted(conformes)),
            liste_non_conformes=json.dumps(sorted(non_conformes)),
            liste_non_references=json.dumps(sorted(non_references)),
            donnees_json=json.dumps({
                'mode': 'manuel' if force_now else 'auto',
                'periode': {
                    'debut': date_debut.isoformat(),
                    'fin': date_fin.isoformat()
                }
            })
        )
        
        db.session.add(archive)
        db.session.commit()
        
        current_app.logger.info(
            f"Archive créée: ID={archive.id}, Taux={round(taux, 1)}%"
        )
        
        return {
            'success': True,
            'archive_id': archive.id,
            'taux_conformite': round(taux, 1),
            'periode': f"{date_debut.strftime('%d/%m/%Y %H:%M')} -> {date_fin.strftime('%d/%m/%Y %H:%M')}"
        }
        
    except Exception as e:
        current_app.logger.error(f"Erreur archivage: {e}", exc_info=True)
        db.session.rollback()
        return {'error': str(e)}
    finally:
        # 🔓 Libérer le lock
        release_lock(lock_key)
        current_app.logger.debug("Lock archivage libéré")
