"""
Service de sauvegarde/restauration PostgreSQL
Permet de créer, restaurer et gérer les backups de la base de données
"""
import os
import subprocess
from datetime import datetime
from pathlib import Path
import gzip
import shutil
from flask import current_app

class BackupService:
    """Service de sauvegarde/restauration PostgreSQL"""
    
    def __init__(self):
        self.backup_dir = Path(current_app.config.get('BACKUP_DIR', 'backups'))
        self.backup_dir.mkdir(exist_ok=True)
        
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
    
    def create_backup(self, description=''):
        """Crée une sauvegarde de la base de données"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"nbcm_backup_{timestamp}.sql"
        filepath = self.backup_dir / filename
        
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
            metadata_file = self.backup_dir / f"{filepath.name}.gz.meta"
            with open(metadata_file, 'w') as f:
                f.write(f"timestamp={timestamp}\n")
                f.write(f"description={description}\n")
                f.write(f"db_type=sqlite\n")
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
            metadata_file = self.backup_dir / f"{filepath.name}.gz.meta"
            with open(metadata_file, 'w') as f:
                f.write(f"timestamp={timestamp}\n")
                f.write(f"description={description}\n")
                f.write(f"db_type=postgresql\n")
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
    
    def restore_backup(self, filename):
        """Restaure une sauvegarde"""
        filepath = self.backup_dir / filename
        
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
    
    def list_backups(self):
        """Liste tous les backups disponibles"""
        backups = []
        
        for file in sorted(self.backup_dir.glob('*.sql.gz'), reverse=True):
            meta_file = file.with_suffix('.gz.meta')
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
                'db_type': meta.get('db_type', 'unknown'),
                'date': datetime.fromtimestamp(file.stat().st_mtime)
            })
        
        return backups
    
    def delete_backup(self, filename):
        """Supprime un backup"""
        filepath = self.backup_dir / filename
        meta_file = filepath.with_suffix('.gz.meta')
        
        try:
            if filepath.exists():
                filepath.unlink()
            if meta_file.exists():
                meta_file.unlink()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}
