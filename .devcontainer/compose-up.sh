#!/usr/bin/env bash
# Bring the compose stack up. Shared by post-create (--build) and post-start.
# Runs SYNCHRONOUSLY inside the lifecycle hooks: backgrounded children are
# reaped when the hook exits on Codespaces (observed 2026-07-31, even with
# setsid+nohup), so we block instead. First creation streams the build into
# the creation log; resumes take seconds when the images already exist.
# The flock makes concurrent invocations skip cleanly instead of stacking.
set -uo pipefail
cd "$(dirname "$0")/.."
LOG=".devcontainer/compose-up.log"

# .env must exist before ANY build (NEXT_PUBLIC_API_URL is baked into the
# frontend image at build time). Idempotent.
bash .devcontainer/setup-env.sh

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
} 2>&1 | tee -a "$LOG"
