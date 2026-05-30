#!/usr/bin/env python3
"""Map Claude Code or Codex hook JSON events to Tab5 lamp states."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time


STATE_MESSAGES = {
    "running": "Agent is working",
    "waiting": "Waiting for approval or input",
    "ok": "Agent finished",
    "error": "Agent reported a failure",
}
MAX_FIELD_LENGTH = 120
DEFAULT_STATE_FILE = "/private/tmp/agent-lamp-state.json"
DEFAULT_EVENT_LOG = "/private/tmp/agent-lamp-events.jsonl"


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


def state_for_event(
    agent: str,
    event: str,
    payload: dict,
    previous_state: str | None = None,
    *,
    show_permission_requests: bool = True,
) -> str | None:
    if event.endswith("Failure") or event in {"Error", "ToolFailure"}:
        return "error"

    if event == "PostToolUse":
        if tool_response_failed(payload):
            return "error"
        return "running" if previous_state == "waiting" else None

    if event in {"UserPromptSubmit", "PreToolUse", "SubagentStart"}:
        return "running"

    if event == "Notification":
        return "waiting"

    if event == "PermissionRequest":
        if agent == "codex" and not show_permission_requests:
            return None
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
            "prompt",
            "notification",
            "notification_type",
            "tool_name",
        )
        or STATE_MESSAGES[state]
    )


def sanitize_protocol_field(value: str, max_len: int = MAX_FIELD_LENGTH) -> str:
    return value.replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()[:max_len]


def protocol_line(agent: str, repo: str, state: str, message: str) -> str:
    fields = ("set", state, agent, repo, message)
    return "\t".join(sanitize_protocol_field(field) for field in fields)


def write_queue(queue_path: str, line: str) -> bool:
    path = Path(queue_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as queue:
        queue.write(line + "\n")
    return True


def read_previous_state(state_path: str) -> str | None:
    path = Path(state_path).expanduser()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    state = data.get("state")
    return state if isinstance(state, str) else None


def write_state_file(
    state_path: str,
    *,
    state: str,
    agent: str,
    repo: str,
    message: str,
    event: str,
    payload: dict | None = None,
) -> None:
    payload = payload or {}
    path = Path(state_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "state": state,
                "agent": agent,
                "repo": repo,
                "message": message,
                "event": event,
                "session_id": payload.get("session_id"),
                "turn_id": payload.get("turn_id"),
                "transcript_path": payload.get("transcript_path"),
                "updated_at": time.time(),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def event_log_record(
    *,
    agent: str,
    event: str,
    payload: dict,
    previous_state: str | None,
    state: str | None,
) -> dict:
    response = payload.get("tool_response")
    if isinstance(response, str):
        try:
            response = json.loads(response)
        except json.JSONDecodeError:
            response = None

    tool_result: dict[str, object] = {}
    if isinstance(response, dict):
        for key in ("success", "exit_code", "exitCode"):
            if key in response:
                tool_result[key] = response[key]

    return {
        "time": time.time(),
        "agent": agent,
        "event": event,
        "state": state,
        "previous_state": previous_state,
        "session_id": payload.get("session_id"),
        "turn_id": payload.get("turn_id"),
        "transcript_path": payload.get("transcript_path"),
        "tool_name": payload.get("tool_name"),
        "notification_type": payload.get("notification_type"),
        "permission_mode": payload.get("permission_mode"),
        "stop_hook_active": payload.get("stop_hook_active"),
        "payload_keys": sorted(payload.keys()),
        "tool_result": tool_result,
    }


def write_event_log(log_path: str, record: dict) -> None:
    path = Path(log_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as log:
        log.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", required=True, choices=("claude", "codex"))
    args = parser.parse_args(argv)

    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    event = text_field(payload, "hook_event_name", "event", "type")
    state_path = os.environ.get("AGENT_LAMP_STATE_FILE", DEFAULT_STATE_FILE)
    previous_state = read_previous_state(state_path)
    show_permission_requests = os.environ.get("AGENT_LAMP_SHOW_PERMISSION_REQUESTS", "1") != "0"
    if os.environ.get("AGENT_LAMP_HIDE_PERMISSION_REQUESTS") == "1":
        show_permission_requests = False
    state = state_for_event(
        args.agent,
        event,
        payload,
        previous_state,
        show_permission_requests=show_permission_requests,
    )
    event_log_path = os.environ.get("AGENT_LAMP_EVENT_LOG", DEFAULT_EVENT_LOG)
    try:
        write_event_log(
            event_log_path,
            event_log_record(
                agent=args.agent,
                event=event,
                payload=payload,
                previous_state=previous_state,
                state=state,
            ),
        )
    except Exception:
        pass
    if not state:
        return 0

    repo = repo_from_payload(payload)
    message = message_for_payload(payload, state)
    line = protocol_line(args.agent, repo, state, message)
    queue_path = os.environ.get("AGENT_LAMP_QUEUE")
    if queue_path:
        try:
            write_queue(queue_path, line)
            write_state_file(
                state_path,
                state=state,
                agent=args.agent,
                repo=repo,
                message=message,
                event=event,
                payload=payload,
            )
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
        write_state_file(
            state_path,
            state=state,
            agent=args.agent,
            repo=repo,
            message=message,
            event=event,
            payload=payload,
        )
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
