#!/usr/bin/env bash
# Install the notifier: venv, terminal-notifier, database, launchd agents, and the Claude Code skill.
# Safe to re-run; it reloads the launchd agents.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/.venv"
HOME_DIR="${NOTIFIER_HOME:-$HOME/.notifier}"
LOGDIR="$HOME_DIR/logs"
AGENTS_DIR="$HOME/Library/LaunchAgents"
SKILL_DST="$HOME/.claude/skills/notify"
DOMAIN="gui/$(id -u)"

echo "==> Python environment ($VENV)"
[ -d "$VENV" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -e "$ROOT"

echo "==> terminal-notifier"
if ! command -v terminal-notifier >/dev/null 2>&1; then
  brew install terminal-notifier
fi
TN_BIN="$(command -v terminal-notifier)"

# Find the .app bundle behind the CLI. Homebrew's bin/terminal-notifier is a wrapper
# script that execs <bundle>/Contents/MacOS/terminal-notifier.
tn_app() {
  local exe
  exe="$(grep -o '/[^"]*\.app/Contents/MacOS/terminal-notifier' "$TN_BIN" 2>/dev/null | head -1 || true)"
  if [ -n "$exe" ]; then
    (cd "$(dirname "$exe")/../.." && pwd)
  elif command -v brew >/dev/null 2>&1 && [ -d "$(brew --prefix terminal-notifier 2>/dev/null)/terminal-notifier.app" ]; then
    echo "$(brew --prefix terminal-notifier)/terminal-notifier.app"
  fi
}
TN_APP="$(tn_app)"

# The brew build is ad-hoc signed. macOS rejects its notifications, and it never shows up in
# System Settings > Notifications, until LaunchServices has registered the bundle and it has
# been launched once as an app. Re-run this script after `brew upgrade terminal-notifier`
# (the bundle path changes with each version).
if [ -n "$TN_APP" ] && [ -d "$TN_APP" ]; then
  echo "    registering $TN_APP"
  /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$TN_APP"
  open -W "$TN_APP" --args -title "Agent Notifier" -message "Notifications enabled" || true
else
  echo "    WARNING: could not find terminal-notifier.app behind $TN_BIN; skipping registration"
fi

# Confirm macOS accepts notifications now. Warn instead of failing so the rest still installs;
# the watcher keeps notifications queued and retries until this is fixed.
if tn_out="$("$TN_BIN" -title "Agent Notifier" -message "Install check" 2>&1)"; then
  echo "    notifications OK"
  TN_OK=1
else
  TN_OK=0
  echo "    WARNING: terminal-notifier still can't post notifications: $tn_out"
  echo "    Open System Settings > Notifications, allow terminal-notifier, then re-run this script."
  open "x-apple.systempreferences:com.apple.Notifications-Settings.extension" 2>/dev/null || true
fi

echo "==> Database"
mkdir -p "$LOGDIR"
"$VENV/bin/notifier" init

echo "==> launchd agents"
mkdir -p "$AGENTS_DIR"
for name in watcher web; do
  label="com.notifier.$name"
  dst="$AGENTS_DIR/$label.plist"
  sed -e "s#__VENV__#$VENV#g" -e "s#__LOGDIR__#$LOGDIR#g" "$ROOT/launchd/$label.plist" > "$dst"
  launchctl bootout "$DOMAIN/$label" 2>/dev/null || true
  launchctl bootstrap "$DOMAIN" "$dst"
  echo "    loaded $label"
done

echo "==> Claude Code skill ($SKILL_DST)"
mkdir -p "$(dirname "$SKILL_DST")"
if [ -L "$SKILL_DST" ] || [ ! -e "$SKILL_DST" ]; then
  ln -sfn "$ROOT/skill/notify" "$SKILL_DST"
else
  echo "    $SKILL_DST exists and is not a symlink; leaving it alone"
fi

echo
echo "Done. Inbox: http://127.0.0.1:${NOTIFIER_PORT:-8765}/"
echo "Try:  echo '<p>Hello from the notifier.</p>' | $VENV/bin/notifier send -s 'Notifier installed' --source setup"
if [ "$TN_OK" = 1 ]; then
  echo "Tip: set terminal-notifier to 'Alerts' in System Settings > Notifications so popups stay until dismissed."
else
  echo "Popups are NOT working yet (see the warning above). Notifications will queue until they are."
fi
