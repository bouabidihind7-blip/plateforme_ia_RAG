#!/bin/bash
# Arrête proprement le backend et le frontend lancés par demarrer.sh (via leur PID enregistré).

RACINE_PROJET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$RACINE_PROJET"

for nom in backend; do
    fichier_pid="logs/${nom}.pid"
    if [ -f "$fichier_pid" ] && kill -0 "$(cat "$fichier_pid")" 2>/dev/null; then
        kill "$(cat "$fichier_pid")"
        echo "${nom} arrêté (PID $(cat "$fichier_pid"))."
    else
        echo "${nom} n'était pas lancé."
    fi
    rm -f "$fichier_pid"
done
