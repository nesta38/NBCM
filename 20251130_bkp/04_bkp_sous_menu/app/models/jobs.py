"""
NBCM V2.5 - Modèle Jobs Altaview
Gestion des jobs de backup
"""
from datetime import datetime

from app import db


class JobAltaview(db.Model):
    """Jobs de backup Altaview"""
    __tablename__ = 'job_altaview'
    
    id = db.Column(db.Integer, primary_key=True)
    hostname = db.Column(db.String(255), nullable=False, index=True)
    backup_time = db.Column(db.DateTime, nullable=False, index=True)
    job_id = db.Column(db.String(50), index=True)
    policy_name = db.Column(db.String(100))
    schedule_name = db.Column(db.String(100))
    status = db.Column(db.String(50), index=True)
    taille_gb = db.Column(db.Float)
    duree_minutes = db.Column(db.Integer)
    date_import = db.Column(db.DateTime, default=datetime.now, index=True)
    
    # Champs supplémentaires
    media_server = db.Column(db.String(100))
    storage_unit = db.Column(db.String(100))
    error_message = db.Column(db.Text)
    
    def is_success(self):
        """Vérifie si le job est un succès (sans warnings)"""
        if not self.status:
            return True
        try:
            status_num = int(self.status)
            return status_num == 0  # 0 = OK uniquement
        except ValueError:
            return self.status.upper() in ['SUCCESS', 'OK', '']
    
    def is_warning(self):
        """Vérifie si le job est un warning"""
        if not self.status:
            return False
        try:
            return int(self.status) == 1
        except ValueError:
            return self.status.upper() == 'WARNING'
    
    def is_error(self):
        """Vérifie si le job est en erreur"""
        if not self.status:
            return False
        try:
            return int(self.status) >= 2
        except ValueError:
            return self.status.upper() in ['ERROR', 'FAILED', 'FAILURE']
    
    def get_status_class(self):
        """Retourne la classe CSS pour le statut"""
        if self.is_success() and not self.is_warning():
            return 'success'
        elif self.is_warning():
            return 'warning'
        elif self.is_error():
            return 'danger'
        return 'secondary'
    
    def get_status_icon(self):
        """Retourne l'icône Bootstrap pour le statut"""
        if self.is_success() and not self.is_warning():
            return 'bi-check-circle-fill'
        elif self.is_warning():
            return 'bi-exclamation-triangle-fill'
        elif self.is_error():
            return 'bi-x-circle-fill'
        return 'bi-question-circle'
    
    def to_dict(self):
        """Sérialisation pour l'API"""
        return {
            'id': self.id,
            'hostname': self.hostname,
            'backup_time': self.backup_time.isoformat() if self.backup_time else None,
            'job_id': self.job_id,
            'policy_name': self.policy_name,
            'schedule_name': self.schedule_name,
            'status': self.status,
            'status_class': self.get_status_class(),
            'is_success': self.is_success(),
            'taille_gb': self.taille_gb,
            'duree_minutes': self.duree_minutes,
            'media_server': self.media_server,
            'storage_unit': self.storage_unit,
            'error_message': self.error_message,
            'date_import': self.date_import.isoformat() if self.date_import else None
        }
    
    def __repr__(self):
        return f'<Job {self.hostname} @ {self.backup_time}>'


class ImportHistory(db.Model):
    """Historique des imports"""
    __tablename__ = 'import_history'
    
    id = db.Column(db.Integer, primary_key=True)
    type_import = db.Column(db.String(20), index=True)  # cmdb, altaview, altaview_api, imap
    filename = db.Column(db.String(255))
    nb_lignes = db.Column(db.Integer)
    statut = db.Column(db.String(20))  # success, error, partial
    message = db.Column(db.Text)
    utilisateur = db.Column(db.String(100), default='admin')
    date_import = db.Column(db.DateTime, default=datetime.now, index=True)
    
    # Détails supplémentaires
    nb_created = db.Column(db.Integer, default=0)
    nb_updated = db.Column(db.Integer, default=0)
    nb_skipped = db.Column(db.Integer, default=0)
    nb_errors = db.Column(db.Integer, default=0)
    duration_seconds = db.Column(db.Float)
    details_json = db.Column(db.Text)
    
    def save(self):
        """Sauvegarde l'entrée"""
        db.session.add(self)
        db.session.commit()
        return self
    
    def to_dict(self):
        """Sérialisation pour l'API"""
        return {
            'id': self.id,
            'type_import': self.type_import,
            'filename': self.filename,
            'nb_lignes': self.nb_lignes,
            'statut': self.statut,
            'message': self.message,
            'utilisateur': self.utilisateur,
            'date_import': self.date_import.isoformat() if self.date_import else None,
            'nb_created': self.nb_created,
            'nb_updated': self.nb_updated,
            'nb_skipped': self.nb_skipped,
            'nb_errors': self.nb_errors,
            'duration_seconds': self.duration_seconds
        }
    
    def __repr__(self):
        return f'<Import {self.type_import} @ {self.date_import}>'
