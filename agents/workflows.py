#!/usr/bin/env python3
"""
Multi-Agent Workflow Engine

Declarative workflows that coordinate multiple agents for complex tasks.
Inspired by OpenClaw's inter-agent coordination patterns.

Usage:
    from agents.workflows import WorkflowEngine

    engine = WorkflowEngine()

    # Trigger workflow
    engine.trigger("bambu", "print_complete", {
        "filename": "bracket.gcode",
        "spool_id": 5,
        "grams_used": 42
    })

Workflow Definition (YAML):
    name: "Print completion workflow"
    trigger:
      agent: bambu
      event: print_complete
    steps:
      - agent: bambu
        action: log_print
      - agent: telegram
        action: send_notification
        template: "Print done: {{filename}}"
      - agent: legalkanban
        action: create_task
        condition: "{{project_related}}"
"""

import json
import yaml
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, Any
import re


class WorkflowEngine:
    """Execute multi-agent workflows"""

    def __init__(self, workflows_dir: Optional[Path] = None):
        if workflows_dir is None:
            workflows_dir = Path(__file__).parent.parent / "workflows"

        self.workflows_dir = workflows_dir
        self.workflows_dir.mkdir(parents=True, exist_ok=True)
        self.workflows = self._load_workflows()

    def _load_workflows(self) -> list[dict]:
        """Load workflow definitions from YAML files"""
        workflows = []

        for workflow_file in self.workflows_dir.glob("*.yaml"):
            try:
                with open(workflow_file) as f:
                    workflow = yaml.safe_load(f)
                    workflow["_source_file"] = str(workflow_file)
                    workflows.append(workflow)
            except Exception as e:
                print(f"Error loading workflow {workflow_file}: {e}")

        return workflows

    def trigger(self, agent: str, event: str, data: dict) -> list[dict]:
        """
        Trigger workflows matching this agent and event.

        Args:
            agent: Source agent name
            event: Event name (e.g., "print_complete", "task_created")
            data: Event data

        Returns:
            List of workflow execution results
        """
        matching = [
            w for w in self.workflows
            if w.get("trigger", {}).get("agent") == agent
            and w.get("trigger", {}).get("event") == event
        ]

        if not matching:
            return []

        results = []
        for workflow in matching:
            result = self.execute_workflow(workflow, data)
            results.append(result)

        return results

    def execute_workflow(self, workflow: dict, initial_data: dict) -> dict:
        """
        Execute workflow steps sequentially.

        Args:
            workflow: Workflow definition
            initial_data: Initial data passed to first step

        Returns:
            {
                "workflow": str,
                "status": "success" | "failed",
                "steps": [...],
                "data": {...},
                "error": str (optional)
            }
        """
        workflow_name = workflow.get("name", "unnamed")
        steps = workflow.get("steps", [])
        data = initial_data.copy()

        result = {
            "workflow": workflow_name,
            "status": "running",
            "steps": [],
            "data": data,
            "started_at": datetime.now().isoformat()
        }

        for i, step in enumerate(steps):
            step_result = self._execute_step(step, data)

            result["steps"].append(step_result)

            if not step_result["success"]:
                result["status"] = "failed"
                result["error"] = step_result.get("error", "Unknown error")
                result["failed_at_step"] = i
                break

            # Merge step result into data for next step
            if "result" in step_result:
                data.update(step_result["result"])

        else:
            # All steps succeeded
            result["status"] = "success"

        result["completed_at"] = datetime.now().isoformat()
        result["data"] = data

        return result

    def _execute_step(self, step: dict, data: dict) -> dict:
        """
        Execute single workflow step.

        Args:
            step: Step definition
            data: Current workflow data

        Returns:
            {
                "agent": str,
                "action": str,
                "success": bool,
                "result": dict (optional),
                "error": str (optional)
            }
        """
        agent = step.get("agent")
        action = step.get("action")
        condition = step.get("condition")

        # Check condition if specified
        if condition:
            if not self._evaluate_condition(condition, data):
                return {
                    "agent": agent,
                    "action": action,
                    "success": True,
                    "skipped": True,
                    "reason": "Condition not met"
                }

        # Prepare step parameters
        params = step.get("params", {})
        params = self._interpolate_template(params, data)

        # Execute step
        try:
            if action == "send_message":
                # Inter-agent messaging
                from agents.messaging import send_message
                target = step.get("target")
                message = step.get("message", {})
                message = self._interpolate_template(message, data)
                send_message(agent, target, message)
                return {
                    "agent": agent,
                    "action": action,
                    "success": True
                }

            elif action == "send_notification":
                # Telegram notification
                from tools.common.credentials import get_telegram_token
                import urllib.request
                import urllib.parse

                template = step.get("template", "")
                message_text = self._interpolate_template(template, data)

                token = get_telegram_token()
                chat_id = step.get("chat_id", "8241581699")

                url = f"https://api.telegram.org/bot{token}/sendMessage"
                payload = urllib.parse.urlencode({
                    "chat_id": chat_id,
                    "text": message_text,
                    "parse_mode": "Markdown"
                }).encode()

                urllib.request.urlopen(url, payload)

                return {
                    "agent": agent,
                    "action": action,
                    "success": True
                }

            elif action == "run_script":
                # Execute Python script
                script = step.get("script")
                args = step.get("args", [])
                args = self._interpolate_template(args, data)

                cmd = ["/opt/homebrew/bin/python3", script] + args
                result = subprocess.run(cmd, capture_output=True, text=True)

                return {
                    "agent": agent,
                    "action": action,
                    "success": result.returncode == 0,
                    "result": {
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "returncode": result.returncode
                    }
                }

            else:
                # Generic action - invoke agent via router
                task_description = self._interpolate_template(
                    step.get("description", f"{action} with {params}"),
                    data
                )

                cmd = [
                    "/opt/homebrew/bin/python3",
                    str(Path(__file__).parent.parent / "router.py"),
                    "--agent", agent,
                    task_description
                ]

                result = subprocess.run(cmd, capture_output=True, text=True)

                return {
                    "agent": agent,
                    "action": action,
                    "success": result.returncode == 0,
                    "result": {
                        "stdout": result.stdout,
                        "stderr": result.stderr
                    }
                }

        except Exception as e:
            return {
                "agent": agent,
                "action": action,
                "success": False,
                "error": str(e)
            }

    def _evaluate_condition(self, condition: str, data: dict) -> bool:
        """
        Evaluate condition expression.

        Supports:
        - {{key}} == value
        - {{key}} != value
        - {{key}} > value
        - {{key}} < value
        """
        # Interpolate template variables
        condition = self._interpolate_template(condition, data)

        # Simple eval (safe for trusted workflows only)
        try:
            return bool(eval(condition))
        except:
            return False

    def _interpolate_template(self, template: Any, data: dict) -> Any:
        """
        Replace {{variable}} placeholders with data values.

        Args:
            template: String, dict, or list with {{placeholders}}
            data: Data dictionary

        Returns:
            Template with placeholders replaced
        """
        if isinstance(template, str):
            for key, value in data.items():
                placeholder = f"{{{{{key}}}}}"
                if placeholder in template:
                    template = template.replace(placeholder, str(value))
            return template

        elif isinstance(template, dict):
            return {k: self._interpolate_template(v, data) for k, v in template.items()}

        elif isinstance(template, list):
            return [self._interpolate_template(item, data) for item in template]

        else:
            return template

    def list_workflows(self) -> list[dict]:
        """List all loaded workflows"""
        return [
            {
                "name": w.get("name", "unnamed"),
                "trigger": w.get("trigger", {}),
                "steps": len(w.get("steps", [])),
                "source_file": w.get("_source_file")
            }
            for w in self.workflows
        ]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Workflow engine CLI")
    parser.add_argument("--list", action="store_true", help="List all workflows")
    parser.add_argument("--trigger", nargs=2, metavar=("AGENT", "EVENT"), help="Trigger workflows")
    parser.add_argument("--data", help="Event data (JSON)")
    parser.add_argument("--reload", action="store_true", help="Reload workflow definitions")

    args = parser.parse_args()

    engine = WorkflowEngine()

    if args.list:
        workflows = engine.list_workflows()
        print(f"\nLoaded Workflows ({len(workflows)}):\n")
        for wf in workflows:
            print(f"  📋 {wf['name']}")
            print(f"      Trigger: {wf['trigger']['agent']}.{wf['trigger']['event']}")
            print(f"      Steps: {wf['steps']}")
            print(f"      File: {wf['source_file']}")
            print()

    elif args.trigger:
        agent, event = args.trigger
        data = json.loads(args.data) if args.data else {}

        print(f"Triggering {agent}.{event} with data: {data}\n")

        results = engine.trigger(agent, event, data)

        if not results:
            print("No matching workflows found")
        else:
            for result in results:
                print(f"Workflow: {result['workflow']}")
                print(f"Status: {result['status']}")
                print(f"Steps executed: {len(result['steps'])}")
                if result['status'] == "failed":
                    print(f"Error: {result.get('error')}")
                print()

    elif args.reload:
        engine.workflows = engine._load_workflows()
        print(f"✓ Reloaded {len(engine.workflows)} workflow(s)")

    else:
        parser.print_help()
