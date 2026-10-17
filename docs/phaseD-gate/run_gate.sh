#!/bin/bash
# PHASE_D section 6 web gate on the TEST stack (docs/phaseD-test-stack.md).
#
#   usage: docs/phaseD-gate/run_gate.sh <work_dir>
#
# Take the host heavy lock around it (rule H4). It RESETS the test stack: the test volume
# is deleted first, then the stack is built (only changed layers) and started, the
# synthetic inputs are generated into <work_dir>/data (once), the API gate and the
# headless-Chrome check run, and the containers are removed at the end (images and the
# new volume are kept). Results: <work_dir>/out (checks.json, result CSVs, screenshots,
# container logs). Needs backend/.venv (its Python has geopandas, rasterio, httpx), node
# and Google Chrome. Synthetic data only.
set -u
export PYTHONDONTWRITEBYTECODE=1
HERE=$(cd "$(dirname "$0")" && pwd)
WT=$(cd "$HERE/../.." && pwd)
WORK=${1:?usage: run_gate.sh <work_dir>}
PY=${PY:-$WT/backend/.venv/bin/python}
DATA_ROOT=${TIER2_PIPELINE_DATA:-/Users/xai/Desktop/spacescans-all/spacescans-web/pipeline-data}
mkdir -p "$WORK"
WORK=$(cd "$WORK" && pwd)
DATA=$WORK/data
OUT=$WORK/out
rm -rf "$OUT"; mkdir -p "$OUT"
[ -f "$DATA/design.json" ] || "$PY" "$HERE/make_data.py" "$DATA" "$DATA_ROOT/TRACT/C3" || exit 2
DC=(docker compose -p tier2-d-test -f "$WT/docs/phaseD-test-stack.yml")
echo "== clean slate (test project only)"; "${DC[@]}" down -v --remove-orphans 2>&1 | tail -3
echo "== build"; "${DC[@]}" build 2>&1 | tail -3
echo "== up"; "${DC[@]}" up -d --no-build 2>&1 | tail -5
for _ in $(seq 1 90); do curl -fsS http://127.0.0.1:8100/api/health >/dev/null 2>&1 && break; sleep 2; done
B=tier2-d-test-backend-1
{
  echo "containers:"; docker ps --filter name=tier2-d-test --format '  {{.Names}} {{.Image}} {{.Ports}} {{.Status}}'
  echo "images:"; docker images --format '  {{.Repository}}:{{.Tag}} {{.ID}} {{.Size}}' | grep tier2-d-
  echo "spacescans in the backend:"; docker exec $B /opt/conda/bin/python -c "import spacescans, sys; print(' ', spacescans.__version__, sys.version.split()[0])"
  echo "mounts:"; docker inspect $B --format '{{range .Mounts}}  {{.Destination}} rw={{.RW}} {{.Type}} {{.Name}}{{println}}{{end}}'
  echo "write to /project:"; docker exec $B sh -c 'touch /project/.gate_probe 2>/dev/null && echo "  WRITABLE (should be read-only)" || echo "  refused (read-only)"'
  echo "CORS preflight from :3100:"; curl -s -D - -o /dev/null -X OPTIONS -H 'Origin: http://localhost:3100' -H 'Access-Control-Request-Method: GET' http://127.0.0.1:8100/api/datasets | grep -i '^access-control-allow-origin' | sed 's/^/  /'
} > "$OUT/facts.txt" 2>&1
cat "$OUT/facts.txt"
echo "== API gate"
"$PY" "$HERE/gate.py" "$DATA" "$OUT" http://127.0.0.1:8100 http://localhost:3100 2>&1 | tee "$OUT/gate.log"
GATE=${PIPESTATUS[0]}
echo "== browser check"
token() { curl -s -X POST -H 'Content-Type: application/json' -d "{\"email\":\"$1\",\"password\":\"Synthetic-Pass-1\"}" http://127.0.0.1:8100/api/auth/login | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["access_token"])'; }
TB=$(token ben.tester@example.com); TA=$(token ada.tester@example.com)
TP=$("$PY" -c "import json; print(json.load(open('$OUT/ids.json'))['task_participant'])" 2>/dev/null)
TE=$("$PY" -c "import json; print(json.load(open('$OUT/ids.json'))['task_episode'])" 2>/dev/null)
node --experimental-websocket "$HERE/browse.mjs" "$OUT/browser" http://localhost:3100 "$TB" "$TA" "$TP" "$TE" "$DATA" http://127.0.0.1:8100 2>&1 | tee "$OUT/browse.log"
BROWSE=${PIPESTATUS[0]}
echo "== logs"
docker logs $B > "$OUT/backend.log" 2>&1
docker logs tier2-d-test-frontend-1 > "$OUT/frontend.log" 2>&1
LEAK=$("$PY" - "$DATA/cohort_B.csv" "$OUT/backend.log" <<'PYEOF'
import csv, sys
rows = list(csv.DictReader(open(sys.argv[1])))
log = open(sys.argv[2], errors="replace").read()
needles = {r["pid"] for r in rows} | {r["longitude"] for r in rows} | {r["latitude"] for r in rows}
print(sorted(n for n in needles if n in log))
PYEOF
)
echo "synthetic cohort values found in the backend log (none expected): $LEAK" | tee -a "$OUT/facts.txt"
echo "PROJ grid download cache in the backend container (none expected):" | tee -a "$OUT/facts.txt"
docker exec $B sh -c 'ls -la "$HOME/.local/share/proj" 2>/dev/null || echo "  none"' 2>&1 | tee -a "$OUT/facts.txt"
echo "== down (containers removed; images and the volume kept)"
"${DC[@]}" down 2>&1 | tail -3
echo "GATE=$GATE BROWSE=$BROWSE" | tee "$OUT/status.txt"
[ "$GATE" = 0 ] && [ "$BROWSE" = 0 ]
