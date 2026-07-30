#!/usr/bin/env bash
# postAttachCommand: make the frontend and backend ports public so the
# browser URLs on the -3000 and -8000 origins keep working after every
# stop/start. There is no declarative way to do this (github/docs runs the
# same command in its own devcontainer), and public visibility reverts to
# private on every codespace stop/start — hence re-running on each attach.
# The long retry outlasts the first-creation build: the ports only become
# forwardable once the services are listening.
set -euo pipefail
[ -n "${CODESPACE_NAME:-}" ] || exit 0
nohup bash -c '
  for i in $(seq 1 400); do
    ok=1
    for port in 3000 8000; do
      if ! gh codespace ports visibility "$port:public" -c "$CODESPACE_NAME" >/dev/null 2>&1; then
        ok=0
        break
      fi
    done
    if [ "$ok" -eq 1 ]; then
      echo "$(date -u "+%F %TZ") ports 3000 and 8000 public after $i tries"
      exit 0
    fi
    sleep 3
  done
  echo "$(date -u "+%F %TZ") gave up making ports 3000 and 8000 public"
' >>/tmp/port-public.log 2>&1 &
disown
