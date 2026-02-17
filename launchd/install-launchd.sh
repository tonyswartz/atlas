#!/usr/bin/env bash
# Install Atlas launchd jobs (envchain-based). Replaces crontab for these jobs.
# Usage: ./launchd/install-launchd.sh [--unload]
# Run from repo root.

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEST="$HOME/Library/LaunchAgents"
DOMAIN="gui/$(id -u)"

mkdir -p "$REPO_ROOT/logs"

# Build list of labels from plists we have (so unload matches what we load)
LABELS=()
for plist in "$SCRIPT_DIR"/com.atlas.*.plist; do
  [[ -f "$plist" ]] || continue
  name="$(basename "$plist" .plist)"
  LABELS+=( "$name" )
done

unload() {
  for label in "${LABELS[@]}"; do
    launchctl bootout "$DOMAIN" "$label" 2>/dev/null || true
  done
  echo "Unloaded Atlas launchd jobs."
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
# Brief pause so launchd domain is ready (avoids "Bootstrap failed: 5: Input/output error" in some environments)
sleep 1
# Load one at a time so we see which job fails (bootstrap can return 5 / I-O error)
FAILED=0
set +e
for plist in "$SCRIPT_DIR"/com.atlas.*.plist; do
  [[ -f "$plist" ]] || continue
  name="$(basename "$plist")"
  label="${name%.plist}"
  err="$(launchctl bootstrap "$DOMAIN" "$DEST/$name" 2>&1)"
  rc=$?
  if [[ $rc -eq 0 ]]; then
    echo "Loaded $label"
  else
    echo "Failed to load $label (exit $rc)" >&2
    [[ -n "$err" ]] && echo "$err" >&2
    FAILED=1
  fi
done
set -e
if [[ $FAILED -eq 1 ]]; then
  echo "Some jobs failed to load. Run from a logged-in GUI session (not SSH) if you use LaunchAgents. Logs: $REPO_ROOT/logs/" >&2
  exit 1
fi
echo "Done. Atlas scheduled jobs are now run by launchd (with envchain). Logs: $REPO_ROOT/logs/"
