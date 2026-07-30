#!/usr/bin/env bash
# Bring the compose stack up. Shared by post-create (--build) and post-start.
# Self-serializing: the flock makes concurrent invocations (e.g. post-start
# firing while the first-creation background build is running) skip cleanly.
set -uo pipefail
cd "$(dirname "$0")/.."
LOG=".devcontainer/compose-up.log"

exec 9>/tmp/compose-up.lock
flock -n 9 || { echo "compose-up already running — tail -f $LOG"; exit 0; }

{
  echo "=== $(date -u '+%F %TZ') compose-up start (args: $*)"
  # dockerd is launched by the image entrypoint, but readiness races are
  # documented (devcontainers/features#780) — wait, then kick it once.
  if ! timeout 120 bash -c 'until docker info >/dev/null 2>&1; do sleep 2; done'; then
    sudo bash /usr/local/share/docker-init.sh || true
    timeout 60 bash -c 'until docker info >/dev/null 2>&1; do sleep 2; done' \
      || { echo "dockerd never came up — giving up"; exit 1; }
  fi
  docker compose up -d "$@"
  echo "=== $(date -u '+%F %TZ') compose-up done rc=$?"
} >>"$LOG" 2>&1
