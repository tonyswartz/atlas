#!/bin/bash
# Add Python -B flag to all atlas launchd services
# This makes Python ignore bytecode cache even if it exists

PLIST_DIR="$HOME/Library/LaunchAgents"
BACKUP_DIR="$PLIST_DIR/backups/$(date +%Y%m%d_%H%M%S)"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# List of critical services that use Python (add more as needed)
SERVICES=(
    "com.atlas.daily-brief"
    "com.atlas.local-news"
    "com.atlas.wa-dui-tracker"
    "com.atlas.watchdog"
    "com.atlas.weekly-review"
)

echo "Adding Python -B flag to critical services..."
echo "Backups will be saved to: $BACKUP_DIR"
echo ""

for service in "${SERVICES[@]}"; do
    plist="$PLIST_DIR/${service}.plist"

    if [[ ! -f "$plist" ]]; then
        echo "⚠️  Skipping $service (plist not found)"
        continue
    fi

    # Backup
    cp "$plist" "$BACKUP_DIR/"

    # Check if -B flag already exists
    if grep -q "<string>-B</string>" "$plist"; then
        echo "✓  $service (already has -B flag)"
        continue
    fi

    # Check if this plist has python3 in ProgramArguments
    if ! grep -q "/python3</string>" "$plist"; then
        echo "⚠️  Skipping $service (no python3 found)"
        continue
    fi

    # Add -B flag after python3 using sed
    # Pattern: Find </string> after python3, insert <string>-B</string> on next line
    sed -i '' '/<string>.*\/python3<\/string>/a\
		<string>-B</string>
' "$plist"

    echo "✓  $service (added -B flag)"

    # Reload the service
    launchctl unload "$plist" 2>/dev/null
    launchctl load "$plist" 2>/dev/null
done

echo ""
echo "Done! Services reloaded."
echo "Verify with: launchctl list | grep atlas"
