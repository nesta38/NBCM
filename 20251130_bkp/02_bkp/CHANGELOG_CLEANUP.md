# Changelog - Nettoyage Automatique des Fichiers

## Version 3.0 - Ajout du nettoyage automatique

### 🆕 Nouvelle fonctionnalité : Purge automatique des fichiers importés

**Date :** 29 novembre 2024

### Description
Mise en place d'un système de nettoyage automatique des fichiers CSV importés depuis le répertoire `/app/data/altaview_auto_import/processed/`.

### Fonctionnalités implémentées

#### 1. Service de nettoyage (`cleanup_service.py`)
- ✅ Classe `CleanupService` pour gérer la purge automatique
- ✅ Suppression automatique des fichiers > 48h
- ✅ Statistiques détaillées (nombre de fichiers, espace libéré)
- ✅ Logs détaillés de toutes les opérations
- ✅ Méthode `get_directory_stats()` pour obtenir l'état actuel

#### 2. Intégration au Scheduler (`scheduler_service.py`)
- ✅ Tâche planifiée quotidienne à 3h00
- ✅ Job `cleanup_processed_files` ajouté au scheduler
- ✅ Fonction `cleanup_processed_files_job()` pour l'exécution

#### 3. Interface d'administration (`admin.py` + `admin/index.html`)
- ✅ Nouvelle section "Nettoyage Fichiers Auto-Import"
- ✅ Affichage en temps réel des statistiques :
  - Nombre total de fichiers
  - Fichiers éligibles à la suppression
  - Espace disque utilisé/libérable
  - Pourcentage de fichiers > 48h
- ✅ Bouton "Nettoyer maintenant" pour purge manuelle
- ✅ Route `/admin/cleanup_stats` (API JSON)
- ✅ Route `/admin/cleanup_now` (action POST)

### Configuration

#### Paramètres par défaut
```python
base_dir = '/app/data/altaview_auto_import/processed'
retention_hours = 48  # 48 heures
schedule = '3:00 AM'  # Tous les jours à 3h
```

#### Personnalisation possible
Pour modifier la durée de rétention, éditer `app/services/cleanup_service.py` :
```python
cleanup_service = CleanupService(
    base_dir='/app/data/altaview_auto_import/processed',
    retention_hours=72  # Exemple : 72h au lieu de 48h
)
```

### Utilisation

#### Vérification des statistiques
1. Accéder à l'interface d'administration
2. Section "Nettoyage Fichiers Auto-Import"
3. Les statistiques se chargent automatiquement

#### Nettoyage manuel
1. Dans l'interface d'administration
2. Cliquer sur "Nettoyer maintenant"
3. Confirmation avec message de succès/erreur

#### Vérification des logs
```bash
tail -f /app/data/logs/nbcm.log | grep "Nettoyage"
```

Exemple de sortie :
```
[2024-11-29 03:00:00] INFO [cleanup_service.cleanup_old_files:45] 🧹 Début nettoyage fichiers > 48h dans /app/data/altaview_auto_import/processed
[2024-11-29 03:00:00] INFO [cleanup_service.cleanup_old_files:51]    Date limite : 2024-11-27 03:00:00
[2024-11-29 03:00:00] INFO [cleanup_service.cleanup_old_files:64]    Suppression: 20251127_193345_altaview_imap_20251127_193245.csv (âge: 55.2h, taille: 12458 bytes)
[2024-11-29 03:00:00] INFO [cleanup_service.cleanup_old_files:82] ✅ Nettoyage terminé : 25 fichiers supprimés (0.45 MB libérés)
```

### Fichiers modifiés

1. **`app/services/cleanup_service.py`** (déjà existant, pas modifié)
   - Service de nettoyage automatique complet

2. **`app/services/scheduler_service.py`**
   - Ajout du job de nettoyage
   - Fonction `cleanup_processed_files_job()`

3. **`app/routes/admin.py`**
   - Route `GET /admin/cleanup_stats`
   - Route `POST /admin/cleanup_now`

4. **`app/templates/admin/index.html`**
   - Nouvelle section "Nettoyage Fichiers Auto-Import"
   - JavaScript pour chargement dynamique des stats

### Tests recommandés

1. **Test de la purge automatique**
```bash
# Créer des fichiers de test avec dates anciennes
touch -t 202411270000 /app/data/altaview_auto_import/processed/test_old.csv

# Déclencher manuellement le nettoyage
# Via l'interface admin ou directement en Python
```

2. **Test de l'API statistiques**
```bash
curl http://localhost:5000/admin/cleanup_stats
```

3. **Vérifier le scheduler**
- Accéder à l'interface admin
- Vérifier que le job "Nettoyage fichiers processed/ > 48h" apparaît

### Sécurité

- ✅ Authentification requise (`@admin_required`)
- ✅ Suppression uniquement dans le répertoire configuré
- ✅ Logs détaillés de toutes les suppressions
- ✅ Pas de suppression récursive dans d'autres dossiers

### Améliorations futures possibles

- [ ] Configuration de la durée de rétention via l'interface admin
- [ ] Configuration de l'heure de nettoyage via l'interface admin
- [ ] Notifications par email après chaque nettoyage
- [ ] Historique des nettoyages dans la base de données
- [ ] Export des logs de nettoyage

### Notes de migration

Cette fonctionnalité est **rétrocompatible** et ne nécessite aucune migration de base de données.

Le service de cleanup était déjà présent dans le code mais n'était pas intégré au scheduler ni à l'interface d'administration.

### Support

Pour toute question ou problème :
1. Vérifier les logs : `/app/data/logs/nbcm.log`
2. Vérifier que le scheduler est actif dans l'interface admin
3. Vérifier les permissions sur le répertoire processed/
