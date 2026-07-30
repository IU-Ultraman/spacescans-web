#!/usr/bin/env bash
# postAttachCommand: make port 8000 public so the browser page on the -3000
# origin can call the API directly. There is no declarative way to do this
# (github/docs runs the same command in its own devcontainer), and public
# visibility REVERTS to private on every codespace stop/start — hence
# re-running on each attach. The long retry outlasts the first-creation
# build: the port only becomes forwardable once the backend is listening.
[ -n "${CODESPACE_NAME:-}" ] || exit 0
nohup bash -c '
  for i in $(seq 1 400); do
    if gh codespace ports visibility 8000:public -c "$CODESPACE_NAME" >/dev/null 2>&1; then
      echo "$(date -u "+%F %TZ") port 8000 public after $i tries"
      exit 0
    fi
    sleep 3
  done
  echo "$(date -u "+%F %TZ") gave up making port 8000 public"
' >>/tmp/port8000.log 2>&1 &
disown
