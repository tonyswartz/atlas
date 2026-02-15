#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent Router for Atlas GOTCHA Framework

Routes tasks to specialized subagents based on keywords and context.
Each agent has focused goals, context, and args for their domain.

Usage:
    python router.py "Fix Telegram bot tool loop"
    python router.py --agent telegram "Debug conversation.py"
    python router.py --list-agents
"""

import sys
import argparse
import subprocess
from pathlib import Path
from typing import Optional

# Agent definitions with routing keywords
AGENTS = {
    "telegram": {
        "description": "Telegram bot conversation management, tool routing, session handling",
        "keywords": ["telegram", "bot", "conversation", "message", "chat", "jeeves"],
        "tools": ["telegram", "memory", "zapier", "research", "browser", "legalkanban", "capture"],
    },
    "bambu": {
        "description": "3D print tracking, spool management, BambuBuddy integration",
        "keywords": ["bambu", "print", "3d", "printer", "filament", "spool", "ams"],
        "tools": ["bambu", "memory"],
    },
    "legalkanban": {
        "description": "Case management, task sync, deadline tracking",
        "keywords": ["case", "legalkanban", "task sync", "deadline", "trial", "client"],
        "tools": ["legalkanban", "memory"],
    },
    "briefings": {
        "description": "News aggregation, weather, reminders, health monitoring, weekly reviews",
        "keywords": ["brief", "news", "weather", "reminder", "health", "wellness", "weekly", "review"],
        "tools": ["briefings", "memory"],
    },
    "system": {
        "description": "Automation config, health checks, backups, service monitoring",
        "keywords": ["cron", "launchd", "config", "monitor", "health", "backup", "service"],
        "tools": ["system", "heartbeat", "memory"],
    },
    "podcast": {
        "description": "Podcast production automation (Explore with Tony, Solo Law Club, 832 Weekends)",
        "keywords": ["podcast", "episode", "tts", "voice", "audio", "script", "explore", "sololaw", "832weekends"],
        "tools": ["podcast", "memory", "telegram"],
    },
}

DEFAULT_AGENT = "system"


def route_task(task_description: str) -> str:
    """
    Route task to appropriate agent based on keyword matching.

    Args:
        task_description: Natural language task description

    Returns:
        Agent name (e.g., "telegram", "bambu")
    """
    task_lower = task_description.lower()

    # Score each agent based on keyword matches
    scores = {}
    for agent_name, agent_config in AGENTS.items():
        score = sum(1 for keyword in agent_config["keywords"] if keyword in task_lower)
        if score > 0:
            scores[agent_name] = score

    # Return highest scoring agent, or default if no matches
    if scores:
        return max(scores.items(), key=lambda x: x[1])[0]

    return DEFAULT_AGENT


def list_agents():
    """Print all available agents and their descriptions."""
    print("\n🤖 Available Agents:\n")
    for agent_name, config in AGENTS.items():
        print(f"  {agent_name:15} — {config['description']}")
        print(f"  {'':15}   Keywords: {', '.join(config['keywords'][:5])}")
        print(f"  {'':15}   Tools: {', '.join(config['tools'])}")
        print()


def invoke_agent(agent_name: str, task: str, extra_args: list[str] = None):
    """
    Invoke Claude with agent-specific context.

    Args:
        agent_name: Which agent to invoke
        task: Task description
        extra_args: Additional CLI arguments for Claude
    """
    repo_root = Path(__file__).parent
    agent_dir = repo_root / "agents" / agent_name

    if not agent_dir.exists():
        print(f"❌ Agent '{agent_name}' not found at {agent_dir}")
        sys.exit(1)

    # Build Claude command with agent context
    claude_bin = Path.home() / ".local" / "bin" / "claude"

    cmd = [
        str(claude_bin),
        "-p",  # Non-interactive mode
        "--permission-mode", "dontAsk",
        "--disallowed-tools", "Bash(git:*)",  # Block git commands for safety
    ]

    # Add extra arguments if provided
    if extra_args:
        cmd.extend(extra_args)

    # Add task as final positional argument
    cmd.append(task)

    # Set environment to signal agent context
    import os
    env = os.environ.copy()
    env["ATLAS_AGENT"] = agent_name
    env["ATLAS_AGENT_DIR"] = str(agent_dir)

    print(f"🤖 Routing to {agent_name} agent...")
    print(f"📁 Agent directory: {agent_dir}")
    print(f"🎯 Task: {task}\n")

    # Execute Claude
    result = subprocess.run(cmd, env=env)
    sys.exit(result.returncode)


def main():
    parser = argparse.ArgumentParser(
        description="Route tasks to specialized Atlas agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  router.py "Fix Telegram bot tool loop"
  router.py --agent bambu "Why aren't prints being detected?"
  router.py --list-agents
        """
    )

    parser.add_argument(
        "task",
        nargs="?",
        help="Task description (natural language)"
    )

    parser.add_argument(
        "--agent", "-a",
        choices=list(AGENTS.keys()),
        help="Explicitly specify which agent to use"
    )

    parser.add_argument(
        "--list-agents", "-l",
        action="store_true",
        help="List all available agents"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show which agent would be selected without invoking"
    )

    # Collect unknown args to pass through to Claude
    args, extra_args = parser.parse_known_args()

    # Handle --list-agents
    if args.list_agents:
        list_agents()
        sys.exit(0)

    # Require task description
    if not args.task:
        parser.print_help()
        sys.exit(1)

    # Determine agent (explicit or auto-route)
    agent_name = args.agent if args.agent else route_task(args.task)

    if args.dry_run:
        print(f"Would route to: {agent_name}")
        print(f"Description: {AGENTS[agent_name]['description']}")
        sys.exit(0)

    # Invoke the agent
    invoke_agent(agent_name, args.task, extra_args)


if __name__ == "__main__":
    main()
