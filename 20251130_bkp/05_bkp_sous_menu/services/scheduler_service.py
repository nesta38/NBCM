"""
NBCM V2.5 - Service Scheduler
Gestion des tâches planifiées
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


def init_scheduler(app):
    """
    Initialise le scheduler avec verrouillage pour éviter les doublons.
    """
    global scheduler, scheduler_lock
    
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
            
            scheduler.start()
            app.logger.info("Scheduler démarré (processus maître)")
            
            # Arrêt propre
            atexit.register(lambda: shutdown_scheduler())
            
            return True
            
    except BlockingIOError:
        app.logger.info("Scheduler déjà actif dans un autre processus")
        return False
    except Exception as e:
        app.logger.error(f"Erreur initialisation scheduler: {e}")
        return False


def shutdown_scheduler():
    """
    Arrête proprement le scheduler.
    """
    global scheduler, scheduler_lock
    
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
    
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
    """
    Tâche: Vérifier et envoyer les emails programmés.
    """
    from app.services.email_service import check_scheduled_emails
    check_scheduled_emails()


def check_auto_import_job():
    """
    Tâche: Vérifier et importer les fichiers CSV.
    """
    from app.services.external_import_service import check_altaview_auto_import
    check_altaview_auto_import()


def fetch_imap_job():
    """
    Tâche: Récupérer les pièces jointes IMAP.
    """
    from app.services.external_import_service import fetch_imap_attachments
    fetch_imap_attachments()


def fetch_api_job():
    """
    Tâche: Importer depuis l'API Altaview.
    """
    from app.services.external_import_service import fetch_altaview_api
    fetch_altaview_api()


def cleanup_duplicates_job():
    """
    Tâche: Nettoyer les doublons.
    """
    from app.services.import_service import supprimer_doublons_altaview
    supprimer_doublons_altaview()


def archive_daily_job():
    """
    Tâche: Archivage quotidien.
    """
    from app.services.compliance_service import archiver_conformite_quotidienne
    archiver_conformite_quotidienne()


def cleanup_processed_files_job():
    """
    Tâche: Nettoyer les fichiers processed/ plus anciens que 48h.
    """
    from app.services.cleanup_service import cleanup_service
    cleanup_service.cleanup_old_files()


def get_scheduler_status():
    """
    Retourne le statut du scheduler.
    """
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
    """
    Reprogramme la tâche d'archivage.
    """
    global scheduler
    
    if not scheduler or not scheduler.running:
        return False
    
    job_id = 'archive_daily'
    
    try:
        if actif:
            trigger = CronTrigger(hour=heure, minute=minute)
            if scheduler.get_job(job_id):
                scheduler.reschedule_job(job_id, trigger=trigger)
            else:
                from flask import current_app
                scheduler.add_job(
                    func=lambda: run_in_context(current_app._get_current_object(), archive_daily_job),
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
