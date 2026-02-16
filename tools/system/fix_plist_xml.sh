#!/bin/bash
# Fix malformed plists: remove EnvironmentVariables from inside nested dicts

PLIST_DIR="$HOME/Library/LaunchAgents"

echo "Fixing malformed plist XML structure..."

for plist in "$PLIST_DIR"/com.atlas.*.plist; do
  if [ ! -f "$plist" ]; then
    continue
  fi

  basename=$(basename "$plist")

  # Check if plist is valid
  if ! plutil -lint "$plist" >/dev/null 2>&1; then
    echo "  🔧 Fixing $basename"

    # Use Python to properly fix the XML
    python3 -c "
import xml.etree.ElementTree as ET
import sys

plist_path = '$plist'
tree = ET.parse(plist_path)
root = tree.getroot()

# Get the main dict
main_dict = root.find('dict')
if main_dict is None:
    sys.exit(0)

# Find all 'key' elements
keys_to_remove = []
dicts_to_remove = []
i = 0
while i < len(main_dict):
    elem = main_dict[i]

    # Look for nested dicts that contain EnvironmentVariables
    if elem.tag == 'dict':
        for j in range(len(elem)):
            if elem[j].tag == 'key' and elem[j].text == 'EnvironmentVariables':
                # This is EnvironmentVariables inside a nested dict - mark for removal
                # Remove the key and the following dict
                if j + 1 < len(elem) and elem[j+1].tag == 'dict':
                    elem.remove(elem[j+1])
                elem.remove(elem[j])
                break
    i += 1

# Write back
tree.write(plist_path, encoding='UTF-8', xml_declaration=True)
print(f'Fixed {plist_path}')
" || echo "  ❌ Failed to fix $basename"

  fi
done

echo ""
echo "Reloading all atlas services..."
for plist in "$PLIST_DIR"/com.atlas.*.plist; do
  basename=$(basename "$plist" .plist)
  launchctl unload "$plist" 2>/dev/null || true
  launchctl load "$plist" 2>/dev/null || true
done

echo "Done!"
