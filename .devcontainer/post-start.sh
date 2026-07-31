#!/usr/bin/env bash
# postStartCommand (every start): ensure the stack is up after a resume —
# seconds when the images already exist, and a full build if the creation
# build never completed. Synchronous for the same reason as post-create.sh;
# the flock makes it skip instantly if post-create's build is still running.
bash "$(dirname "$0")/compose-up.sh"
