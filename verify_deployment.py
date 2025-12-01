#!/usr/bin/env python3
"""
Script de vérification post-déploiement NBCM V3.0
Vérifie que toutes les modifications sont bien en place
"""

import os
import sys

def check_file_exists(filepath, description):
    """Vérifie qu'un fichier existe"""
    if os.path.exists(filepath):
        print(f"✅ {description}")
        return True
    else:
        print(f"❌ {description} - MANQUANT: {filepath}")
        return False

def check_file_contains(filepath, search_string, description):
    """Vérifie qu'un fichier contient une chaîne spécifique"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            if search_string in content:
                print(f"✅ {description}")
                return True
            else:
                print(f"❌ {description} - CONTENU MANQUANT")
                return False
    except Exception as e:
        print(f"❌ {description} - ERREUR: {e}")
        return False

def main():
    print("=" * 60)
    print("🔍 NBCM V3.0 - Vérification Post-Déploiement")
    print("=" * 60)
    print()
    
    all_ok = True
    
    # Vérification 1: Fichiers de service
    print("📁 Vérification des fichiers de service...")
    all_ok &= check_file_exists(
        "app/services/cleanup_service.py",
        "Service de cleanup présent"
    )
    all_ok &= check_file_exists(
        "app/services/scheduler_service.py",
        "Service scheduler présent"
    )
    print()
    
    # Vérification 2: Integration scheduler
    print("⚙️  Vérification de l'intégration scheduler...")
    all_ok &= check_file_contains(
        "app/services/scheduler_service.py",
        "cleanup_processed_files_job",
        "Fonction cleanup_processed_files_job() présente"
    )
    all_ok &= check_file_contains(
        "app/services/scheduler_service.py",
        "cleanup_processed_files",
        "Job cleanup_processed_files planifié"
    )
    all_ok &= check_file_contains(
        "app/services/scheduler_service.py",
        "CronTrigger(hour=3, minute=0)",
        "Planification à 3h00 configurée"
    )
    print()
    
    # Vérification 3: Routes admin
    print("🌐 Vérification des routes admin...")
    all_ok &= check_file_contains(
        "app/routes/admin.py",
        "cleanup_stats",
        "Route /admin/cleanup_stats présente"
    )
    all_ok &= check_file_contains(
        "app/routes/admin.py",
        "cleanup_now",
        "Route /admin/cleanup_now présente"
    )
    print()
    
    # Vérification 4: Template admin
    print("🎨 Vérification du template admin...")
    all_ok &= check_file_contains(
        "app/templates/admin/index.html",
        "Nettoyage Fichiers Auto-Import",
        "Section cleanup dans admin présente"
    )
    all_ok &= check_file_contains(
        "app/templates/admin/index.html",
        "cleanup-stats",
        "Div statistiques cleanup présent"
    )
    all_ok &= check_file_contains(
        "app/templates/admin/index.html",
        "loadCleanupStats",
        "JavaScript de chargement stats présent"
    )
    print()
    
    # Vérification 5: Sidebar hiérarchique
    print("🗂️  Vérification de la sidebar hiérarchique...")
    all_ok &= check_file_contains(
        "app/templates/base.html",
        "has-submenu",
        "Classe has-submenu présente"
    )
    all_ok &= check_file_contains(
        "app/templates/base.html",
        "bi-chevron-right",
        "Icônes chevron présentes"
    )
    all_ok &= check_file_contains(
        "app/templates/base.html",
        "submenu nav flex-column",
        "Structure submenu présente"
    )
    all_ok &= check_file_contains(
        "app/templates/base.html",
        "submenuMaintenance",
        "Menu Maintenance présent"
    )
    all_ok &= check_file_contains(
        "app/templates/base.html",
        "submenuBackup",
        "Menu Sauvegarde & Restauration présent"
    )
    print()
    
    # Vérification 6: CSS
    print("💅 Vérification du CSS...")
    all_ok &= check_file_contains(
        "app/templates/base.html",
        ".submenu { padding-left: 0",
        "Style submenu présent"
    )
    all_ok &= check_file_contains(
        "app/templates/base.html",
        "transform: rotate(90deg)",
        "Animation chevron présente"
    )
    all_ok &= check_file_contains(
        "app/templates/base.html",
        "overflow-y: auto",
        "Scroll sidebar configuré"
    )
    print()
    
    # Vérification 7: Répertoires
    print("📂 Vérification des répertoires...")
    processed_dir = "data/altaview_auto_import/processed"
    if os.path.exists(processed_dir):
        print(f"✅ Répertoire processed/ présent")
        file_count = len([f for f in os.listdir(processed_dir) if os.path.isfile(os.path.join(processed_dir, f))])
        print(f"   → {file_count} fichiers présents")
    else:
        print(f"⚠️  Répertoire processed/ sera créé au démarrage")
    print()
    
    # Résultat final
    print("=" * 60)
    if all_ok:
        print("✅ TOUTES LES VÉRIFICATIONS SONT PASSÉES")
        print("=" * 60)
        print()
        print("🚀 Prochaines étapes:")
        print("   1. Redémarrer l'application")
        print("   2. Vérifier le dashboard admin")
        print("   3. Tester la navigation hiérarchique")
        print("   4. Consulter les statistiques de cleanup")
        print()
        return 0
    else:
        print("❌ CERTAINES VÉRIFICATIONS ONT ÉCHOUÉ")
        print("=" * 60)
        print()
        print("⚠️  Veuillez vérifier les fichiers manquants ci-dessus")
        print()
        return 1

if __name__ == "__main__":
    sys.exit(main())
