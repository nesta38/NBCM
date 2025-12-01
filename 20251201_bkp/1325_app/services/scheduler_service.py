"""
NBCM V3.0 - Service Scheduler
Gestion des tâches planifiées incluant les backups automatiques
Support du rechargement dynamique via Redis pub/sub
"""
import os
import fcntl
import atexit
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from flask import current_app

# Scheduler global
scheduler = None
scheduler_lock = None
_flask_app = None  # Stocker l'app Flask pour les jobs


def init_scheduler(app):
    """
    Initialise le scheduler avec verrouillage pour éviter les doublons.
    """
    global scheduler, scheduler_lock, _flask_app
    
    # Stocker l'app pour usage dans les jobs
    _flask_app = app
    
    lock_file_path = os.path.join(app.config.get('LOG_DIR', '/app/data/logs'), 'scheduler.lock')
    
    try:
        scheduler_lock = open(lock_file_path, 'wb')
        fcntl.flock(scheduler_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        
        with app.app_context():
            from app.services.config_service import get_config
            
            scheduler = BackgroundScheduler()
            
            # Tâche: Vérification des emails programmés (chaque minute)
            scheduler.add_job(
                func=lambda: run_in_context(app, check_scheduled_emails_job),
                trigger="interval",
                seconds=60,
                id='check_scheduled_emails',
                name='Vérification emails programmés'
            )
            
            # Tâche: Import automatique des fichiers (chaque minute)
            scheduler.add_job(
                func=lambda: run_in_context(app, check_auto_import_job),
                trigger="interval",
                seconds=60,
                id='auto_import_files',
                name='Import automatique fichiers'
            )
            
            # Tâche: Import IMAP (selon config)
            scheduler.add_job(
                func=lambda: run_in_context(app, fetch_imap_job),
                trigger="interval",
                minutes=1,
                id='imap_check',
                name='Vérification IMAP'
            )
            
            # Tâche: Import API (toutes les heures)
            scheduler.add_job(
                func=lambda: run_in_context(app, fetch_api_job),
                trigger="interval",
                minutes=60,
                id='api_import',
                name='Import API Altaview'
            )
            
            # Tâche: Nettoyage des doublons (toutes les heures)
            scheduler.add_job(
                func=lambda: run_in_context(app, cleanup_duplicates_job),
                trigger="interval",
                hours=1,
                id='cleanup_duplicates',
                name='Nettoyage doublons'
            )
            
            # Tâche: Nettoyage fichiers processed/ > 48h (tous les jours à 3h)
            scheduler.add_job(
                func=lambda: run_in_context(app, cleanup_processed_files_job),
                trigger=CronTrigger(hour=3, minute=0),
                id='cleanup_processed_files',
                name='Nettoyage fichiers processed/ > 48h'
            )
            
            # Tâche: Archivage quotidien (selon config)
            arch_config = get_config('archive_config', {'heure': 18, 'minute': 0, 'actif': True})
            if arch_config.get('actif', True):
                scheduler.add_job(
                    func=lambda: run_in_context(app, archive_daily_job),
                    trigger=CronTrigger(
                        hour=int(arch_config.get('heure', 18)),
                        minute=int(arch_config.get('minute', 0))
                    ),
                    id='archive_daily',
                    name='Archivage quotidien'
                )
            
            # Charger et ajouter les tâches de backup configurées
            load_backup_schedules(app)
            
            scheduler.start()
            app.logger.info("Scheduler démarré (processus maître)")
            
            # Démarrer le listener Redis avec l'app pour le contexte
            try:
                from app.services.scheduler_reload_service import get_reload_service
                reload_service = get_reload_service()
                reload_service.start_listener(SchedulerServiceWrapper(), app)
                app.logger.info("Listener Redis pour rechargement scheduler démarré")
            except Exception as e:
                app.logger.warning(f"Listener Redis non disponible: {e}")
            
            # Arrêt propre
            atexit.register(lambda: shutdown_scheduler())
            
            return True
            
    except BlockingIOError:
        app.logger.info("Scheduler déjà actif dans un autre processus")
        return False
    except Exception as e:
        app.logger.error(f"Erreur initialisation scheduler: {e}")
        return False


class SchedulerServiceWrapper:
    """
    Wrapper pour permettre au reload service d'appeler les méthodes de reload
    """
    
    def reload_backup_schedule(self, backup_type, frequency):
        """Recharge un schedule de backup spécifique"""
        from app.services.config_service import get_config
        from flask import current_app
        
        try:
            config_key = f'backup_schedule_{backup_type}_{frequency}'
            config = get_config(config_key, {})
            
            if config:
                reschedule_backup(backup_type, frequency, config)
                current_app.logger.info(f"✅ Backup schedule rechargé: {backup_type} {frequency}")
            else:
                current_app.logger.warning(f"Aucune config trouvée pour {backup_type} {frequency}")
                
        except Exception as e:
            current_app.logger.error(f"Erreur reload backup schedule: {e}", exc_info=True)
    
    def reload_all_backup_schedules(self):
        """Recharge TOUS les schedules de backup"""
        from app.services.config_service import get_config
        from flask import current_app
        
        frequencies = ['daily', 'weekly', 'monthly']
        backup_types = ['db', 'fs']
        
        reloaded = 0
        for backup_type in backup_types:
            for frequency in frequencies:
                try:
                    config_key = f'backup_schedule_{backup_type}_{frequency}'
                    config = get_config(config_key, {})
                    
                    if config:
                        reschedule_backup(backup_type, frequency, config)
                        reloaded += 1
                        
                except Exception as e:
                    current_app.logger.error(f"Erreur reload {backup_type}/{frequency}: {e}")
        
        current_app.logger.info(f"✅ {reloaded} backup schedules rechargés")


def load_backup_schedules(app):
    """
    Charge et ajoute les tâches de backup depuis la configuration.
    """
    from app.services.config_service import get_config
    
    frequencies = ['daily', 'weekly', 'monthly']
    backup_types = ['db', 'fs']
    
    for backup_type in backup_types:
        for frequency in frequencies:
            config_key = f'backup_schedule_{backup_type}_{frequency}'
            config = get_config(config_key, {})
            
            if config.get('enabled', False):
                try:
                    reschedule_backup(backup_type, frequency, config)
                except Exception as e:
                    app.logger.error(f"Erreur chargement backup {backup_type}/{frequency}: {e}")


def shutdown_scheduler():
    """
    Arrête proprement le scheduler.
    """
    global scheduler, scheduler_lock
    
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
    
    # Arrêter le listener Redis
    try:
        from app.services.scheduler_reload_service import get_reload_service
        reload_service = get_reload_service()
        reload_service.stop_listener()
    except:
        pass
    
    if scheduler_lock:
        try:
            fcntl.flock(scheduler_lock, fcntl.LOCK_UN)
            scheduler_lock.close()
        except:
            pass


def run_in_context(app, func):
    """
    Exécute une fonction dans le contexte de l'application.
    """
    with app.app_context():
        try:
            func()
        except Exception as e:
            app.logger.error(f"Erreur tâche planifiée: {e}", exc_info=True)


def check_scheduled_emails_job():
    """Tâche: Vérifier et envoyer les emails programmés."""
    from app.services.email_service import check_scheduled_emails
    check_scheduled_emails()


def check_auto_import_job():
    """Tâche: Vérifier et importer les fichiers CSV."""
    from app.services.external_import_service import check_altaview_auto_import
    check_altaview_auto_import()


def fetch_imap_job():
    """Tâche: Récupérer les pièces jointes IMAP."""
    from app.services.external_import_service import fetch_imap_attachments
    fetch_imap_attachments()


def fetch_api_job():
    """Tâche: Importer depuis l'API Altaview."""
    from app.services.external_import_service import fetch_altaview_api
    fetch_altaview_api()


def cleanup_duplicates_job():
    """Tâche: Nettoyer les doublons."""
    from app.services.import_service import supprimer_doublons_altaview
    supprimer_doublons_altaview()


def archive_daily_job():
    """Tâche: Archivage quotidien."""
    from app.services.compliance_service import archiver_conformite_quotidienne
    archiver_conformite_quotidienne()


def cleanup_processed_files_job():
    """Tâche: Nettoyer les fichiers processed/ plus anciens que 48h."""
    from app.services.cleanup_service import cleanup_service
    cleanup_service.cleanup_old_files()


def backup_db_job(frequency, config):
    """Tâche: Sauvegarde DB automatique"""
    from app.services.backup_service import BackupService
    from flask import current_app
    
    try:
        backup_service = BackupService()
        description = f'Sauvegarde automatique {frequency}'
        
        result = backup_service.create_backup(description)
        
        if result['success']:
            current_app.logger.info(f"Backup DB {frequency} créé: {result['filename']}")
            
            # Gérer la rétention
            retention = config.get('retention', 7)
            cleanup_result = backup_service.cleanup_old_backups('db', retention)
            current_app.logger.info(f"Rétention DB appliquée: {cleanup_result.get('deleted', 0)} backups supprimés")
        else:
            current_app.logger.error(f"Erreur backup DB {frequency}: {result['error']}")
            
    except Exception as e:
        current_app.logger.error(f"Exception backup DB {frequency}: {e}", exc_info=True)


def backup_fs_job(frequency, config):
    """Tâche: Sauvegarde FS automatique"""
    from app.services.backup_service import BackupService
    from flask import current_app
    
    try:
        backup_service = BackupService()
        description = f'Sauvegarde FS automatique {frequency}'
        
        result = backup_service.create_fs_backup(description, config)
        
        if result['success']:
            current_app.logger.info(f"Backup FS {frequency} créé: {result['filename']}")
            
            # Gérer la rétention
            retention = config.get('retention', 7)
            cleanup_result = backup_service.cleanup_old_backups('fs', retention)
            current_app.logger.info(f"Rétention FS appliquée: {cleanup_result.get('deleted', 0)} backups supprimés")
        else:
            current_app.logger.error(f"Erreur backup FS {frequency}: {result['error']}")
            
    except Exception as e:
        current_app.logger.error(f"Exception backup FS {frequency}: {e}", exc_info=True)


def get_scheduler_status():
    """Retourne le statut du scheduler."""
    global scheduler
    
    if scheduler and scheduler.running:
        jobs = []
        for job in scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run': job.next_run_time.strftime('%H:%M:%S') if job.next_run_time else '-'
            })
        return {
            'running': True,
            'jobs': jobs
        }
    
    # Vérifier si un autre processus a le lock
    lock_file_path = os.path.join(
        current_app.config.get('LOG_DIR', '/app/data/logs'),
        'scheduler.lock'
    )
    
    try:
        if os.path.exists(lock_file_path):
            with open(lock_file_path, 'wb') as f:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(f, fcntl.LOCK_UN)
            return {'running': False, 'jobs': []}
    except BlockingIOError:
        return {
            'running': True,
            'managed_by': 'main_process',
            'jobs': [{'id': 'Géré par processus principal', 'next_run': 'Actif'}]
        }
    
    return {'running': False, 'jobs': []}


def reschedule_archive(heure, minute, actif):
    """Reprogramme la tâche d'archivage."""
    global scheduler, _flask_app
    
    if not scheduler or not scheduler.running:
        return False
    
    job_id = 'archive_daily'
    
    try:
        if actif:
            trigger = CronTrigger(hour=heure, minute=minute)
            if scheduler.get_job(job_id):
                scheduler.reschedule_job(job_id, trigger=trigger)
            else:
                scheduler.add_job(
                    func=lambda: run_in_context(_flask_app, archive_daily_job),
                    trigger=trigger,
                    id=job_id,
                    name='Archivage quotidien'
                )
        else:
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)
        
        return True
        
    except Exception as e:
        current_app.logger.error(f"Erreur reprogrammation archive: {e}")
        return False


def reschedule_backup(backup_type, frequency, config):
    """
    Reprogramme une tâche de backup (DB ou FS).
    
    Args:
        backup_type: 'db' ou 'fs'
        frequency: 'daily', 'weekly', ou 'monthly'
        config: dict avec 'time', 'enabled', 'retention', etc.
    """
    global scheduler, _flask_app
    
    if not scheduler or not scheduler.running:
        return False
    
    job_id = f'backup_{backup_type}_{frequency}'
    
    try:
        if config.get('enabled', False):
            # Parser l'heure
            time_parts = config.get('time', '03:00').split(':')
            hour = int(time_parts[0])
            minute = int(time_parts[1]) if len(time_parts) > 1 else 0
            
            # Créer le trigger selon la fréquence
            if frequency == 'daily':
                trigger = CronTrigger(hour=hour, minute=minute)
            elif frequency == 'weekly':
                day_of_week = int(config.get('day_of_week', 6))
                trigger = CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute)
            elif frequency == 'monthly':
                day_of_month = int(config.get('day_of_month', 1))
                trigger = CronTrigger(day=day_of_month, hour=hour, minute=minute)
            else:
                return False
            
            # 🔥 FIX: Utiliser _flask_app au lieu de current_app
            # Fonction de backup appropriée
            if backup_type == 'db':
                job_func = lambda: run_in_context(
                    _flask_app, 
                    lambda: backup_db_job(frequency, config)
                )
            else:  # fs
                job_func = lambda: run_in_context(
                    _flask_app, 
                    lambda: backup_fs_job(frequency, config)
                )
            
            # Ajouter ou reprogrammer le job
            if scheduler.get_job(job_id):
                scheduler.reschedule_job(job_id, trigger=trigger)
            else:
                scheduler.add_job(
                    func=job_func,
                    trigger=trigger,
                    id=job_id,
                    name=f'Backup {backup_type.upper()} {frequency}'
                )
        else:
            # Désactiver le job
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)
        
        return True
        
    except Exception as e:
        # Utiliser _flask_app pour logger si current_app pas disponible
        if _flask_app:
            with _flask_app.app_context():
                from flask import current_app
                current_app.logger.error(f"Erreur reprogrammation backup {backup_type}/{frequency}: {e}")
        return False
