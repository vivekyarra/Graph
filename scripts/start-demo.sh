#!/bin/sh
set -eu
redis-server --bind 127.0.0.1 --protected-mode yes --port 6379 \
    --save '' --appendonly no --loadmodule /var/lib/falkordb/bin/falkordb.so &
DB_PID=$!
trap 'kill "$DB_PID" 2>/dev/null || true' EXIT HUP INT TERM
python - <<'PY'
import time
from falkordb import FalkorDB
db=FalkorDB(host="127.0.0.1",port=6379)
for attempt in range(80):
    try:
        db.list_graphs()
        break
    except Exception:
        if attempt==79: raise
        time.sleep(.3)
PY
python -m maelin.seed --tenant alpha
python -m maelin.seed --tenant beta
exec uvicorn maelin.api:api --host 0.0.0.0 --port "${PORT:-8000}"
