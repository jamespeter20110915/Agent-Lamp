#!/usr/bin/env python3
"""Forward queued hook status updates to the agent lamp serial device."""

from __future__ import annotations

import argparse
from pathlib import Path
import time

from agent_lamp import pick_port, send_serial


def follow_queue(path: Path, *, port: str | None, baud: int, open_delay: float, poll_interval: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    serial_port = pick_port(port)

    with path.open("r", encoding="utf-8") as queue:
        queue.seek(0, 2)
        print(f"agent-lamp bridge watching {path}", flush=True)
        print(f"agent-lamp bridge sending to {serial_port}", flush=True)
        while True:
            line = queue.readline()
            if not line:
                time.sleep(poll_interval)
                continue

            command = line.rstrip("\n")
            if not command:
                continue

            try:
                send_serial(serial_port, baud, command, open_delay)
                print(f"sent: {command}", flush=True)
            except Exception as exc:
                print(f"send failed: {exc}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(prog="agent-lamp-daemon")
    parser.add_argument(
        "--queue",
        default="/private/tmp/agent-lamp-queue.tsv",
        help="Queue file written by hooks.",
    )
    parser.add_argument("--port", help="Serial port, for example /dev/cu.usbmodem1101.")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--open-delay", type=float, default=0.15)
    parser.add_argument("--poll-interval", type=float, default=0.1)
    args = parser.parse_args()

    try:
        follow_queue(
            Path(args.queue).expanduser(),
            port=args.port,
            baud=args.baud,
            open_delay=args.open_delay,
            poll_interval=args.poll_interval,
        )
    except KeyboardInterrupt:
        print("\nagent-lamp bridge stopped", flush=True)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
