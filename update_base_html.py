#!/usr/bin/env python3
"""
Script de mise à jour automatique de base.html pour NBCM V3.0
Met à jour les liens de la sidebar vers les nouvelles routes admin
"""

import sys
import os
from pathlib import Path

def update_base_html(base_html_path):
    """
    Met à jour base.html avec les nouvelles routes admin
    """
    print(f"📝 Lecture de {base_html_path}...")
    
    with open(base_html_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Backup
    backup_path = str(base_html_path) + '.backup'
    print(f"💾 Sauvegarde dans {backup_path}...")
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    # Liste des remplacements
    replacements = [
        # SMTP - Configuration
        (
            '''                            <li class="nav-item">
                                <a class="nav-link" href="{{ url_for('admin.index') }}#smtp">
                                    <i class="bi bi-calendar-week"></i> Planification envoi vers destinataires
                                </a>
                            </li>''',
            '''                            <li class="nav-item">
                                <a class="nav-link {{ 'active' if request.endpoint == 'admin.smtp' }}" href="{{ url_for('admin.smtp') }}">
                                    <i class="bi bi-gear"></i> Configuration SMTP
                                </a>
                            </li>
                            <li class="nav-item">
                                <a class="nav-link {{ 'active' if request.endpoint == 'admin.smtp_schedule' }}" href="{{ url_for('admin.smtp_schedule') }}">
                                    <i class="bi bi-calendar-week"></i> Planification envoi
                                </a>
                            </li>'''
        ),
        
        # IMAP - Configuration + Historique
        (
            '''                            <li class="nav-item">
                                <a class="nav-link" href="{{ url_for('admin.index') }}#imap">
                                    <i class="bi bi-clock-history"></i> Historique des imports
                                </a>
                            </li>''',
            '''                            <li class="nav-item">
                                <a class="nav-link {{ 'active' if request.endpoint == 'admin.imap' }}" href="{{ url_for('admin.imap') }}">
                                    <i class="bi bi-gear"></i> Configuration IMAP
                                </a>
                            </li>
                            <li class="nav-item">
                                <a class="nav-link {{ 'active' if request.endpoint == 'admin.imap_history' }}" href="{{ url_for('admin.imap_history') }}">
                                    <i class="bi bi-clock-history"></i> Historique des imports
                                </a>
                            </li>'''
        ),
        
        # API Altaview
        (
            '''                <li class="nav-item">
                    <a class="nav-link" href="{{ url_for('admin.index') }}#api">
                        <i class="bi bi-cloud-arrow-down"></i> API Altaview
                    </a>
                </li>''',
            '''                <li class="nav-item">
                    <a class="nav-link {{ 'active' if request.endpoint == 'admin.api' }}" href="{{ url_for('admin.api') }}">
                        <i class="bi bi-cloud-arrow-down"></i> API Altaview
                    </a>
                </li>'''
        ),
        
        # Maintenance DB - Purge CMDB
        (
            '''href="{{ url_for('admin.index') }}#purge-cmdb"''',
            '''href="{{ url_for('admin.maintenance_db') }}"'''
        ),
        
        # Maintenance DB - Purge Jobs
        (
            '''href="{{ url_for('admin.index') }}#purge-jobs"''',
            '''href="{{ url_for('admin.maintenance_db') }}"'''
        ),
        
        # Maintenance DB - Cleanup
        (
            '''href="{{ url_for('admin.index') }}#cleanup"''',
            '''href="{{ url_for('admin.maintenance_db') }}"'''
        ),
        
        # Maintenance DB - Dedup
        (
            '''href="{{ url_for('admin.index') }}#dedup"''',
            '''href="{{ url_for('admin.maintenance_db') }}"'''
        ),
        
        # Maintenance FS
        (
            '''href="{{ url_for('admin.index') }}#cleanup-files"''',
            '''href="{{ url_for('admin.maintenance_fs') }}"'''
        ),
        
        # Planification Archivage
        (
            '''                            <li class="nav-item">
                                <a class="nav-link" href="#">
                                    <i class="bi bi-calendar-check"></i> Planification Archivage
                                </a>
                            </li>''',
            '''                            <li class="nav-item">
                                <a class="nav-link {{ 'active' if request.endpoint == 'admin.archive_schedule' }}" href="{{ url_for('admin.archive_schedule') }}">
                                    <i class="bi bi-calendar-check"></i> Planification Archivage
                                </a>
                            </li>'''
        ),
    ]
    
    # Appliquer les remplacements
    modified = False
    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            modified = True
            print(f"✅ Remplacement effectué : {old[:50]}...")
        else:
            print(f"⚠️  Pattern non trouvé : {old[:50]}...")
    
    # Sauvegarder
    if modified:
        print(f"\n💾 Sauvegarde du fichier mis à jour...")
        with open(base_html_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ Fichier mis à jour avec succès !")
        print(f"📦 Backup disponible : {backup_path}")
        return True
    else:
        print(f"\n⚠️  Aucune modification effectuée")
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python update_base_html.py <chemin_vers_base.html>")
        print("Exemple: python update_base_html.py /chemin/vers/nbcm/app/templates/base.html")
        sys.exit(1)
    
    base_html_path = Path(sys.argv[1])
    
    if not base_html_path.exists():
        print(f"❌ Fichier non trouvé : {base_html_path}")
        sys.exit(1)
    
    print("🚀 Mise à jour de base.html pour NBCM V3.0")
    print("=" * 60)
    
    if update_base_html(base_html_path):
        print("\n" + "=" * 60)
        print("✅ Mise à jour terminée avec succès !")
        print("\n📝 Prochaines étapes :")
        print("   1. Vérifier le fichier mis à jour")
        print("   2. Tester la navigation dans l'application")
        print("   3. En cas de problème, restaurer depuis .backup")
    else:
        print("\n❌ Mise à jour échouée - vérifier le fichier source")


if __name__ == "__main__":
    main()
