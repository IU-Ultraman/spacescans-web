#!/usr/bin/env bash
# postStartCommand (every start, incl. first creation): make sure the stack
# is up after a resume. restart:unless-stopped normally brings the containers
# back by itself; this is the safety net for the documented dind flakiness.
# No --build here — resumes reuse the images. If the first-creation build is
# still running, the flock inside compose-up.sh skips this instantly.
# setsid: escape the lifecycle runner's process-group kill (see post-create.sh)
setsid nohup bash "$(dirname "$0")/compose-up.sh" >/dev/null 2>&1 </dev/null &
disown
