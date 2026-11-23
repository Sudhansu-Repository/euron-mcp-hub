#!/usr/bin/env bash
# Write deploy/compose/.env with random, local-only secrets (once; never overwrites).
set -euo pipefail
f="$(cd "$(dirname "$0")/.." && pwd)/deploy/compose/.env"
if [[ -f "$f" ]]; then
  echo "deploy/compose/.env exists (delete it to regenerate)"
  exit 0
fi
rand() { openssl rand -base64 48 | tr -d '/+=\n' | cut -c1-"$1"; }
umask 077
cat > "$f" <<ENV
MCPHUB_SESSION_SECRET=$(rand 64)
MCPHUB_API_KEY_PEPPER=$(rand 64)
MCPHUB_DEMO_PASSWORD=Demo-$(rand 12)
MCPHUB_DEMO_TICKETS_TOKEN=tkt_$(rand 32)
MCPHUB_DEMO_WEATHER_KEY=wx_$(rand 32)
ENV
echo "wrote deploy/compose/.env"
