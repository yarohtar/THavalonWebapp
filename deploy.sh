#!/usr/bin/env bash
set -euo pipefail

### CONFIG ###
REMOTE_DIR="/var/www/avalon/THavalonWebapp"
SERVICE_NAME="avalon"

### SAFETY CHECK ###
if [ ! -d ".git" ]; then
  echo "Warning: this does not look like a git repo root"
fi

echo "🚀 Starting deployment..."

### 1. Sync files ###
rsync -avz \
  --delete \
  --exclude ".git" \
  --exclude ".env" \
  --exclude "__pycache__" \
  --exclude ".DS_Store" \
  ./ merlin:${REMOTE_DIR}/

echo "📦 Sync complete"

ssh merlin << EOF
set -e

echo "Restarting service: ${SERVICE_NAME}"
sudo systemctl restart ${SERVICE_NAME}

echo "Checking status..."
sudo systemctl --no-pager status ${SERVICE_NAME} | head -n 20

EOF

echo "Deployment finished"

