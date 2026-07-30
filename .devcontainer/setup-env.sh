#!/usr/bin/env bash
# One-time .env provisioning (idempotent). Must run BEFORE the first frontend
# image build: NEXT_PUBLIC_API_URL is baked into the image at build time.
set -uo pipefail
cd "$(dirname "$0")/.."

cp -n .env.docker.example .env || true
if grep -q change-me-to-a-real-secret .env; then
  sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$(openssl rand -hex 32)/" .env
fi
# In Codespaces the browser reaches the API on the forwarded -8000 URL, not
# localhost — bake that into the frontend build.
if [ -n "${CODESPACE_NAME:-}" ] && ! grep -q '^NEXT_PUBLIC_API_URL=https' .env; then
  sed -i "s|^NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=https://${CODESPACE_NAME}-8000.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}|" .env
fi
