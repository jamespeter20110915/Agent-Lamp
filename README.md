# Agent-Lamp

Agent-Lamp is an M5Stack Tab5 agent status indicator for Claude Code and Codex.

The first version uses USB serial because it works without Wi-Fi setup. The Mac sends a compact status line to the Tab5, and the Tab5 renders a full-screen state:

- `idle` / `ok`: green
- `running` / `waiting`: yellow
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

## Host CLI

List likely ports:

```bash
./host/agent-lamp ports
```

If more than one port is listed, set the one for Tab5:

```bash
export AGENT_LAMP_PORT=/dev/cu.usbmodem1101
```

Send test states:

```bash
./host/agent-lamp set running --agent codex --repo Agent-Lamp --message "Working"
./host/agent-lamp set waiting --agent codex --repo Agent-Lamp --message "Needs approval"
./host/agent-lamp set ok --agent codex --repo Agent-Lamp --message "Done"
./host/agent-lamp set error --agent codex --repo Agent-Lamp --message "Failed"
```

If `pyserial` is installed, the CLI uses it. If not, it writes directly to the serial device path.

## Claude Code Hook

Use `hooks/claude/settings.example.json` as the reference. Copy the `hooks` block into your Claude Code settings and keep the command path absolute:

```text
/Users/peterjames/study/Code/Agent-Lamp/hooks/claude/status-hook.sh
```

## Codex Hook

Codex hooks may run in an app sandbox that cannot open `/dev/cu.*` directly. Use the queue bridge: keep one Terminal process running outside Codex, and let Codex hooks write status lines to `/private/tmp/agent-lamp-queue.tsv`.

Start the bridge in Terminal:

```bash
cd /Users/peterjames/study/Code/Agent-Lamp
./host/agent-lamp-daemon --port /dev/cu.usbmodem1101
```

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

1. Flash Tab5.
2. Run `./host/agent-lamp ports`.
3. Set `AGENT_LAMP_PORT`.
4. Manually test `running`, `ok`, and `error`.
5. Start `./host/agent-lamp-daemon --port /dev/cu.usbmodem1101`.
6. Enable one hook integration at a time.

Codex failure detection is based on `PostToolUse` responses with a non-zero `exit_code` or `success: false`. Other Codex failures may still need more event-specific mapping after observing real hook payloads.
