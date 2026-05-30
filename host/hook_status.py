#!/usr/bin/env python3
"""Map Claude Code or Codex hook JSON events to Tab5 lamp states."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


STATE_MESSAGES = {
    "running": "Agent is working",
    "waiting": "Waiting for approval or input",
    "ok": "Agent finished",
    "error": "Agent reported a failure",
}


def text_field(payload: dict, *names: str) -> str:
    for name in names:
        value = payload.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def repo_from_payload(payload: dict) -> str:
    cwd = text_field(payload, "cwd", "workspace", "project_dir")
    if cwd:
        return Path(cwd).name
    return Path.cwd().name


def tool_response_failed(payload: dict) -> bool:
    response = payload.get("tool_response")
    if isinstance(response, str):
        try:
            response = json.loads(response)
        except json.JSONDecodeError:
            return False

    if not isinstance(response, dict):
        return False

    success = response.get("success")
    if success is False:
        return True

    exit_code = response.get("exit_code", response.get("exitCode"))
    return isinstance(exit_code, int) and exit_code != 0


def state_for_event(agent: str, event: str, payload: dict) -> str | None:
    if event.endswith("Failure") or event in {"Error", "ToolFailure"}:
        return "error"

    if event == "PostToolUse":
        return "error" if tool_response_failed(payload) else "running"

    if event in {"UserPromptSubmit", "PreToolUse", "SubagentStart"}:
        return "running"

    if event in {"Notification", "PermissionRequest"}:
        return "waiting"

    if event in {"Stop", "SubagentStop"}:
        return "ok"

    if agent == "codex" and event in {"SessionStart"}:
        return "idle"

    if agent == "claude" and event in {"SessionStart"}:
        return "idle"

    return None


def message_for_payload(payload: dict, state: str) -> str:
    return (
        text_field(
            payload,
            "message",
            "notification",
            "notification_type",
            "tool_name",
            "last_assistant_message",
        )
        or STATE_MESSAGES[state]
    )


def protocol_line(agent: str, repo: str, state: str, message: str) -> str:
    fields = ("set", state, agent, repo, message)
    return "\t".join(field.replace("\t", " ").replace("\r", " ").replace("\n", " ").strip() for field in fields)


def write_queue(queue_path: str, line: str) -> bool:
    path = Path(queue_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as queue:
        queue.write(line + "\n")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", required=True, choices=("claude", "codex"))
    args = parser.parse_args(argv)

    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    event = text_field(payload, "hook_event_name", "event", "type")
    state = state_for_event(args.agent, event, payload)
    if not state:
        return 0

    repo = repo_from_payload(payload)
    message = message_for_payload(payload, state)
    line = protocol_line(args.agent, repo, state, message)
    queue_path = os.environ.get("AGENT_LAMP_QUEUE")
    if queue_path:
        try:
            write_queue(queue_path, line)
        except Exception:
            pass
        return 0

    script = Path(__file__).with_name("agent_lamp.py")
    command = [
        sys.executable,
        str(script),
        "set",
        state,
        "--agent",
        args.agent,
        "--repo",
        repo,
        "--message",
        message,
    ]

    try:
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
