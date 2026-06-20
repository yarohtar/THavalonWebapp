#!/usr/bin/env bash
set -euo pipefail

### CONFIG ###
REMOTE_DIR="/var/www/avalon/THavalonWebapp"
SERVICE_NAME="avalon"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Starting deployment..."

### 1. Sync files ###
rsync -avz \
  --delete \
  --exclude ".git" \
  --exclude ".env" \
  --exclude "__pycache__" \
  --exclude ".DS_Store" \
  ${SCRIPT_DIR}/ merlin-cf:${REMOTE_DIR}/

echo "Sync complete"

ssh merlin-cf << EOF
set -e

echo "Restarting service: ${SERVICE_NAME}"
sudo systemctl restart ${SERVICE_NAME}

echo "Checking status..."
sudo systemctl --no-pager status ${SERVICE_NAME} | head -n 20

EOF

echo "Deployment finished"

