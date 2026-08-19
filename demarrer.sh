#!/bin/bash
# Lance le backend FastAPI (port 8000) en arrière-plan — il sert aussi le frontend depuis la
# même origine (voir app.mount("/", StaticFiles(...)) dans main.py), un seul serveur suffit.
# Log dans logs/backend.log, PID dans logs/backend.pid pour qu'arreter.sh le retrouve.

set -e

RACINE_PROJET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$RACINE_PROJET"

mkdir -p logs

# Si un ancien PID existe et tourne encore, on ne relance pas par-dessus.
if [ -f logs/backend.pid ] && kill -0 "$(cat logs/backend.pid)" 2>/dev/null; then
    echo "Backend déjà lancé (PID $(cat logs/backend.pid))."
else
    source backend/.venv/bin/activate
    export TORCHDYNAMO_DISABLE=1
    nohup uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 > logs/backend.log 2>&1 &
    echo $! > logs/backend.pid
    echo "Backend lancé (PID $!) → logs/backend.log"
fi

echo ""
echo "Application : http://127.0.0.1:8000"
