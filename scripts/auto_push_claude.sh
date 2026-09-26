#!/usr/bin/env bash
# Push the `claude` branch whenever it is ahead of origin.
#
# Claude (Cowork) commits but cannot push: the remote is SSH and its sandbox has no
# keys. This runs on the Mac with your own credentials, so commits reach origin
# without a credential ever living inside the repo.
#
# By hand:   ./scripts/auto_push_claude.sh
# Scheduled: scripts/com.suraj.tradingview-autopush.plist (every 15 minutes)
set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

LOG_DIR="$PROJECT_DIR/data"; mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/auto_push.log"
BRANCH="$(git --no-optional-locks rev-parse --abbrev-ref HEAD)"

{
  if [ "$BRANCH" != "claude" ]; then
      echo "$(date '+%F %T') skip — on '$BRANCH', not 'claude'"; exit 0
  fi
  # Refuse to push a half-finished state
  if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ] || [ -f .git/MERGE_HEAD ] \
     || [ -f "$(git rev-parse --git-dir)/MERGE_HEAD" ]; then
      echo "$(date '+%F %T') skip — merge or rebase in progress"; exit 0
  fi
  if ! git --no-optional-locks diff --quiet || ! git --no-optional-locks diff --cached --quiet; then
      echo "$(date '+%F %T') skip — uncommitted changes in the working tree"; exit 0
  fi

  git fetch --quiet origin claude 2>/dev/null
  AHEAD="$(git --no-optional-locks rev-list --count origin/claude..claude 2>/dev/null || echo 0)"
  BEHIND="$(git --no-optional-locks rev-list --count claude..origin/claude 2>/dev/null || echo 0)"

  if [ "$AHEAD" = "0" ]; then
      exit 0   # nothing to push, stay quiet
  fi
  if [ "$BEHIND" != "0" ]; then
      echo "$(date '+%F %T') skip — diverged: $AHEAD ahead, $BEHIND behind; merge or rebase first"; exit 0
  fi

  echo "$(date '+%F %T') pushing $AHEAD commit(s)…"
  if git push origin claude 2>&1; then
      echo "$(date '+%F %T') pushed OK"
  else
      echo "$(date '+%F %T') PUSH FAILED — see above"
  fi
} >> "$LOG" 2>&1
