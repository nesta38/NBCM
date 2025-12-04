"""
NBCM V2.5 - Service de Restauration Asynchrone
Gestion des restaurations DB avec suivi de progression et logs en temps réel
✅ CORRECTION: Termine les connexions actives avant restauration
✅ FIX: RLock pour éviter deadlocks + logging sans current_app
✅ FIX: Plus besoin d'app_context dans le thread
"""
import threading
import time
import subprocess
import gzip
import shutil
import logging
from datetime import datetime
from pathlib import Path


class RestoreTask:
    """Représente une tâche de restauration en cours"""
    
    def __init__(self, filename, restore_type='db'):
        self.filename = filename
        self.restore_type = restore_type  # 'db' ou 'fs'
        self.status = 'pending'  # pending, running, completed, failed
        self.progress = 0  # 0-100
        self.message = 'En attente...'
        self.logs = []
        self.started_at = datetime.now()
        self.completed_at = None
        self.error = None
    
    def add_log(self, message, level='info'):
        """Ajoute un log avec timestamp"""
        log_entry = {
            'timestamp': datetime.now().strftime('%H:%M:%S'),
            'level': level,  # info, success, warning, error
            'message': message
        }
        self.logs.append(log_entry)
        
        # ✅ FIX: Logger avec logging standard au lieu de current_app.logger
        logger = logging.getLogger('nbcm.restore')
        
        if level == 'error':
            logger.error(f"[RESTORE] {message}")
        elif level == 'warning':
            logger.warning(f"[RESTORE] {message}")
        else:
            logger.info(f"[RESTORE] {message}")
    
    def to_dict(self):
        """Sérialisation pour API"""
        return {
            'filename': self.filename,
            'restore_type': self.restore_type,
            'status': self.status,
            'progress': self.progress,
            'message': self.message,
            'logs': self.logs,
            'started_at': self.started_at.strftime('%Y-%m-%d %H:%M:%S'),
            'completed_at': self.completed_at.strftime('%Y-%m-%d %H:%M:%S') if self.completed_at else None,
            'error': self.error,
            'duration_seconds': (datetime.now() - self.started_at).seconds if self.status == 'running' else None
        }


class AsyncRestoreService:
    """Service de restauration asynchrone"""
    
    def __init__(self):
        self.current_task = None
        self.lock = threading.RLock()  # ✅ FIX: RLock au lieu de Lock pour éviter les deadlocks
    
    def is_restore_running(self):
        """Vérifie si une restauration est en cours"""
        with self.lock:
            return self.current_task is not None and self.current_task.status == 'running'
    
    def get_current_task(self):
        """Retourne la tâche en cours"""
        with self.lock:
            return self.current_task
    
    def start_restore_db(self, filename, backup_service, app=None):
        """Démarre une restauration DB asynchrone (app est optionnel, non utilisé)"""
        with self.lock:
            if self.is_restore_running():
                return {'success': False, 'error': 'Une restauration est déjà en cours'}
            
            # Créer une nouvelle tâche
            self.current_task = RestoreTask(filename, 'db')
            
            # Lancer le thread (pas besoin de passer app)
            thread = threading.Thread(
                target=self._restore_db_thread,
                args=(filename, backup_service),
                daemon=True
            )
            thread.start()
            
            return {'success': True, 'message': 'Restauration démarrée'}
    
    def _restore_db_thread(self, filename, backup_service):
        """Thread de restauration DB - fonctionne sans contexte Flask"""
        task = self.current_task
        
        try:
            task.status = 'running'
            task.add_log(f'🔄 Démarrage restauration: {filename}')
            task.progress = 10
            
            # ✅ CRITIQUE : Attendre 5 secondes pour que le worker Flask ferme sa connexion
            task.add_log('⏳ Attente fermeture connexion du worker (5s)...')
            time.sleep(5)
            
            # Vérifier le fichier
            filepath = backup_service.backup_db_dir / filename
            if not filepath.exists():
                raise Exception('Fichier introuvable')
            
            task.add_log(f'✅ Fichier trouvé: {filepath}')
            task.progress = 20
            
            # Lire métadonnées
            meta_file = filepath.with_suffix('.gz.meta')
            db_type = 'postgresql'
            
            if meta_file.exists():
                with open(meta_file) as f:
                    for line in f:
                        if line.startswith('db_type='):
                            db_type = line.strip().split('=')[1]
            
            task.add_log(f'📊 Type de base: {db_type}')
            task.progress = 30
            
            # Décompression
            task.message = 'Décompression du backup...'
            task.add_log('📦 Décompression en cours...')
            
            sql_file = filepath.with_suffix('')
            with gzip.open(filepath, 'rb') as f_in:
                with open(sql_file, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            task.add_log(f'✅ Fichier décompressé: {sql_file.name}')
            task.progress = 50
            
            # Restauration
            if db_type == 'postgresql':
                task.message = 'Restauration PostgreSQL...'
                result = self._restore_postgres(sql_file, backup_service.db_config, task)
            else:
                task.message = 'Restauration SQLite...'
                result = self._restore_sqlite(sql_file, backup_service.db_config, task)
            
            # Nettoyage
            sql_file.unlink()
            task.add_log('🧹 Fichier temporaire supprimé')
            
            if result['success']:
                task.status = 'completed'
                task.progress = 100
                task.message = '✅ Restauration terminée avec succès'
                task.add_log('✅ Restauration terminée avec succès', 'success')
            else:
                raise Exception(result.get('error', 'Erreur inconnue'))
            
        except Exception as e:
            task.status = 'failed'
            task.error = str(e)
            task.message = f'❌ Échec: {str(e)}'
            task.add_log(f'❌ ERREUR: {str(e)}', 'error')
        
        finally:
            task.completed_at = datetime.now()
            duration = (task.completed_at - task.started_at).seconds
            task.add_log(f'⏱️ Durée totale: {duration} secondes')
            
            # Garder la tâche en mémoire pendant 5 minutes pour consultation
            time.sleep(300)
            with self.lock:
                if self.current_task == task:
                    self.current_task = None
    
    def _restore_postgres(self, sql_file, db_config, task):
        """Restaure PostgreSQL avec logs détaillés + terminaison connexions actives"""
        try:
            task.add_log('🐘 Connexion à PostgreSQL...')
            task.progress = 55
            
            env = {
                'PGPASSWORD': db_config['password']
            }
            
            # ✅ CRITIQUE : Terminer TOUTES les connexions actives AVANT restauration
            task.add_log('⚠️ Terminaison des connexions actives sur la base...')
            task.message = 'Terminaison des connexions actives...'
            
            terminate_cmd = [
                'psql',
                '-h', db_config['host'],
                '-p', db_config['port'],
                '-U', db_config['user'],
                '-d', 'postgres',  # ✅ Se connecter à la DB postgres, pas à nbcm
                '-c', f"""
                    SELECT pg_terminate_backend(pg_stat_activity.pid)
                    FROM pg_stat_activity
                    WHERE pg_stat_activity.datname = '{db_config['database']}'
                    AND pid <> pg_backend_pid();
                """
            ]
            
            try:
                terminate_result = subprocess.run(
                    terminate_cmd,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if terminate_result.returncode == 0:
                    # Compter combien de connexions ont été terminées
                    output = terminate_result.stdout.strip()
                    conn_count = output.count('t') if output else 0
                    task.add_log(f'✅ {conn_count} connexion(s) terminée(s)')
                else:
                    task.add_log(f'⚠️ Avertissement terminaison: {terminate_result.stderr[:150]}', 'warning')
            
            except subprocess.TimeoutExpired:
                task.add_log('⚠️ Timeout terminaison connexions (pas critique)', 'warning')
            
            task.progress = 60
            
            # ✅ Attendre 3 secondes que les connexions se ferment proprement
            task.add_log('⏳ Attente fermeture des connexions (3s)...')
            time.sleep(3)
            
            # Maintenant, lancer la restauration
            task.add_log('🔧 Lancement de la restauration...')
            task.message = 'Restauration en cours...'
            task.progress = 65
            
            cmd = [
                'psql',
                '-h', db_config['host'],
                '-p', db_config['port'],
                '-U', db_config['user'],
                '-d', db_config['database'],
                '-f', str(sql_file),
                '-v', 'ON_ERROR_STOP=1'  # Arrêter en cas d'erreur
            ]
            
            task.add_log(f'📝 Commande: psql -h {db_config["host"]} -d {db_config["database"]} -f {sql_file.name}')
            task.progress = 70
            
            # Exécuter avec capture des logs
            process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Lire stderr en temps réel pour progression
            stderr_lines = []  # ✅ AJOUT
            lines_processed = 0
            for line in process.stderr:
                stderr_lines.append(line)  # ✅ AJOUT
                lines_processed += 1
                if lines_processed % 100 == 0:  # Log toutes les 100 lignes
                    task.add_log(f'📝 {lines_processed} commandes traitées...')
                    task.progress = min(95, 70 + (lines_processed // 100))
            
            # Attendre la fin
            returncode = process.wait(timeout=900)  # 15 minutes max
            
            # stdout, stderr = process.communicate()
            stdout = process.stdout.read()
            stderr = ''.join(stderr_lines)  # ✅ CHANGEMEN
            
            if returncode != 0:
                task.add_log(f'❌ Code retour psql: {returncode}', 'error')
                task.add_log(f'❌ STDERR COMPLET ({len(stderr)} caractères):', 'error')
                # Logger TOUT le stderr
                for line in stderr.split('\n'):
                    if line.strip():
                        task.add_log(f'  {line}', 'error')
                return {'success': False, 'error': f'psql returned {returncode}'}
            
            task.add_log(f'✅ PostgreSQL restauré ({lines_processed} commandes exécutées)', 'success')
            task.progress = 95
            
            return {'success': True}
            
        except subprocess.TimeoutExpired:
            task.add_log('❌ TIMEOUT: Restauration trop longue (> 15 min)', 'error')
            return {'success': False, 'error': 'Timeout après 15 minutes'}
        except Exception as e:
            task.add_log(f'❌ Exception: {str(e)}', 'error')
            import traceback
            traceback_str = traceback.format_exc()
            task.add_log(f'Traceback: {traceback_str[:500]}', 'error')
            return {'success': False, 'error': str(e)}
    
    def _restore_sqlite(self, sql_file, db_config, task):
        """Restaure SQLite"""
        try:
            task.add_log('📄 Restauration SQLite...')
            task.progress = 70
            
            sqlite_path = db_config['path']
            
            # Copie vers destination
            shutil.copy2(sql_file, sqlite_path)
            
            task.add_log('✅ SQLite restauré', 'success')
            task.progress = 95
            
            return {'success': True}
            
        except Exception as e:
            task.add_log(f'❌ Exception: {str(e)}', 'error')
            return {'success': False, 'error': str(e)}


# Singleton global
_async_restore_service = None


def get_async_restore_service():
    """Retourne le service singleton"""
    global _async_restore_service
    
    if _async_restore_service is None:
        _async_restore_service = AsyncRestoreService()
    
    return _async_restore_service
