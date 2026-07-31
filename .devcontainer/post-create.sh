#!/usr/bin/env bash
# postCreateCommand: provision .env synchronously (must precede the frontend
# build), then build + start the stack in the background so codespace
# creation isn't blocked for the ~10-minute first build.
set -uo pipefail
cd "$(dirname "$0")/.."

bash .devcontainer/setup-env.sh
# setsid, not just nohup: the lifecycle runner kills the hook's process
# GROUP when the hook exits (observed 2026-07-31: .env written but the
# nohup'd child died before creating its lock file). A new session
# escapes the group-kill; nohup/disown alone do not.
setsid nohup bash .devcontainer/compose-up.sh --build >/dev/null 2>&1 </dev/null &
disown
echo "Stack building in the background — follow with: tail -f .devcontainer/compose-up.log"
