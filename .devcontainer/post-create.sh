#!/usr/bin/env bash
# postCreateCommand: provision .env synchronously (must precede the frontend
# build), then build + start the stack in the background so codespace
# creation isn't blocked for the ~10-minute first build.
set -uo pipefail
cd "$(dirname "$0")/.."

bash .devcontainer/setup-env.sh
nohup bash .devcontainer/compose-up.sh --build >/dev/null 2>&1 &
disown
echo "Stack building in the background — follow with: tail -f .devcontainer/compose-up.log"
