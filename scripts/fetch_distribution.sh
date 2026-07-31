#!/usr/bin/env bash
# Download deployer-distributed exposure data straight into pipeline-data/.
#
# Use this when the machine running the app is not the machine you browse from
# — a GitHub Codespace, a remote VM — so there is no local copy to upload.
# It pulls from the same anonymous OneDrive share link the Data Setup page
# shows, verifies the SHA-256 from the shipped manifest, extracts, and deletes
# the archive (so peak disk is one archive, not all of them).
#
# Usage, from the repo root:
#   scripts/fetch_distribution.sh tract_boundaries_v1.tar.gz [more...]
#   scripts/fetch_distribution.sh --list
#   scripts/fetch_distribution.sh --small      # everything except the 38 GB NHD cache
#
# Note on size: a default Codespace has ~32 GB of disk. The NHD cache needs
# ~89 GB (38.5 download + 50.3 extracted) and simply will not fit — run the
# bluespace variable on a machine with real storage, or pick a larger machine
# type when creating the codespace.
set -uo pipefail

cd "$(dirname "$0")/.."
MANIFEST="backend/app/data/distribution_manifest.json"
SOURCES="frontend/src/lib/data-sources.json"
DATA_DIR="${SPACESCANS_DATA_HOST:-pipeline-data}"
WORK="$DATA_DIR/.downloads"

command -v python3 >/dev/null || { echo "python3 is required"; exit 1; }
[ -f "$MANIFEST" ] || { echo "run me from the repo root (missing $MANIFEST)"; exit 1; }

py() { python3 -c "$@"; }

list_artifacts() {
  py "
import json
m = json.load(open('$MANIFEST'))['artifacts']
for n, s in m.items():
    extra = f\", {s['extracted_bytes']/1e9:.1f} GB extracted\" if 'extracted_bytes' in s else ''
    print(f\"{n:45s} {s['bytes']/1e9:6.2f} GB download{extra}\")
"
}

case "${1:-}" in
  ""|-h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  --list) list_artifacts; exit 0 ;;
  --small)
    mapfile -t NAMES < <(py "
import json
m = json.load(open('$MANIFEST'))['artifacts']
print('\n'.join(n for n in m if 'nhd' not in n))
")
    ;;
  *) NAMES=("$@") ;;
esac

# The share link lives in the Data Setup catalog — one source of truth.
SHARE_URL=$(py "
import json, sys
d = json.load(open('$SOURCES'))
for entry in d['selfServe'] + d['preset']:
    for key in ('sourceUrl', 'downloadUrl'):
        u = entry.get(key, '')
        if 'sharepoint.com' in u:
            print(u); sys.exit()
sys.exit('no SharePoint share link found in $SOURCES')
") || exit 1

mkdir -p "$WORK"
COOKIES="$WORK/.cookies"
# Step 1: follow the share link once to mint an anonymous access cookie, and
# read the folder's server-relative path out of the redirect it hands back.
FOLDER=$(curl -sI --max-time 60 -c "$COOKIES" "$SHARE_URL" \
  | tr -d '\r' | awk '/^[Ll]ocation:/ {print $2}' \
  | py "
import sys, urllib.parse as u
loc = sys.stdin.read().strip()
q = u.parse_qs(u.urlparse(loc).query)
print(q['id'][0])
") || { echo "could not resolve the share link — is it still shared 'anyone with the link'?"; exit 1; }
HOST=$(py "import urllib.parse as u; print(u.urlparse('$SHARE_URL').netloc)")
SITE=$(py "print('/'.join('$FOLDER'.strip('/').split('/')[:2]))")

echo "Source : https://$HOST$FOLDER"
echo "Target : $DATA_DIR/"
echo

for NAME in "${NAMES[@]}"; do
  read -r EXPECT KIND DEST <<<"$(py "
import json, sys
m = json.load(open('$MANIFEST'))['artifacts']
s = m.get('$NAME')
if s is None:
    sys.exit('not a distribution artifact: $NAME (try --list)')
print(s['sha256'], s['kind'], s.get('dest', '-'))
")" || exit 1

  ARCHIVE="$WORK/$NAME"
  echo "==> $NAME"
  if ! curl -sfL --max-time 21600 -b "$COOKIES" -o "$ARCHIVE" --progress-bar \
      "https://$HOST/$SITE/_api/web/GetFileByServerRelativeUrl('$FOLDER/$NAME')/\$value"; then
    echo "    download failed"; rm -f "$ARCHIVE"; exit 1
  fi

  ACTUAL=$(py "
import hashlib
h = hashlib.sha256()
with open('$ARCHIVE', 'rb') as f:
    for c in iter(lambda: f.read(8 << 20), b''):
        h.update(c)
print(h.hexdigest())
")
  if [ "$ACTUAL" != "$EXPECT" ]; then
    echo "    CHECKSUM MISMATCH (got ${ACTUAL:0:16}…, expected ${EXPECT:0:16}…) — not extracting"
    rm -f "$ARCHIVE"; exit 1
  fi
  echo "    checksum ok"

  if [ "$KIND" = "bare" ]; then
    mkdir -p "$DATA_DIR/$DEST"
    mv "$ARCHIVE" "$DATA_DIR/$DEST/$NAME"
    echo "    placed in $DATA_DIR/$DEST/"
  else
    tar -xzf "$ARCHIVE" -C "$DATA_DIR/" || { echo "    extract failed"; exit 1; }
    rm -f "$ARCHIVE"
    echo "    extracted into $DATA_DIR/"
  fi
done

rm -f "$COOKIES"
rmdir "$WORK" 2>/dev/null
echo
echo "Done. The Data Setup page should now show these datasets as present."
