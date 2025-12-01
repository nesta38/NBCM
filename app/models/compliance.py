"""
NBCM V2.5 - Modèles Conformité et Archives
"""
from datetime import datetime
import json

from app import db


class HistoriqueConformite(db.Model):
    """Historique des calculs de conformité"""
    __tablename__ = 'historique_conformite'
    
    id = db.Column(db.Integer, primary_key=True)
    date_calcul = db.Column(db.DateTime, default=datetime.now, index=True)
    total_cmdb = db.Column(db.Integer)
    total_backup_enabled = db.Column(db.Integer)
    total_jobs = db.Column(db.Integer)
    nb_conformes = db.Column(db.Integer)
    nb_non_conformes = db.Column(db.Integer)
    nb_non_references = db.Column(db.Integer)
    taux_conformite = db.Column(db.Float)
    details_json = db.Column(db.Text)
    
    def get_details(self):
        """Retourne les détails en dict"""
        try:
            return json.loads(self.details_json) if self.details_json else {}
        except:
            return {}
    
    def to_dict(self):
        """Sérialisation pour l'API"""
        return {
            'id': self.id,
            'date_calcul': self.date_calcul.isoformat() if self.date_calcul else None,
            'total_cmdb': self.total_cmdb,
            'total_backup_enabled': self.total_backup_enabled,
            'total_jobs': self.total_jobs,
            'nb_conformes': self.nb_conformes,
            'nb_non_conformes': self.nb_non_conformes,
            'nb_non_references': self.nb_non_references,
            'taux_conformite': self.taux_conformite
        }


class ArchiveConformite(db.Model):
    """Archives quotidiennes de conformité"""
    __tablename__ = 'archive_conformite'
    
    id = db.Column(db.Integer, primary_key=True)
    date_archivage = db.Column(db.DateTime, default=datetime.now, nullable=False, index=True)
    date_debut_periode = db.Column(db.DateTime, nullable=False)
    date_fin_periode = db.Column(db.DateTime, nullable=False)
    
    # Statistiques
    total_cmdb = db.Column(db.Integer)
    total_backup_enabled = db.Column(db.Integer)
    total_jobs = db.Column(db.Integer)
    nb_conformes = db.Column(db.Integer)
    nb_non_conformes = db.Column(db.Integer)
    nb_non_references = db.Column(db.Integer)
    taux_conformite = db.Column(db.Float)
    
    # Listes (JSON)
    liste_conformes = db.Column(db.Text)
    liste_non_conformes = db.Column(db.Text)
    liste_non_references = db.Column(db.Text)
    donnees_json = db.Column(db.Text)
    
    def get_liste_conformes(self):
        try:
            return json.loads(self.liste_conformes) if self.liste_conformes else []
        except:
            return []
    
    def get_liste_non_conformes(self):
        try:
            return json.loads(self.liste_non_conformes) if self.liste_non_conformes else []
        except:
            return []
    
    def get_liste_non_references(self):
        try:
            return json.loads(self.liste_non_references) if self.liste_non_references else []
        except:
            return []
    
    def to_dict(self):
        """Sérialisation pour l'API"""
        return {
            'id': self.id,
            'date_archivage': self.date_archivage.isoformat() if self.date_archivage else None,
            'date_debut_periode': self.date_debut_periode.isoformat() if self.date_debut_periode else None,
            'date_fin_periode': self.date_fin_periode.isoformat() if self.date_fin_periode else None,
            'total_cmdb': self.total_cmdb,
            'total_backup_enabled': self.total_backup_enabled,
            'total_jobs': self.total_jobs,
            'nb_conformes': self.nb_conformes,
            'nb_non_conformes': self.nb_non_conformes,
            'nb_non_references': self.nb_non_references,
            'taux_conformite': self.taux_conformite,
            'liste_conformes': self.get_liste_conformes(),
            'liste_non_conformes': self.get_liste_non_conformes(),
            'liste_non_references': self.get_liste_non_references()
        }


class Recipient(db.Model):
    """Destinataires des rapports"""
    __tablename__ = 'recipients'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    active = db.Column(db.Boolean, default=True)
    schedule_time = db.Column(db.String(5), default='08:00', nullable=False)
    
    # Préférences
    report_format = db.Column(db.String(10), default='both')  # pdf, excel, both
    include_details = db.Column(db.Boolean, default=True)
    language = db.Column(db.String(5), default='fr')
    
    # Dates
    created_at = db.Column(db.DateTime, default=datetime.now)
    last_sent = db.Column(db.DateTime)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'active': self.active,
            'schedule_time': self.schedule_time,
            'report_format': self.report_format,
            'include_details': self.include_details,
            'language': self.language,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_sent': self.last_sent.isoformat() if self.last_sent else None
        }


class Configuration(db.Model):
    """Configuration système"""
    __tablename__ = 'configuration'
    
    id = db.Column(db.Integer, primary_key=True)
    cle = db.Column(db.String(100), unique=True, nullable=False, index=True)
    valeur = db.Column(db.Text)
    description = db.Column(db.String(500))
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    updated_by = db.Column(db.String(100))
    
    def get_value(self):
        """Retourne la valeur désérialisée"""
        try:
            return json.loads(self.valeur)
        except:
            return self.valeur
    
    def set_value(self, value):
        """Sérialise et stocke la valeur"""
        if isinstance(value, (dict, list)):
            self.valeur = json.dumps(value)
        else:
            self.valeur = str(value)
