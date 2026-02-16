#!/usr/bin/env bash
# Install Atlas launchd jobs (envchain-based). Replaces crontab for these jobs.
# Usage: ./launchd/install-launchd.sh [--unload]
# Run from repo root.

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEST="$HOME/Library/LaunchAgents"
DOMAIN="gui/$(id -u)"

LABELS=(
  com.atlas.bambu-watcher
  com.atlas.bambu-watcher-health
  com.atlas.daily-brief
  com.atlas.git-sync
  com.atlas.git-sync-deferred-restart
  com.atlas.wa-dui-bill-tracker
  com.atlas.local-news
  com.atlas.research-brief
  com.atlas.rotary-print-agenda
  com.atlas.watchdog
)

mkdir -p "$REPO_ROOT/logs"

unload() {
  for label in "${LABELS[@]}"; do
    launchctl bootout "$DOMAIN" "$label" 2>/dev/null || true
  done
  echo "Unloaded all Atlas launchd jobs."
}

if [[ "${1:-}" == "--unload" ]]; then
  unload
  exit 0
fi

mkdir -p "$DEST"
for plist in "$SCRIPT_DIR"/com.atlas.*.plist; do
  [[ -f "$plist" ]] || continue
  name="$(basename "$plist")"
  cp "$plist" "$DEST/$name"
  echo "Installed $name"
done

unload 2>/dev/null || true
for plist in "$SCRIPT_DIR"/com.atlas.*.plist; do
  [[ -f "$plist" ]] || continue
  name="$(basename "$plist")"
  label="${name%.plist}"
  launchctl bootstrap "$DOMAIN" "$DEST/$name"
  echo "Loaded $label"
done
echo "Done. Atlas scheduled jobs are now run by launchd (with envchain). Logs: $REPO_ROOT/logs/"
