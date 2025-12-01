"""
NBCM V2.5 - Modèle CMDB
Référentiel des serveurs
"""
from datetime import datetime

from app import db


class ReferentielCMDB(db.Model):
    """Référentiel des serveurs CMDB"""
    __tablename__ = 'referentiel_cmdb'
    
    id = db.Column(db.Integer, primary_key=True)
    hostname = db.Column(db.String(255), unique=True, nullable=False, index=True)
    backup_enabled = db.Column(db.Boolean, default=True, nullable=False, index=True)
    
    # Désactivation temporaire
    date_debut_desactivation = db.Column(db.DateTime, nullable=True)
    date_fin_desactivation = db.Column(db.DateTime, nullable=True)
    raison_desactivation = db.Column(db.String(500), nullable=True)
    
    # Métadonnées
    date_creation = db.Column(db.DateTime, default=datetime.now)
    date_modification = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    modifie_par = db.Column(db.String(100), default='admin')
    commentaire = db.Column(db.Text, nullable=True)
    
    # Informations supplémentaires
    environnement = db.Column(db.String(50))  # PROD, DEV, TEST, DR
    criticite = db.Column(db.String(20))  # CRITICAL, HIGH, MEDIUM, LOW
    application = db.Column(db.String(100))
    responsable = db.Column(db.String(100))
    tags = db.Column(db.Text)  # JSON array
    
    def est_desactive_temporairement(self):
        """Vérifie si le serveur est temporairement désactivé"""
        if not self.date_debut_desactivation or not self.date_fin_desactivation:
            return False
        now = datetime.now()
        return self.date_debut_desactivation <= now <= self.date_fin_desactivation
    
    def desactiver_temporairement(self, duree_jours, raison, utilisateur='admin'):
        """Désactive temporairement le serveur"""
        from datetime import timedelta
        self.date_debut_desactivation = datetime.now()
        self.date_fin_desactivation = datetime.now() + timedelta(days=duree_jours)
        self.raison_desactivation = raison
        self.modifie_par = utilisateur
        self.date_modification = datetime.now()
    
    def reactiver(self, utilisateur='admin'):
        """Réactive le serveur (FIX BUG V2.2)"""
        self.date_debut_desactivation = None
        self.date_fin_desactivation = None
        self.raison_desactivation = None
        self.modifie_par = utilisateur
        self.date_modification = datetime.now()
    
    def get_tags_list(self):
        """Retourne les tags sous forme de liste"""
        import json
        try:
            return json.loads(self.tags) if self.tags else []
        except:
            return []
    
    def set_tags_list(self, tags_list):
        """Définit les tags depuis une liste"""
        import json
        self.tags = json.dumps(tags_list)
    
    def to_dict(self):
        """Sérialisation pour l'API"""
        return {
            'id': self.id,
            'hostname': self.hostname,
            'backup_enabled': self.backup_enabled,
            'is_temporarily_disabled': self.est_desactive_temporairement(),
            'date_debut_desactivation': self.date_debut_desactivation.isoformat() if self.date_debut_desactivation else None,
            'date_fin_desactivation': self.date_fin_desactivation.isoformat() if self.date_fin_desactivation else None,
            'raison_desactivation': self.raison_desactivation,
            'environnement': self.environnement,
            'criticite': self.criticite,
            'application': self.application,
            'responsable': self.responsable,
            'tags': self.get_tags_list(),
            'commentaire': self.commentaire,
            'date_creation': self.date_creation.isoformat() if self.date_creation else None,
            'date_modification': self.date_modification.isoformat() if self.date_modification else None,
            'modifie_par': self.modifie_par
        }
    
    def __repr__(self):
        return f'<CMDB {self.hostname}>'


class CMDBHistory(db.Model):
    """Historique des modifications CMDB"""
    __tablename__ = 'cmdb_history'
    
    id = db.Column(db.Integer, primary_key=True)
    cmdb_id = db.Column(db.Integer, db.ForeignKey('referentiel_cmdb.id'), nullable=False)
    action = db.Column(db.String(20), nullable=False)  # create, update, delete
    field_name = db.Column(db.String(50))
    old_value = db.Column(db.Text)
    new_value = db.Column(db.Text)
    modified_by = db.Column(db.String(100))
    modified_at = db.Column(db.DateTime, default=datetime.now)
    
    cmdb = db.relationship('ReferentielCMDB', backref=db.backref('history', lazy='dynamic'))
    
    @classmethod
    def log_change(cls, cmdb_id, action, field_name=None, old_value=None, new_value=None, modified_by='system'):
        """Enregistre un changement"""
        entry = cls(
            cmdb_id=cmdb_id,
            action=action,
            field_name=field_name,
            old_value=str(old_value) if old_value is not None else None,
            new_value=str(new_value) if new_value is not None else None,
            modified_by=modified_by
        )
        db.session.add(entry)
        return entry
