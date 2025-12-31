#!/bin/bash
echo "=========================================="
echo " Démarrage de l'interface web Gliffy"
echo "=========================================="
# Vérifier si python3 est installé
if command -v python3 &>/dev/null; then
    python3 cli.py web
else
    python cli.py web
fi

