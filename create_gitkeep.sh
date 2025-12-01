#!/usr/bin/env bash
set -euo pipefail

# Dossier racine à traiter (par défaut: app)
ROOT_DIR="${1:-app}"

if [ ! -d "$ROOT_DIR" ]; then
  echo "Erreur : le dossier '$ROOT_DIR' n'existe pas."
  exit 1
fi

echo "Ajout de .gitkeep dans tous les sous-dossiers de '$ROOT_DIR'..."

# Parcourt tous les dossiers sous ROOT_DIR (y compris ROOT_DIR lui-même)
find "$ROOT_DIR" -type d -print0 | while IFS= read -r -d '' dir; do
  gitkeep_path="$dir/.gitkeep"
  if [ ! -e "$gitkeep_path" ]; then
    touch "$gitkeep_path"
    echo "  -> Créé : $gitkeep_path"
  fi
done

echo "Terminé."
