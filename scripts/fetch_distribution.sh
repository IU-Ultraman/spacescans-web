#!/usr/bin/env bash
# Download project-mirrored exposure data straight into pipeline-data/.
#
# A thin wrapper around the spacescans package's own downloader:
#     python -m spacescans data fetch --data-dir pipeline-data --dataset <key> ...
# which resumes interrupted downloads (HTTP Range), verifies every SHA-256
# against the package's data manifest, extracts, and deletes the archive (so
# peak disk is one archive, not all of them).
#
# Usage, from the repo root:
#   scripts/fetch_distribution.sh tract_boundaries_v1.tar.gz [more...]   # by artifact file name
#   scripts/fetch_distribution.sh tract_boundaries noise_rasters         # or by dataset key
#   scripts/fetch_distribution.sh --list        # every mirrored artifact, its dataset and size
#   scripts/fetch_distribution.sh --small       # everything except Bluespace — the other
#                                               # variables' mirrored data, about 8.5 GB on disk
#                                               # (Bluespace's NHD cache alone needs ~89 GB free
#                                               # while unpacking)
#   scripts/fetch_distribution.sh noise_v1.tar.gz -- --dry-run   # anything after -- goes to
#                                               # `spacescans data fetch` (e.g. --mirror DIR)
#
# Needs a Python with the spacescans package importable (the one the backend
# uses; set SPACESCANS_PYTHON to pick it, default python3). Install it with
#   pip install "spacescans-pipeline @ git+https://github.com/IU-Ultraman/spacescans.git@<ref>"
# using the ref pinned in backend/Dockerfile (SPACESCANS_REF).
#
# Note on size: a default Codespace has ~32 GB of disk. The NHD cache needs
# ~89 GB (38.5 download + 50.3 extracted) and simply will not fit — run the
# bluespace variable on a machine with real storage, or pick a larger machine
# type when creating the codespace.
set -uo pipefail

cd "$(dirname "$0")/.."
DATA_DIR="${SPACESCANS_DATA_HOST:-pipeline-data}"
PY="${SPACESCANS_PYTHON:-python3}"

usage() {
  # Print the header comment block, stopping at the first line of code — a
  # fixed line range would truncate (or overrun) it on the next edit.
  awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "$0"
}

case "${1:-}" in ""|-h|--help) usage; exit 0 ;; esac

command -v "$PY" >/dev/null || { echo "$PY is required but not installed (set SPACESCANS_PYTHON)"; exit 1; }
"$PY" -c 'import spacescans.data' 2>/dev/null || {
  echo "the spacescans package is not importable by $PY."
  echo "Install it (see the ref in backend/Dockerfile, SPACESCANS_REF):"
  echo "  $PY -m pip install \"spacescans-pipeline @ git+https://github.com/IU-Ultraman/spacescans.git@<ref>\""
  echo "or point SPACESCANS_PYTHON at an interpreter that has it. The running backend"
  echo "container has one, with the data root mounted at /project:"
  echo "  docker compose exec backend python -m spacescans data fetch --data-dir /project --dataset <key>"
  echo "(dataset keys: scripts/fetch_distribution.sh --list, once the package is importable,"
  echo " or docker compose exec backend python -m spacescans data status --data-dir /project)"
  exit 1
}

# Everything the manifest mirrors: artifact -> dataset key, size on disk, status.
list_artifacts() {
  "$PY" - <<'EOF'
from spacescans.data import load_manifest
m = load_manifest()
print(f"{'artifact':70s} {'dataset':22s} {'on disk':>10s}  status")
for name, a in m.artifacts.items():
    ds = (m.datasets_of_artifact(name) or ["-"])[0]
    print(f"{name:70s} {ds:22s} {a.disk_bytes / 1e9:7.2f} GB  {a.status}")
EOF
}

# Map each requested name (artifact file name or dataset key) to --dataset
# arguments; "--small" is every mirror dataset except the NHD cache.
resolve_datasets() {
  "$PY" - "$@" <<'EOF'
import sys
from spacescans.data import load_manifest
m = load_manifest()
names = sys.argv[1:]
keys: list[str] = []
if names == ["--small"]:
    names = [k for k, d in m.datasets.items() if d.fetchable and k != "nhd_features_cache"]
for name in names:
    if name in m.datasets:
        key = name
    else:
        found = m.datasets_of_artifact(name)
        if not found:
            sys.exit(f"not a mirrored artifact or dataset: {name} (try --list)")
        key = found[0]
    if key not in keys:
        keys.append(key)
for key in keys:
    print(key)
EOF
}

case "${1:-}" in
  --list) list_artifacts; exit 0 ;;
esac

NAMES=()
EXTRA=()
while [ $# -gt 0 ]; do
  case "$1" in
    --) shift; EXTRA=("$@"); break ;;
    *) NAMES+=("$1"); shift ;;
  esac
done
[ "${#NAMES[@]}" -gt 0 ] || { echo "nothing to fetch"; exit 1; }

RESOLVED=$(resolve_datasets "${NAMES[@]}") || exit 1
# No mapfile/readarray: macOS ships bash 3.2, where they don't exist.
ARGS=()
while IFS= read -r key; do
  [ -n "$key" ] && ARGS+=(--dataset "$key")
done <<EOF
$RESOLVED
EOF
[ "${#ARGS[@]}" -gt 0 ] || { echo "nothing to fetch"; exit 1; }

echo "Target : $DATA_DIR/"
echo
exec "$PY" -m spacescans data fetch --data-dir "$DATA_DIR" "${ARGS[@]}" ${EXTRA[@]+"${EXTRA[@]}"}
