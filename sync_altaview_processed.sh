#!/usr/bin/env bash
set -euo pipefail

SRC_DIR="/home/dockers/netbackup-compliance-claude-v23/nbcm_v30/data/altaview_auto_import/processed"
DEST_DIR="/home/github/NBCM/data/altaview_auto_import/processing"

mkdir -p "$DEST_DIR"

# Fichiers modifiés depuis 15 minutes contenant "altaview_imap"
find "$SRC_DIR" -maxdepth 1 -type f -mmin -10 -name '*altaview_imap*' -print0 \
  | while IFS= read -r -d '' file; do
      filename="$(basename "$file")"

      # Enlève les 2 premiers segments séparés par "_"
      # 20251201_224623_altaview_imap_20251201_224523.csv
      # -> altaview_imap_20251201_224523.csv
      dest="$(echo "$filename" | cut -d'_' -f3-)"

      echo "Copie de : $file"
      echo "        -> $DEST_DIR/$dest"
      cp -p "$file" "$DEST_DIR/$dest"
    done
