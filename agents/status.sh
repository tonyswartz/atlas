#!/bin/bash
# Agent Status Dashboard
# Shows which agents exist, their goals, and tools

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "═══════════════════════════════════════════════════════════════"
echo "  Atlas Agent Status Dashboard"
echo "═══════════════════════════════════════════════════════════════"
echo ""

for agent_dir in "$SCRIPT_DIR"/*/; do
    agent_name=$(basename "$agent_dir")

    # Skip files (only process directories)
    [ -d "$agent_dir" ] || continue

    # Skip special directories
    [[ "$agent_name" =~ ^(README|QUICKSTART) ]] && continue

    echo "🤖 Agent: $agent_name"
    echo "   Directory: $agent_dir"

    # Count goals
    goal_count=$(find "$agent_dir/goals" -type f -name "*.md" 2>/dev/null | wc -l | tr -d ' ')
    echo "   Goals: $goal_count"

    # List goal files
    if [ -d "$agent_dir/goals" ]; then
        for goal in "$agent_dir/goals"/*.md; do
            [ -f "$goal" ] && echo "     - $(basename "$goal")"
        done
    fi

    # Count context files
    context_count=$(find "$agent_dir/context" -type f -name "*.md" 2>/dev/null | wc -l | tr -d ' ')
    echo "   Context files: $context_count"

    # Check for args file
    if [ -f "$agent_dir/args/$agent_name.yaml" ]; then
        echo "   Args: ✓ $agent_name.yaml"
    else
        echo "   Args: ✗ Missing"
    fi

    echo ""
done

echo "─────────────────────────────────────────────────────────────────"
echo "Usage:"
echo "  python ../router.py \"task description\"           # Auto-route"
echo "  python ../router.py --agent telegram \"task\"      # Explicit"
echo "  python ../router.py --list-agents                # List all"
echo ""
echo "Documentation:"
echo "  cat README.md        # Full architecture guide"
echo "  cat QUICKSTART.md    # Quick usage examples"
echo "═══════════════════════════════════════════════════════════════"
