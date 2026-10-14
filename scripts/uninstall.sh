#!/usr/bin/env bash
# Stop and remove the launchd agents and the skill symlink. Keeps the database (~/.notifier).
set -euo pipefail

DOMAIN="gui/$(id -u)"
for label in com.notifier.watcher com.notifier.web; do
  launchctl bootout "$DOMAIN/$label" 2>/dev/null || true
  rm -f "$HOME/Library/LaunchAgents/$label.plist"
  echo "removed $label"
done

if [ -L "$HOME/.claude/skills/notify" ]; then
  rm "$HOME/.claude/skills/notify"
  echo "removed skill symlink"
fi
echo "Database left in place at ${NOTIFIER_HOME:-$HOME/.notifier}"
