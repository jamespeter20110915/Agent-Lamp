# Agent-Lamp

Agent-Lamp is an M5Stack Tab5 agent status indicator for Claude Code and Codex.

The next version is wireless by default: the Tab5 joins Wi-Fi, exposes a tiny
HTTP status endpoint, and the Mac sends compact status lines over the local
network. USB serial remains available for first flash, recovery, and fallback
debugging, but daily desk use should not need a visible USB-C connection.

The Tab5 renders a full-screen state:

- `idle`: dark gray
- `running`: amber
- `waiting`: blue
- `ok`: green
- `error`: red

Project convention: use `Agent-Lamp` for the repository and display name, and keep `agent-lamp` for local command/script names.

## GitHub

Create an empty GitHub repository named `Agent-Lamp`, without a generated README, `.gitignore`, or license. Then connect and push from the project folder:

```bash
cd /Users/peterjames/study/Code/Agent-Lamp
git init
git add .
git commit -m "Initial Agent-Lamp prototype"
git branch -M main
git remote add origin git@github.com:YOUR_USER/Agent-Lamp.git
git push -u origin main
```

If you prefer HTTPS, use this remote instead:

```bash
git remote add origin https://github.com/YOUR_USER/Agent-Lamp.git
```

## Software To Use

Use the Arduino framework, but manage it with PlatformIO instead of starting with the Arduino IDE.

Recommended setup:

1. Install VS Code.
2. Install the PlatformIO IDE extension.
3. Open `firmware/tab5-agent-lamp` in PlatformIO.
4. Connect the Tab5 over USB.
5. Build and upload the firmware.

Arduino IDE can work for quick sketches, but PlatformIO keeps board config, libraries, and build flags in the repo. That matters for the Tab5 because it uses ESP32-P4 support and M5Stack libraries.

## Arduino IDE

Arduino IDE opens sketches, not PlatformIO projects. Use this Arduino-compatible sketch:

```text
firmware/tab5_agent_lamp_arduino/tab5_agent_lamp_arduino.ino
```

Setup:

1. Open Arduino IDE 2.x.
2. On macOS, go to `Arduino IDE` -> `Settings...`, or press `Command + ,`.
3. Add this URL to `Additional Board Manager URLs`:

```text
https://static-cdn.m5stack.com/resource/arduino/package_m5stack_index.json
```

4. Open `Boards Manager`, search `M5Stack`, and install it.
5. Open `Library Manager`, install `M5Unified` and `M5GFX`; choose `Install All` if Arduino IDE asks about dependencies.
6. Use `File` -> `Open...`, then open:

```text
/Users/peterjames/study/Code/Agent-Lamp/firmware/tab5_agent_lamp_arduino/tab5_agent_lamp_arduino.ino
```

7. Select board `M5Tab5`.
8. Connect Tab5 over USB, select the matching port under `Tools` -> `Port`.
9. Click Upload.

If upload does not start, put Tab5 into download mode: connect USB or battery, long-press Reset for about 2 seconds until the internal green LED blinks rapidly, then release and upload again.

If `M5Stack` does not appear in Boards Manager, wait for `Downloading index: package_m5stack_index.json` to finish first. If it still does not appear, restart Arduino IDE and search again.

## Firmware

Build/upload:

```bash
cd firmware/tab5-agent-lamp
pio run -t upload
pio device monitor
```

The firmware accepts either a simple state:

```text
running
ok
error
```

or the host protocol:

```text
set<TAB>running<TAB>codex<TAB>Agent-Lamp<TAB>Agent is working
```

The same protocol works over HTTP after Wi-Fi is configured:

```text
POST http://agent-lamp.local/set
Content-Type: text/plain

set<TAB>running<TAB>codex<TAB>Agent-Lamp<TAB>Agent is working
```

Useful device endpoints:

```text
POST /set      plain text protocol line
GET  /ping     returns pong
GET  /status   returns the current protocol line
```

## Wireless Setup

Create a local Wi-Fi secrets header before building firmware. Do not commit the
real file.

For PlatformIO:

```bash
cp firmware/tab5-agent-lamp/include/agent_lamp_secrets.example.h firmware/tab5-agent-lamp/include/agent_lamp_secrets.h
```

For Arduino IDE:

```bash
cp firmware/tab5_agent_lamp_arduino/agent_lamp_secrets.example.h firmware/tab5_agent_lamp_arduino/agent_lamp_secrets.h
```

Edit the copied file:

```cpp
#define AGENT_LAMP_WIFI_SSID "Your Wi-Fi SSID"
#define AGENT_LAMP_WIFI_PASSWORD "Your Wi-Fi password"
#define AGENT_LAMP_HOSTNAME "agent-lamp"
```

Flash once over USB-C. After boot, the bottom of the Tab5 screen shows the HTTP
target, usually:

```text
http://agent-lamp.local/set
```

If mDNS is not available on your network, use the IP shown on the Tab5 instead.

## Host CLI

Set the wireless target:

```bash
export AGENT_LAMP_URL=http://agent-lamp.local
```

Send test states:

```bash
./host/agent-lamp set running --agent codex --repo Agent-Lamp --message "Working"
./host/agent-lamp set waiting --agent codex --repo Agent-Lamp --message "Needs approval"
./host/agent-lamp set ok --agent codex --repo Agent-Lamp --message "Done"
./host/agent-lamp set error --agent codex --repo Agent-Lamp --message "Failed"
```

You can also pass the wireless target directly:

```bash
./host/agent-lamp set running --transport http --lamp-url http://agent-lamp.local
```

USB serial is still available as a fallback. List likely ports:

```bash
./host/agent-lamp ports
```

If more than one port is listed, set the one for Tab5:

```bash
export AGENT_LAMP_PORT=/dev/cu.usbmodem1101
```

Send serial test states:

```bash
./host/agent-lamp set running --transport serial --agent codex --repo Agent-Lamp --message "Working"
./host/agent-lamp set waiting --transport serial --agent codex --repo Agent-Lamp --message "Needs approval"
./host/agent-lamp set ok --transport serial --agent codex --repo Agent-Lamp --message "Done"
./host/agent-lamp set error --transport serial --agent codex --repo Agent-Lamp --message "Failed"
```

If `pyserial` is installed, the CLI uses it. If not, it writes directly to the serial device path.

## Claude Code Hook

Use `hooks/claude/settings.example.json` as the reference. Copy the `hooks` block into your Claude Code settings and keep the command path absolute:

```text
/Users/peterjames/study/Code/Agent-Lamp/hooks/claude/status-hook.sh
```

## Codex Hook

Codex hooks may run in an app sandbox that cannot open device ports or make
network calls consistently. Use the queue bridge: keep one daemon running
outside Codex, and let Codex hooks write status lines to
`/private/tmp/agent-lamp-queue.tsv`.

Start the bridge manually in Terminal:

```bash
cd /Users/peterjames/study/Code/Agent-Lamp
./host/agent-lamp-daemon --transport http --lamp-url http://agent-lamp.local
```

Codex hooks only append status lines to the queue; the bridge is the process
that forwards those lines to the Tab5 over HTTP or serial. For daily use,
install the LaunchAgent so the bridge starts again after login:

```bash
cp launchd/com.peterjames.agent-lamp.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.peterjames.agent-lamp.plist
```

If the queue updates but the lamp does not, restart the bridge:

```bash
cd /Users/peterjames/study/Code/Agent-Lamp
./host/agent-lamp-daemon --transport http --lamp-url http://agent-lamp.local
```

The LaunchAgent resends the last known status every 5 seconds. That low-frequency
refresh lets a Tab5 recover after it reboots or reconnects to Wi-Fi while Codex
is already mid-turn. The firmware skips redraws when the status line has not
changed, so this should not create visible flicker.

Codex Desktop does not emit a hook event when a turn is interrupted. To avoid
leaving the lamp stuck in `running`, the daemon reads the Codex transcript path
recorded by the hook and clears `running` when that transcript records a
`turn_aborted` event.

Do not use a fixed `running` timeout for normal Codex work. During thinking or
long commands, Codex may not emit hook events for a long time, so a timeout can
incorrectly mark active work as `ok`. The timeout is disabled by default:

```bash
./host/agent-lamp-daemon --transport http --lamp-url http://agent-lamp.local --running-timeout 0 --refresh-interval 5
```

You can check whether hooks are writing status lines with:

```bash
tail -f /private/tmp/agent-lamp-queue.tsv
```

Codex hook behavior is intentionally conservative:

- `UserPromptSubmit` sets `running`.
- `running` uses a generic message instead of echoing the prompt, so sensitive
  prompt text is not shown on the device or copied into the status queue.
- `PermissionRequest` is hidden by default for Codex so command approvals do not
  flicker the lamp between `running`, `waiting`, and `running` during a turn.
- Set `AGENT_LAMP_SHOW_PERMISSION_REQUESTS=1` if you want real permission
  prompts to show as `waiting`. A successful `PostToolUse` after `waiting`
  sets `running`, so approved permissions do not leave the lamp stuck.
- `Notification` sets `waiting`.
- A successful `PostToolUse` is normally silent to avoid flickering during each
  tool call.
- A successful `PostToolUse` after `waiting` sets `running`.
- A failed `PostToolUse` sets `error`.
- `Stop` sets `ok`.

Then use `.codex/hooks.json` or `hooks/codex/hooks.example.json` as the Codex hook config reference. Keep the command path absolute:

```text
/Users/peterjames/study/Code/Agent-Lamp/hooks/codex/status-hook.sh
```

The Codex hook script writes to `AGENT_LAMP_QUEUE`, defaulting to:

```text
/private/tmp/agent-lamp-queue.tsv
```

## Next Step

The practical bring-up order is:

1. Copy `agent_lamp_secrets.example.h` to `agent_lamp_secrets.h` and set Wi-Fi credentials.
2. Flash Tab5 once over USB-C.
3. Boot it untethered and confirm the bottom line shows an HTTP target.
4. Set `AGENT_LAMP_URL=http://agent-lamp.local`, or use the displayed IP address.
5. Manually test `running`, `ok`, and `error`.
6. Start `./host/agent-lamp-daemon --transport http --lamp-url http://agent-lamp.local`.
7. Enable one hook integration at a time.

Codex failure detection is based on `PostToolUse` responses with a non-zero `exit_code` or `success: false`. Other Codex failures may still need more event-specific mapping after observing real hook payloads.
