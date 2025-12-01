"""
NBCM V2.5 - Routes Authentification
Login, logout, gestion de session
"""
from datetime import datetime
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user

from app import db
from app.models.user import User, AuditLog, create_default_admin

auth_bp = Blueprint('auth', __name__)


def admin_required(f):
    """Décorateur pour restreindre l'accès aux admins"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin():
            flash('Accès réservé aux administrateurs.', 'danger')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated_function


def operator_required(f):
    """Décorateur pour restreindre l'accès aux opérateurs et admins"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_operator():
            flash('Accès réservé aux opérateurs.', 'danger')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated_function


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Page de connexion"""
    # Créer l'admin par défaut si nécessaire
    create_default_admin()
    
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember', False)
        
        user = User.query.filter(
            (User.username == username) | (User.email == username)
        ).first()
        
        if user and user.check_password(password):
            if not user.is_active:
                flash('Votre compte est désactivé. Contactez l\'administrateur.', 'warning')
                return render_template('auth/login.html')
            
            login_user(user, remember=bool(remember))
            user.update_last_login()
            
            # Audit log
            AuditLog.log(
                user_id=user.id,
                action='login',
                details={'username': username},
                ip_address=request.remote_addr
            )
            
            flash(f'Bienvenue, {user.display_name or user.username} !', 'success')
            
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('dashboard.index'))
        else:
            flash('Identifiants incorrects.', 'danger')
            
            # Log tentative échouée
            AuditLog.log(
                user_id=None,
                action='login_failed',
                details={'username': username},
                ip_address=request.remote_addr
            )
    
    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """Déconnexion"""
    AuditLog.log(
        user_id=current_user.id,
        action='logout',
        ip_address=request.remote_addr
    )
    
    logout_user()
    flash('Vous avez été déconnecté.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/change-language/<lang>')
@login_required
def change_language(lang):
    """Changer la langue de l'utilisateur"""
    if lang in ['en', 'fr', 'pl']:
        current_user.language = lang
        db.session.commit()
        flash('Langue mise à jour.', 'success')
    return redirect(request.referrer or url_for('dashboard.index'))


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """Profil utilisateur"""
    if request.method == 'POST':
        # Simple form update (includes language)
        if 'new_password' not in request.form or not request.form.get('new_password'):
            current_user.display_name = request.form.get('display_name', '').strip()
            current_user.email = request.form.get('email', '').strip()
            current_user.language = request.form.get('language', 'en')
            db.session.commit()
            flash('Profil mis à jour.', 'success')
        
        # Password change
        elif request.form.get('new_password'):
            new_password = request.form.get('new_password', '').strip()
            confirm_password = request.form.get('confirm_password', '').strip()
            
            if new_password != confirm_password:
                flash('Les nouveaux mots de passe ne correspondent pas.', 'danger')
            elif len(new_password) < 6:
                flash('Le mot de passe doit contenir au moins 6 caractères.', 'danger')
            else:
                current_user.set_password(new_password)
                db.session.commit()
                flash('Mot de passe modifié avec succès.', 'success')
        
        # API key regeneration
        if request.form.get('regenerate_api_key'):
            new_key = current_user.generate_api_key()
            db.session.commit()
            flash(f'Nouvelle clé API générée: {new_key[:20]}...', 'success')
    
    return render_template('auth/profile.html', user=current_user)


@auth_bp.route('/users')
@admin_required
def users():
    """Liste des utilisateurs (admin only)"""
    all_users = User.query.order_by(User.username).all()
    return render_template('auth/users.html', users=all_users)


@auth_bp.route('/users/add', methods=['GET', 'POST'])
@admin_required
def add_user():
    """Ajouter un utilisateur"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'viewer')
        display_name = request.form.get('display_name', '').strip()
        
        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash('Un utilisateur avec ce nom ou email existe déjà.', 'danger')
        else:
            user = User(
                username=username,
                email=email,
                role=role,
                display_name=display_name,
                is_active=True
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            
            AuditLog.log(
                user_id=current_user.id,
                action='create',
                resource_type='user',
                resource_id=user.id,
                details={'username': username, 'role': role},
                ip_address=request.remote_addr
            )
            
            flash(f'Utilisateur {username} créé avec succès.', 'success')
            return redirect(url_for('auth.users'))
    
    return render_template('auth/add_user.html')


@auth_bp.route('/users/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def edit_user(id):
    """Modifier un utilisateur"""
    user = User.query.get_or_404(id)
    
    if request.method == 'POST':
        user.email = request.form.get('email', '').strip()
        user.display_name = request.form.get('display_name', '').strip()
        
        # Protéger le compte admin - ne pas modifier le rôle ni le statut
        if user.username != 'admin':
            user.role = request.form.get('role', 'viewer')
            user.is_active = request.form.get('is_active') == 'on'
        else:
            # S'assurer que l'admin reste toujours actif et admin
            user.role = 'admin'
            user.is_active = True
        
        new_password = request.form.get('new_password', '').strip()
        if new_password:
            confirm_password = request.form.get('confirm_password', '').strip()
            if new_password != confirm_password:
                flash('Les mots de passe ne correspondent pas.', 'danger')
                return render_template('auth/edit_user.html', user=user)
            user.set_password(new_password)
        
        db.session.commit()
        
        AuditLog.log(
            user_id=current_user.id,
            action='update',
            resource_type='user',
            resource_id=user.id,
            ip_address=request.remote_addr
        )
        
        flash('Utilisateur mis à jour.', 'success')
        return redirect(url_for('auth.users'))
    
    return render_template('auth/edit_user.html', user=user)


@auth_bp.route('/users/delete/<int:id>', methods=['POST'])
@admin_required
def delete_user(id):
    """Supprimer un utilisateur"""
    user = User.query.get_or_404(id)
    
    if user.id == current_user.id:
        flash('Vous ne pouvez pas supprimer votre propre compte.', 'danger')
    else:
        AuditLog.log(
            user_id=current_user.id,
            action='delete',
            resource_type='user',
            resource_id=user.id,
            details={'username': user.username},
            ip_address=request.remote_addr
        )
        
        db.session.delete(user)
        db.session.commit()
        flash('Utilisateur supprimé.', 'success')
    
    return redirect(url_for('auth.users'))
