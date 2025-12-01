"""
NBCM V3.0 - Service de purge automatique
Nettoie les fichiers dans data/altaview_auto_import/processed/ après 48h
"""
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class CleanupService:
    """Service de nettoyage automatique des fichiers"""
    
    def __init__(self, base_dir='/app/data/altaview_auto_import/processed', retention_hours=48):
        """
        Initialise le service de cleanup
        
        Args:
            base_dir: Répertoire à nettoyer
            retention_hours: Durée de rétention en heures (défaut: 48h)
        """
        self.base_dir = Path(base_dir)
        self.retention_hours = retention_hours
        self.retention_seconds = retention_hours * 3600
        
    def cleanup_old_files(self):
        """
        Supprime les fichiers plus anciens que la durée de rétention
        
        Returns:
            dict: Statistiques de nettoyage
        """
        if not self.base_dir.exists():
            logger.warning(f"Répertoire {self.base_dir} n'existe pas")
            return {
                'status': 'error',
                'message': f'Répertoire {self.base_dir} introuvable',
                'deleted': 0,
                'size_freed': 0
            }
        
        stats = {
            'status': 'success',
            'deleted': 0,
            'size_freed': 0,  # en bytes
            'errors': [],
            'deleted_files': []
        }
        
        cutoff_time = time.time() - self.retention_seconds
        cutoff_datetime = datetime.now() - timedelta(hours=self.retention_hours)
        
        logger.info(f"🧹 Début nettoyage fichiers > {self.retention_hours}h dans {self.base_dir}")
        logger.info(f"   Date limite : {cutoff_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            # Parcourir tous les fichiers
            for file_path in self.base_dir.rglob('*'):
                if not file_path.is_file():
                    continue
                
                try:
                    # Vérifier l'âge du fichier
                    file_mtime = file_path.stat().st_mtime
                    
                    if file_mtime < cutoff_time:
                        # Fichier trop ancien, le supprimer
                        file_size = file_path.stat().st_size
                        file_age_hours = (time.time() - file_mtime) / 3600
                        
                        logger.info(f"   Suppression: {file_path.name} (âge: {file_age_hours:.1f}h, taille: {file_size} bytes)")
                        
                        file_path.unlink()
                        
                        stats['deleted'] += 1
                        stats['size_freed'] += file_size
                        stats['deleted_files'].append({
                            'filename': file_path.name,
                            'age_hours': round(file_age_hours, 1),
                            'size_bytes': file_size
                        })
                        
                except Exception as e:
                    error_msg = f"Erreur suppression {file_path.name}: {str(e)}"
                    logger.error(f"   ❌ {error_msg}")
                    stats['errors'].append(error_msg)
            
            # Convertir taille en MB pour lisibilité
            stats['size_freed_mb'] = round(stats['size_freed'] / (1024 * 1024), 2)
            
            if stats['deleted'] > 0:
                logger.info(f"✅ Nettoyage terminé : {stats['deleted']} fichiers supprimés ({stats['size_freed_mb']} MB libérés)")
            else:
                logger.info(f"✅ Nettoyage terminé : Aucun fichier à supprimer")
            
            return stats
            
        except Exception as e:
            error_msg = f"Erreur lors du nettoyage: {str(e)}"
            logger.error(f"❌ {error_msg}")
            stats['status'] = 'error'
            stats['message'] = error_msg
            return stats
    
    def get_directory_stats(self):
        """
        Récupère les statistiques du répertoire
        
        Returns:
            dict: Statistiques (nb fichiers, taille totale, fichiers éligibles suppression)
        """
        if not self.base_dir.exists():
            return {
                'exists': False,
                'total_files': 0,
                'total_size': 0,
                'eligible_for_deletion': 0
            }
        
        stats = {
            'exists': True,
            'total_files': 0,
            'total_size': 0,
            'eligible_for_deletion': 0,
            'eligible_size': 0
        }
        
        cutoff_time = time.time() - self.retention_seconds
        
        for file_path in self.base_dir.rglob('*'):
            if not file_path.is_file():
                continue
            
            file_size = file_path.stat().st_size
            stats['total_files'] += 1
            stats['total_size'] += file_size
            
            if file_path.stat().st_mtime < cutoff_time:
                stats['eligible_for_deletion'] += 1
                stats['eligible_size'] += file_size
        
        # Convertir en MB
        stats['total_size_mb'] = round(stats['total_size'] / (1024 * 1024), 2)
        stats['eligible_size_mb'] = round(stats['eligible_size'] / (1024 * 1024), 2)
        
        return stats


# Instance globale
cleanup_service = CleanupService()


def schedule_cleanup_job(scheduler):
    """
    Planifie le job de nettoyage automatique
    
    Args:
        scheduler: Instance APScheduler
    """
    try:
        # Exécuter tous les jours à 3h du matin
        scheduler.add_job(
            id='cleanup_processed_files',
            func=cleanup_service.cleanup_old_files,
            trigger='cron',
            hour=3,
            minute=0,
            name='Nettoyage fichiers processed/ > 48h'
        )
        logger.info("✅ Job de nettoyage automatique planifié (tous les jours à 3h)")
    except Exception as e:
        logger.error(f"❌ Erreur planification cleanup: {e}")
