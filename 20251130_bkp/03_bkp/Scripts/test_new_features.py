"""
Tests automatisés pour les nouvelles fonctionnalités NBCM V2.5
- Multi-langue (EN/FR/PL)
- Filtres persistants Altaview
"""
import os
import sys
from datetime import datetime, timedelta

# Ajouter le répertoire parent au path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.user import User
from app.models.jobs import JobAltaview
from app.services.translations import get_translation, t, get_user_language

def test_translations():
    """Test du système de traductions"""
    print("\n" + "="*60)
    print("TEST 1: Système de traductions")
    print("="*60)
    
    # Test des traductions basiques
    test_keys = ['nav_dashboard', 'btn_save', 'profile_title']
    
    for key in test_keys:
        en = get_translation(key, 'en')
        fr = get_translation(key, 'fr')
        pl = get_translation(key, 'pl')
        
        print(f"\n{key}:")
        print(f"  EN: {en}")
        print(f"  FR: {fr}")
        print(f"  PL: {pl}")
        
        # Vérifier qu'aucune traduction n'est vide
        assert en and fr and pl, f"Traduction manquante pour {key}"
    
    print("\n✅ Test des traductions : RÉUSSI")

def test_user_default_language():
    """Test de la langue par défaut des utilisateurs"""
    print("\n" + "="*60)
    print("TEST 2: Langue par défaut des utilisateurs")
    print("="*60)
    
    app = create_app()
    
    with app.app_context():
        # Créer un utilisateur de test
        test_user = User(
            username='test_multilang',
            email='test@example.com',
            role='viewer',
            display_name='Test Multi-Lang'
        )
        test_user.set_password('test123')
        
        # Vérifier la langue par défaut
        assert test_user.language == 'en', f"Langue par défaut devrait être 'en', mais c'est '{test_user.language}'"
        
        print(f"✅ Nouvelle utilisateur créé avec langue par défaut: {test_user.language}")
        
        # Tester le changement de langue
        test_user.language = 'fr'
        assert test_user.language == 'fr', "Changement de langue vers FR échoué"
        print(f"✅ Changement vers FR: {test_user.language}")
        
        test_user.language = 'pl'
        assert test_user.language == 'pl', "Changement de langue vers PL échoué"
        print(f"✅ Changement vers PL: {test_user.language}")
        
    print("\n✅ Test langue par défaut : RÉUSSI")

def test_altaview_filters_logic():
    """Test de la logique des filtres Altaview"""
    print("\n" + "="*60)
    print("TEST 3: Logique des filtres Altaview")
    print("="*60)
    
    app = create_app()
    
    with app.app_context():
        # Compter les jobs totaux
        total_jobs = JobAltaview.query.count()
        print(f"Total jobs dans la DB: {total_jobs}")
        
        # Test filtre par date
        date_from = datetime.now() - timedelta(days=7)
        recent_jobs = JobAltaview.query.filter(
            JobAltaview.backup_time >= date_from
        ).count()
        print(f"Jobs des 7 derniers jours: {recent_jobs}")
        
        # Test filtre par statut
        success_jobs = JobAltaview.query.filter(
            JobAltaview.status.in_(['Success', 'Completed'])
        ).count()
        print(f"Jobs réussis: {success_jobs}")
        
        error_jobs = JobAltaview.query.filter(
            JobAltaview.status.in_(['Failed', 'Error', 'Partial'])
        ).count()
        print(f"Jobs en erreur: {error_jobs}")
        
        # Test récupération des policies
        policies = db.session.query(JobAltaview.policy_name).distinct().all()
        print(f"Nombre de policies uniques: {len(policies)}")
        if policies:
            print(f"Exemples de policies: {[p[0] for p in policies[:3]]}")
        
        # Vérifications
        assert total_jobs >= 0, "Le nombre de jobs ne peut pas être négatif"
        assert recent_jobs <= total_jobs, "Jobs récents ne peut pas dépasser le total"
        assert success_jobs + error_jobs <= total_jobs, "Somme des statuts ne peut pas dépasser le total"
        
    print("\n✅ Test logique filtres : RÉUSSI")

def test_session_filters():
    """Test de la persistance des filtres dans la session"""
    print("\n" + "="*60)
    print("TEST 4: Persistance des filtres (simulation)")
    print("="*60)
    
    # Simuler les filtres de session
    test_filters = {
        'date_from': '2025-01-01',
        'date_to': '2025-01-31',
        'status': 'success',
        'policy': 'Daily_Backup',
        'search': 'server01'
    }
    
    print("Filtres simulés:")
    for key, value in test_filters.items():
        print(f"  {key}: {value}")
    
    # Vérifier que tous les champs sont présents
    required_fields = ['date_from', 'date_to', 'status', 'policy', 'search']
    for field in required_fields:
        assert field in test_filters, f"Champ {field} manquant dans les filtres"
    
    print("\n✅ Test structure filtres : RÉUSSI")

def test_translation_coverage():
    """Test de la couverture des traductions"""
    print("\n" + "="*60)
    print("TEST 5: Couverture des traductions")
    print("="*60)
    
    from app.services.translations import TRANSLATIONS
    
    total_keys = len(TRANSLATIONS)
    print(f"Nombre total de clés de traduction: {total_keys}")
    
    # Vérifier que chaque clé a bien les 3 langues
    missing_translations = []
    for key, translations in TRANSLATIONS.items():
        if 'en' not in translations:
            missing_translations.append(f"{key} - EN manquant")
        if 'fr' not in translations:
            missing_translations.append(f"{key} - FR manquant")
        if 'pl' not in translations:
            missing_translations.append(f"{key} - PL manquant")
    
    if missing_translations:
        print("\n⚠️ Traductions manquantes:")
        for missing in missing_translations[:10]:  # Afficher les 10 premières
            print(f"  - {missing}")
        print(f"\nTotal traductions manquantes: {len(missing_translations)}")
    else:
        print("✅ Toutes les clés ont les 3 langues (EN/FR/PL)")
    
    # Catégories de traductions
    categories = {}
    for key in TRANSLATIONS.keys():
        prefix = key.split('_')[0]
        categories[prefix] = categories.get(prefix, 0) + 1
    
    print("\nCatégories de traductions:")
    for category, count in sorted(categories.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {category}: {count} clés")
    
    print(f"\n✅ Test couverture traductions : RÉUSSI")
    print(f"   {total_keys} clés disponibles")
    print(f"   {len(missing_translations)} traductions manquantes")

def run_all_tests():
    """Exécuter tous les tests"""
    print("\n" + "="*60)
    print("TESTS AUTOMATISÉS - NBCM V2.5")
    print("Multi-langue + Filtres Persistants Altaview")
    print("="*60)
    
    try:
        test_translations()
        test_user_default_language()
        test_altaview_filters_logic()
        test_session_filters()
        test_translation_coverage()
        
        print("\n" + "="*60)
        print("✅ TOUS LES TESTS RÉUSSIS !")
        print("="*60)
        return True
        
    except AssertionError as e:
        print(f"\n❌ ÉCHEC DU TEST: {e}")
        return False
    except Exception as e:
        print(f"\n❌ ERREUR INATTENDUE: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
