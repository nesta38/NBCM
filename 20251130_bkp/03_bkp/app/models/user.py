"""
NBCM V2.5 - Modèle User
Gestion de l'authentification
"""
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

from app import db, login_manager


class User(UserMixin, db.Model):
    """Modèle utilisateur avec authentification"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='viewer', nullable=False)  # admin, operator, viewer
    
    # Infos profil
    display_name = db.Column(db.String(100))
    avatar_url = db.Column(db.String(255))
    
    # États
    is_active = db.Column(db.Boolean, default=True)
    is_verified = db.Column(db.Boolean, default=False)
    
    # Dates
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    last_login = db.Column(db.DateTime)
    
    # Préférences
    language = db.Column(db.String(5), default='en')  # Default language: English
    theme = db.Column(db.String(10), default='light')
    
    # API
    api_key = db.Column(db.String(64), unique=True, index=True)
    api_key_created_at = db.Column(db.DateTime)
    
    def set_password(self, password):
        """Hash et stocke le mot de passe"""
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    
    def check_password(self, password):
        """Vérifie le mot de passe"""
        return check_password_hash(self.password_hash, password)
    
    def generate_api_key(self):
        """Génère une nouvelle clé API"""
        import secrets
        self.api_key = secrets.token_hex(32)
        self.api_key_created_at = datetime.now()
        return self.api_key
    
    def is_admin(self):
        """Vérifie si l'utilisateur est admin"""
        return self.role == 'admin'
    
    def is_operator(self):
        """Vérifie si l'utilisateur est opérateur ou admin"""
        return self.role in ['admin', 'operator']
    
    def can_edit(self):
        """Vérifie si l'utilisateur peut modifier les données"""
        return self.role in ['admin', 'operator']
    
    def can_admin(self):
        """Vérifie si l'utilisateur peut accéder à l'administration"""
        return self.role == 'admin'
    
    def update_last_login(self):
        """Met à jour la date de dernière connexion"""
        self.last_login = datetime.now()
        db.session.commit()
    
    def to_dict(self):
        """Sérialisation pour l'API"""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'display_name': self.display_name,
            'is_active': self.is_active,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'language': self.language,
            'theme': self.theme
        }
    
    def __repr__(self):
        return f'<User {self.username}>'


class UserSession(db.Model):
    """Historique des sessions utilisateur"""
    __tablename__ = 'user_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    session_token = db.Column(db.String(64), unique=True, index=True)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.now)
    expires_at = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    
    user = db.relationship('User', backref=db.backref('sessions', lazy='dynamic'))


class AuditLog(db.Model):
    """Journal d'audit des actions"""
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    action = db.Column(db.String(50), nullable=False)  # login, logout, create, update, delete
    resource_type = db.Column(db.String(50))  # cmdb, job, config, user
    resource_id = db.Column(db.Integer)
    details = db.Column(db.Text)  # JSON avec détails
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=datetime.now, index=True)
    
    user = db.relationship('User', backref=db.backref('audit_logs', lazy='dynamic'))
    
    @classmethod
    def log(cls, user_id, action, resource_type=None, resource_id=None, details=None, ip_address=None):
        """Crée une entrée d'audit"""
        import json
        entry = cls(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=json.dumps(details) if details else None,
            ip_address=ip_address
        )
        db.session.add(entry)
        db.session.commit()
        return entry


@login_manager.user_loader
def load_user(user_id):
    """Callback pour Flask-Login"""
    return User.query.get(int(user_id))


def create_default_admin():
    """Crée l'utilisateur admin par défaut si inexistant"""
    import os
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            email=os.getenv('ADMIN_EMAIL', 'admin@nbcm.local'),
            role='admin',
            display_name='Administrateur',
            is_active=True,
            is_verified=True
        )
        admin.set_password(os.getenv('ADMIN_PASSWORD', 'admin123'))
        admin.generate_api_key()
        db.session.add(admin)
        db.session.commit()
        return admin
    return None
