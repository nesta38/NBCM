#!/usr/bin/env python3
"""
Script pour réactiver le compte admin et corriger les problèmes d'authentification.
À exécuter depuis le container Docker:
    docker exec -it nbcm-v25 python fix_admin.py
"""
import sys
sys.path.insert(0, '/app')

from app import create_app, db
from app.models.auth import User

def fix_admin():
    app = create_app()
    
    with app.app_context():
        # Trouver le compte admin
        admin = User.query.filter_by(username='admin').first()
        
        if not admin:
            print("❌ Compte admin non trouvé!")
            print("Création d'un nouveau compte admin...")
            
            admin = User(
                username='admin',
                email='admin@localhost',
                display_name='Administrateur',
                role='admin',
                is_active=True
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("✅ Compte admin créé avec succès!")
            print("   Username: admin")
            print("   Password: admin123")
            return
        
        print(f"📋 État actuel du compte admin:")
        print(f"   - ID: {admin.id}")
        print(f"   - Username: {admin.username}")
        print(f"   - Email: {admin.email}")
        print(f"   - Role: {admin.role}")
        print(f"   - Active: {admin.is_active}")
        print(f"   - Last login: {admin.last_login}")
        
        # Corrections
        changes = []
        
        if not admin.is_active:
            admin.is_active = True
            changes.append("Réactivé")
        
        if admin.role != 'admin':
            admin.role = 'admin'
            changes.append("Rôle remis à 'admin'")
        
        if changes:
            db.session.commit()
            print(f"\n✅ Corrections appliquées: {', '.join(changes)}")
        else:
            print("\n✅ Le compte admin est déjà correctement configuré.")
        
        # Option pour réinitialiser le mot de passe
        reset_pwd = input("\nVoulez-vous réinitialiser le mot de passe à 'admin123'? (o/N): ")
        if reset_pwd.lower() in ['o', 'oui', 'y', 'yes']:
            admin.set_password('admin123')
            db.session.commit()
            print("✅ Mot de passe réinitialisé à 'admin123'")
        
        print("\n📋 État final du compte admin:")
        print(f"   - Active: {admin.is_active}")
        print(f"   - Role: {admin.role}")

if __name__ == '__main__':
    fix_admin()
