# Version Change: Status Recovery and Palette

Date: 2026-05-30
Target tag: v0.1.0

## Changes

- Added persistent LaunchAgent config for the Agent-Lamp daemon.
- Kept the daemon on a persistent serial connection and disabled periodic redraw refresh by default.
- Added Codex transcript-based interruption detection so interrupted turns clear `running` to `ok`.
- Made Codex permission requests show `waiting` by default, then return to `running` after the approved tool completes.
- Displayed the submitted user prompt on `running` instead of only the generic working message.
- Kept assistant output bodies out of Tab5 messages to avoid sending long code blocks to the display.
- Added event and state metadata for debugging hook behavior.
- Added duplicate-state redraw protection in both firmware entry points.
- Updated state colors:
  - `idle`: dark gray
  - `running`: amber
  - `waiting`: blue
  - `ok`: green
  - `error`: red
- Added focused unit tests for hook mapping, state persistence, interruption handling, and daemon behavior.

## Verification

- `python3 -m unittest discover -s tests`
- `python3 -m py_compile host/agent_lamp.py host/agent_lamp_daemon.py host/hook_status.py tests/test_agent_lamp_daemon.py tests/test_hook_status.py`
- `plutil -lint launchd/com.peterjames.agent-lamp.plist`
- Live daemon checks for prompt display, permission waiting, interruption recovery, and no periodic redraw.
