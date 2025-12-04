"""
Service de sauvegarde/restauration PostgreSQL et Filesystem
Permet de créer, restaurer et gérer les backups de la base de données et du filesystem
"""
import os
import subprocess
import tarfile
from datetime import datetime, timedelta
from pathlib import Path
import gzip
import shutil
from flask import current_app

class BackupService:
    """Service de sauvegarde/restauration PostgreSQL et Filesystem"""
    
    def __init__(self):
        self.backup_dir = Path(current_app.config.get('BACKUP_DIR', 'backups'))
        self.backup_dir.mkdir(exist_ok=True)
        
        # Créer sous-répertoires
        self.backup_db_dir = self.backup_dir / 'db'
        self.backup_fs_dir = self.backup_dir / 'fs'
        self.backup_db_dir.mkdir(exist_ok=True)
        self.backup_fs_dir.mkdir(exist_ok=True)
        
        # Configuration PostgreSQL depuis DATABASE_URL
        db_url = current_app.config['SQLALCHEMY_DATABASE_URI']
        
        # Support SQLite (dev) et PostgreSQL (prod)
        if db_url.startswith('sqlite'):
            self.db_type = 'sqlite'
            self.db_config = {'path': db_url.replace('sqlite:///', '')}
        else:
            self.db_type = 'postgresql'
            # Format: postgresql://user:password@host:port/dbname
            parts = db_url.replace('postgresql://', '').split('@')
            user_pass = parts[0].split(':')
            host_port_db = parts[1].split('/')
            host_port = host_port_db[0].split(':')
            
            self.db_config = {
                'user': user_pass[0],
                'password': user_pass[1] if len(user_pass) > 1 else '',
                'host': host_port[0],
                'port': host_port[1] if len(host_port) > 1 else '5432',
                'database': host_port_db[1]
            }
    
    # =========================================================================
    # BACKUP DATABASE
    # =========================================================================
    
    def create_backup(self, description=''):
        """Crée une sauvegarde de la base de données"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"nbcm_db_{timestamp}.sql"
        filepath = self.backup_db_dir / filename
        
        if self.db_type == 'sqlite':
            return self._create_sqlite_backup(filepath, timestamp, description)
        else:
            return self._create_postgres_backup(filepath, timestamp, description)
    
    def _create_sqlite_backup(self, filepath, timestamp, description):
        """Backup SQLite (copie simple)"""
        try:
            sqlite_path = self.db_config['path']
            
            # Copie du fichier SQLite
            shutil.copy2(sqlite_path, filepath)
            
            # Compression gzip
            with open(filepath, 'rb') as f_in:
                with gzip.open(f"{filepath}.gz", 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            filepath.unlink()
            
            # Métadonnées
            metadata_file = self.backup_db_dir / f"{filepath.name}.gz.meta"
            with open(metadata_file, 'w') as f:
                f.write(f"timestamp={timestamp}\n")
                f.write(f"description={description}\n")
                f.write(f"db_type=sqlite\n")
                f.write(f"backup_type=db\n")
                f.write(f"size={os.path.getsize(f'{filepath}.gz')}\n")
            
            return {
                'success': True,
                'filename': f"{filepath.name}.gz",
                'size': os.path.getsize(f"{filepath}.gz"),
                'timestamp': timestamp
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _create_postgres_backup(self, filepath, timestamp, description):
        """Backup PostgreSQL avec pg_dump"""
        try:
            env = os.environ.copy()
            env['PGPASSWORD'] = self.db_config['password']
            
            cmd = [
                'pg_dump',
                '-h', self.db_config['host'],
                '-p', self.db_config['port'],
                '-U', self.db_config['user'],
                '-d', self.db_config['database'],
                '--clean',
                '--if-exists',
                '--no-owner',
                '--no-privileges',
                '-f', str(filepath)
            ]
            
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode != 0:
                raise Exception(f"pg_dump failed: {result.stderr}")
            
            # Compression gzip
            with open(filepath, 'rb') as f_in:
                with gzip.open(f"{filepath}.gz", 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            filepath.unlink()
            
            # Métadonnées
            metadata_file = self.backup_db_dir / f"{filepath.name}.gz.meta"
            with open(metadata_file, 'w') as f:
                f.write(f"timestamp={timestamp}\n")
                f.write(f"description={description}\n")
                f.write(f"db_type=postgresql\n")
                f.write(f"backup_type=db\n")
                f.write(f"size={os.path.getsize(f'{filepath}.gz')}\n")
            
            return {
                'success': True,
                'filename': f"{filepath.name}.gz",
                'size': os.path.getsize(f"{filepath}.gz"),
                'timestamp': timestamp
            }
            
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Backup timeout (> 5 minutes)'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # =========================================================================
    # BACKUP FILESYSTEM
    # =========================================================================
    
    def create_fs_backup(self, description='', config=None):
        """Crée une sauvegarde du filesystem"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"nbcm_fs_{timestamp}.tar.gz"
        filepath = self.backup_fs_dir / filename
        
        try:
            # 🔍 DEBUG: Log de la config reçue
            current_app.logger.info(f"🔍 create_fs_backup appelé avec config: {config}")
            
            # Déterminer les répertoires/fichiers à sauvegarder
            if config and 'directories' in config:
                current_app.logger.info(f"🔍 Utilisation config['directories']: {repr(config['directories'])}")
                
                # Gérer les deux formats possibles : string ou liste
                if isinstance(config['directories'], str):
                    items = [d.strip() for d in config['directories'].split('\n') if d.strip()]
                elif isinstance(config['directories'], list):
                    items = [str(d).strip() for d in config['directories'] if str(d).strip()]
                else:
                    current_app.logger.error(f"Format directories invalide: {type(config['directories'])}")
                    items = []
            else:
                current_app.logger.info("🔍 Utilisation des répertoires par défaut")
                # Répertoires par défaut
                items = [
                    '/app/data/db',
                    '/app/data/logs',
                    '/app/data/altaview_auto_import'
                ]
            
            current_app.logger.info(f"🔍 Liste finale de {len(items)} items à sauvegarder: {items}")
            
            # Créer l'archive TAR.GZ avec préservation de la structure
            items_added = []
            with tarfile.open(filepath, "w:gz") as tar:
                for item in items:
                    if os.path.exists(item):
                        # Préserver la structure : /app/models → app/models dans le tar
                        # Enlever le / initial pour éviter les chemins absolus dans l'archive
                        arcname = item.lstrip('/')
                        
                        try:
                            tar.add(item, arcname=arcname)
                            items_added.append(item)
                            current_app.logger.info(f"✅ Ajouté au backup FS: {item} → {arcname}")
                        except Exception as e:
                            current_app.logger.warning(f"❌ Impossible d'ajouter {item}: {e}")
                    else:
                        current_app.logger.warning(f"⚠️  Chemin inexistant (ignoré): {item}")
            
            if not items_added:
                return {'success': False, 'error': 'Aucun fichier/répertoire valide trouvé'}
            
            current_app.logger.info(f"✅ Backup FS créé avec {len(items_added)} items")
            
            # Métadonnées
            metadata_file = self.backup_fs_dir / f"{filepath.name}.meta"
            with open(metadata_file, 'w') as f:
                f.write(f"timestamp={timestamp}\n")
                f.write(f"description={description}\n")
                f.write(f"backup_type=fs\n")
                f.write(f"directories={','.join(items_added)}\n")
                f.write(f"size={os.path.getsize(filepath)}\n")
            
            return {
                'success': True,
                'filename': filepath.name,
                'size': os.path.getsize(filepath),
                'timestamp': timestamp,
                'items_count': len(items_added)
            }
            
        except Exception as e:
            current_app.logger.error(f"Erreur création backup FS: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    # =========================================================================
    # RESTORE DATABASE
    # =========================================================================
    
    def restore_backup(self, filename):
        """Restaure une sauvegarde DB"""
        filepath = self.backup_db_dir / filename
        
        if not filepath.exists():
            return {'success': False, 'error': 'Fichier introuvable'}
        
        # Lire métadonnées pour connaître le type de backup
        meta_file = filepath.with_suffix('.gz.meta')
        db_type = 'postgresql'  # Par défaut
        
        if meta_file.exists():
            with open(meta_file) as f:
                for line in f:
                    if line.startswith('db_type='):
                        db_type = line.strip().split('=')[1]
        
        if db_type == 'sqlite':
            return self._restore_sqlite_backup(filepath)
        else:
            return self._restore_postgres_backup(filepath)
    
    def _restore_sqlite_backup(self, filepath):
        """Restore SQLite"""
        try:
            sqlite_path = self.db_config['path']
            
            # Décompression
            sql_file = filepath.with_suffix('')
            with gzip.open(filepath, 'rb') as f_in:
                with open(sql_file, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            # Copie vers destination
            shutil.copy2(sql_file, sqlite_path)
            sql_file.unlink()
            
            return {'success': True, 'message': 'Base restaurée avec succès'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _restore_postgres_backup(self, filepath):
        """Restore PostgreSQL avec psql"""
        try:
            # Décompression
            sql_file = filepath.with_suffix('')
            with gzip.open(filepath, 'rb') as f_in:
                with open(sql_file, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            env = os.environ.copy()
            env['PGPASSWORD'] = self.db_config['password']
            
            cmd = [
                'psql',
                '-h', self.db_config['host'],
                '-p', self.db_config['port'],
                '-U', self.db_config['user'],
                '-d', self.db_config['database'],
                '-f', str(sql_file)
            ]
            
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=600
            )
            
            sql_file.unlink()
            
            if result.returncode != 0:
                if 'ERROR' in result.stderr:
                    return {'success': False, 'error': result.stderr}
            
            return {'success': True, 'message': 'Base restaurée avec succès'}
            
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Restore timeout (> 10 minutes)'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # =========================================================================
    # RESTORE FILESYSTEM
    # =========================================================================
    
    def restore_fs_backup(self, filename):
        """Restaure une sauvegarde FS (extraction)"""
        filepath = self.backup_fs_dir / filename
        
        if not filepath.exists():
            return {'success': False, 'error': 'Fichier introuvable'}
        
        try:
            # Extraire directement à la racine / pour restaurer la structure
            with tarfile.open(filepath, "r:gz") as tar:
                # Obtenir la liste des membres pour logging
                members = tar.getmembers()
                current_app.logger.info(f"Restauration de {len(members)} fichiers/répertoires")
                
                # Extraire à la racine /
                tar.extractall('/')
            
            return {'success': True, 'message': f'Archive FS extraite: {len(members)} éléments restaurés'}
            
        except Exception as e:
            current_app.logger.error(f"Erreur restauration FS: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    # =========================================================================
    # LISTING & CLEANUP
    # =========================================================================
    
    def list_backups(self):
        """Liste tous les backups disponibles (DB et FS)"""
        result = {
            'db': self._list_backups_dir(self.backup_db_dir, '.sql.gz'),
            'fs': self._list_backups_dir(self.backup_fs_dir, '.tar.gz')
        }
        return result
    
    def _list_backups_dir(self, directory, extension):
        """Liste les backups d'un répertoire donné"""
        backups = []
        
        for file in sorted(directory.glob(f'*{extension}'), reverse=True):
            # ✅ FIX: Utiliser concatenation directe au lieu de with_suffix() pour les extensions multiples
            meta_file = Path(str(file) + '.meta')
            meta = {}
            
            if meta_file.exists():
                with open(meta_file) as f:
                    for line in f:
                        if '=' in line:
                            key, val = line.strip().split('=', 1)
                            meta[key] = val
            
            backups.append({
                'filename': file.name,
                'size': os.path.getsize(file),
                'size_mb': round(os.path.getsize(file) / (1024*1024), 2),
                'timestamp': meta.get('timestamp', 'Unknown'),
                'description': meta.get('description', ''),
                'backup_type': meta.get('backup_type', 'unknown'),
                'date': datetime.fromtimestamp(file.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            })
        
        return backups
    
    def cleanup_old_backups(self, backup_type, retention):
        """
        Supprime les anciens backups selon la politique de rétention.
        
        Args:
            backup_type: 'db' ou 'fs'
            retention: nombre de backups à conserver
        """
        try:
            directory = self.backup_db_dir if backup_type == 'db' else self.backup_fs_dir
            extension = '.sql.gz' if backup_type == 'db' else '.tar.gz'
            
            # Lister tous les backups
            backups = sorted(directory.glob(f'*{extension}'), key=lambda x: x.stat().st_mtime, reverse=True)
            
            # Supprimer ceux au-delà de la rétention
            deleted = 0
            for backup_file in backups[retention:]:
                meta_file = backup_file.with_suffix(f'{extension}.meta' if extension == '.sql.gz' else '.meta')
                
                backup_file.unlink()
                if meta_file.exists():
                    meta_file.unlink()
                
                deleted += 1
            
            return {'success': True, 'deleted': deleted}
            
        except Exception as e:
            return {'success': False, 'error': str(e), 'deleted': 0}
    
    def delete_backup(self, filename):
        """Supprime un backup spécifique"""
        # Essayer dans les deux répertoires
        for directory in [self.backup_db_dir, self.backup_fs_dir]:
            filepath = directory / filename
            
            if filepath.exists():
                try:
                    # ✅ FIX: Utiliser concatenation directe pour trouver le fichier meta
                    meta_file = Path(str(filepath) + '.meta')
                    
                    filepath.unlink()
                    if meta_file and meta_file.exists():
                        meta_file.unlink()
                    
                    return {'success': True}
                except Exception as e:
                    return {'success': False, 'error': str(e)}
        
        return {'success': False, 'error': 'Fichier introuvable'}
