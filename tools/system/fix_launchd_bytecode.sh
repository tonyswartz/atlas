#!/bin/bash
# Permanent fix: Add PYTHONDONTWRITEBYTECODE=1 to all atlas launchd plists
# This prevents Python from writing .pyc files, eliminating stale bytecode cache issues

PLIST_DIR="$HOME/Library/LaunchAgents"
BACKUP_DIR="$HOME/Library/LaunchAgents/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

echo "Adding PYTHONDONTWRITEBYTECODE=1 to all atlas launchd services..."

for plist in "$PLIST_DIR"/com.atlas.*.plist; do
  if [ ! -f "$plist" ]; then
    continue
  fi

  basename=$(basename "$plist")

  # Check if already has EnvironmentVariables
  if grep -q "EnvironmentVariables" "$plist"; then
    echo "  ⏭️  $basename already has EnvironmentVariables - skipping"
    continue
  fi

  # Backup original
  cp "$plist" "$BACKUP_DIR/${basename%.plist}_${TIMESTAMP}.plist"

  # Add EnvironmentVariables section before closing </dict>
  # This adds it as the last key in the plist
  sed -i '' '/<\/dict>$/i\
\  <key>EnvironmentVariables</key>\
\  <dict>\
\    <key>PYTHONDONTWRITEBYTECODE</key>\
\    <string>1</string>\
\  </dict>
' "$plist"

  echo "  ✅ Updated $basename"
done

echo ""
echo "Reloading all atlas launchd services..."
for plist in "$PLIST_DIR"/com.atlas.*.plist; do
  basename=$(basename "$plist" .plist)
  launchctl unload "$plist" 2>/dev/null || true
  launchctl load "$plist"
done

echo ""
echo "Done! All atlas services now run with PYTHONDONTWRITEBYTECODE=1"
echo "Backups saved to: $BACKUP_DIR"
