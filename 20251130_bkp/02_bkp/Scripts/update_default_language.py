"""
Script de migration pour mettre à jour la langue par défaut des utilisateurs
Passe tous les utilisateurs existants à 'en' (English) par défaut
"""
import os
import sys

# Ajouter le répertoire parent au path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.user import User

def update_default_language():
    """Met à jour la langue par défaut de tous les utilisateurs vers 'en'"""
    app = create_app()
    
    with app.app_context():
        # Compter les utilisateurs
        total = User.query.count()
        print(f"Nombre total d'utilisateurs : {total}")
        
        if total == 0:
            print("Aucun utilisateur trouvé.")
            return
        
        # Mettre à jour tous les utilisateurs qui ont 'fr' ou NULL comme langue
        users_to_update = User.query.filter(
            (User.language == 'fr') | (User.language == None)
        ).all()
        
        print(f"Utilisateurs à mettre à jour : {len(users_to_update)}")
        
        for user in users_to_update:
            old_lang = user.language
            user.language = 'en'
            print(f"  - {user.username}: {old_lang} → en")
        
        # Sauvegarder les changements
        db.session.commit()
        print(f"\n✅ Migration terminée avec succès !")
        print(f"   {len(users_to_update)} utilisateur(s) mis à jour.")

if __name__ == '__main__':
    update_default_language()
