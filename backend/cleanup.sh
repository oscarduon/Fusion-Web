#!/bin/bash
# Retención de archivos FUSION: elimina outputs de más de 24h (binarios efímeros).
FUSION_DIR="$HOME/.wine/drive_c/FUSION"

# Archivos generados (LAS/LAZ/DTM/TIF/PNG/JPG/CSV/TXT/HTML) con >24h de antigüedad
find "$FUSION_DIR" -maxdepth 1 -type f -mmin +1440 \
  \( -name '*.las' -o -name '*.laz' -o -name '*.dtm' -o -name '*.tif' -o -name '*.tiff' \
     -o -name '*.png' -o -name '*.jpg' -o -name '*.jpeg' -o -name '*.csv' \
     -o -name '*.txt' -o -name '*.html' -o -name '*.xyz' -o -name '*.asc' \) \
  ! -name 'betera15.las' \
  ! -name 'temp_exec_*.bat' \
  -delete 2>/dev/null

# Directorios Potree (octrees) con >24h
find "$FUSION_DIR/potree" -maxdepth 1 -mindepth 1 -mmin +1440 -exec rm -rf {} + 2>/dev/null

exit 0
