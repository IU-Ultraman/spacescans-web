#!/usr/bin/env bash
# postCreateCommand: build + start the stack SYNCHRONOUSLY. Backgrounded
# children do not survive hook exit on Codespaces (reaped even under
# setsid+nohup — observed 2026-07-31), so we block: the ~10-min first
# build streams into the creation log, and the terminal/editor stay
# usable meanwhile (waitFor defaults to updateContentCommand).
set -uo pipefail
cd "$(dirname "$0")/.."
bash .devcontainer/compose-up.sh --build
