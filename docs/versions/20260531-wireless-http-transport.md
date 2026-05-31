# Version Change: Wireless HTTP Transport

Date: 2026-05-31
Target tag: v0.2.0

## Goal

Remove the visible USB-C runtime connection. USB stays available for flashing
and fallback debugging, but the normal desk setup should be an untethered Tab5
that receives status updates over local Wi-Fi.

## Changes

- Added host-side HTTP transport alongside the existing serial transport.
- Kept `auto` transport mode: HTTP is used when `AGENT_LAMP_URL`,
  `AGENT_LAMP_HOST`, `--lamp-url`, or `--lamp-host` is configured; otherwise
  the CLI and daemon continue using serial.
- Added a Tab5 HTTP server with:
  - `POST /set` for the existing text protocol.
  - `GET /ping` for reachability checks.
  - `GET /status` for the current status line.
- Added optional mDNS hostname support through `AGENT_LAMP_HOSTNAME`, defaulting
  to `agent-lamp`.
- Added ignored local Wi-Fi secrets headers and committed example headers for
  PlatformIO and Arduino IDE.
- Updated the LaunchAgent example to run the daemon against
  `http://agent-lamp.local`.
- Updated README bring-up steps so daily use is wireless by default.

## Verification

- `python3 -m py_compile host/agent_lamp.py host/agent_lamp_daemon.py host/hook_status.py tests/test_agent_lamp.py tests/test_agent_lamp_daemon.py tests/test_hook_status.py`
- `python3 -m unittest discover -s tests`
- `"/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli" compile --fqbn m5stack:esp32:m5stack_tab5 --build-path /private/tmp/agent-lamp-arduino-build --output-dir /private/tmp/agent-lamp-arduino-output firmware/tab5_agent_lamp_arduino`
- `./host/agent-lamp set running --transport serial --port /dev/cu.usbmodem1101 --agent codex --repo Agent-Lamp --message "Serial fallback test"`
- `./host/agent-lamp set ok --transport serial --port /dev/cu.usbmodem1101 --agent codex --repo Agent-Lamp --message "Serial fallback works"`
- `"/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli" upload --fqbn m5stack:esp32:m5stack_tab5 -p /dev/cu.usbmodem1101 --input-dir /private/tmp/agent-lamp-arduino-output firmware/tab5_agent_lamp_arduino`
- Serial boot log showed Wi-Fi connected at `192.168.3.147` and mDNS advertised `http://agent-lamp.local`.
- `http://192.168.3.147/ping` and `http://agent-lamp.local/ping` returned `pong`.
- `./host/agent-lamp set ok --transport http --lamp-url http://agent-lamp.local --agent codex --repo Agent-Lamp --message "Wireless mDNS works"`
- Installed and reloaded the LaunchAgent with `--transport http --lamp-url http://agent-lamp.local`.
- Added hook message redaction for password/token-like prompt content, stopped echoing user prompts as `running` messages, and cleared temporary Agent-Lamp queue/log files from the bring-up session.
- Made the daemon recover if the queue file is truncated while it is already following the file.
- Added transcript-based `task_complete` recovery so the daemon can clear `running` even if the Codex `Stop` hook is missed or its queue line is not consumed.
- Hid Codex `PermissionRequest` status changes by default, keeping the Tab5 on
  `running` during command approvals unless `AGENT_LAMP_SHOW_PERMISSION_REQUESTS=1`
  is explicitly configured.
- Reworked the Tab5 screen from full-color warning panels into a dark status
  dashboard with a state accent rail, header pill, large central state, message
  card, agent/workspace cards, and compact Wi-Fi status.
- Changed the wireless LaunchAgent to resend the last known status every 5
  seconds, so a Tab5 that reboots or reconnects after the daemon is already
  running can recover from firmware-default `idle` without waiting for the next
  Codex hook event.

## Not Verified Yet

- PlatformIO compile, because `pio` is not installed in the current shell.
- Live flashing of the redesigned UI, because no `/dev/cu.usbmodem*` Tab5 port
  was connected when the firmware compile passed.
