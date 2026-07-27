#!/usr/bin/env bash
# Auto-deploy for the fork instance (see docker-compose.fork.yml).
#
# Designed to run from cron on the server, e.g. every 10 minutes:
#   */10 * * * * /opt/open-notebook-fork/scripts/deploy-fork.sh >> /var/log/open-notebook-fork-deploy.log 2>&1
#
# Behavior: if origin/$DEPLOY_BRANCH has new commits, fast-forward the local
# checkout, rebuild the image and restart the stack. Otherwise exit silently.
# The checkout this script runs from must be dedicated to deployments — local
# commits are not preserved.
set -euo pipefail

DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

# Prevent overlapping runs (builds can take longer than the cron interval).
exec 9> /tmp/open-notebook-fork-deploy.lock
if ! flock -n 9; then
  echo "$(date -Is) another deploy is running, skipping"
  exit 0
fi

git fetch origin "$DEPLOY_BRANCH"
LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse "origin/$DEPLOY_BRANCH")"

if [ "$LOCAL" = "$REMOTE" ] && [ "${FORCE:-}" != "1" ]; then
  exit 0
fi

echo "$(date -Is) deploying $REMOTE (was $LOCAL)"
git reset --hard "$REMOTE"

docker compose -f docker-compose.fork.yml build
docker compose -f docker-compose.fork.yml up -d --remove-orphans

# Reclaim disk from superseded image layers.
docker image prune -f

echo "$(date -Is) deploy complete"
