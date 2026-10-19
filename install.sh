#!/bin/bash
# Installe ThreadTool dans FreeCAD 1.1 (Linux).
#   ./install.sh          -> lien symbolique (les modifications du dossier sont prises en compte directement)
#   ./install.sh --copy   -> copie du dossier
#   ./install.sh --remove -> désinstallation
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
MOD="${FREECAD_MOD_DIR:-$HOME/.local/share/FreeCAD/v1-1/Mod}"
DEST="$MOD/ThreadTool"

if [ "$1" = "--remove" ]; then
    rm -rf "$DEST"
    echo "ThreadTool désinstallé ($DEST supprimé)."
    exit 0
fi

mkdir -p "$MOD"
if [ -e "$DEST" ] || [ -L "$DEST" ]; then
    echo "Une version existe déjà dans $DEST : remplacement."
    rm -rf "$DEST"
fi
if [ "$1" = "--copy" ]; then
    cp -r "$SRC" "$DEST"
    rm -rf "$DEST/tests/__pycache__" "$DEST/threadtool/__pycache__"
    echo "ThreadTool copié dans $DEST"
else
    ln -s "$SRC" "$DEST"
    echo "Lien créé : $DEST -> $SRC"
fi
echo "Redémarre FreeCAD, puis ouvre l'atelier Part Design."
