#!/usr/bin/env python3
"""Forward queued hook status updates to the agent lamp serial device."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import time

from agent_lamp import list_ports, pick_port


def resolve_serial_port(configured_port: str | None) -> str:
    if not configured_port:
        return pick_port(None)

    if Path(configured_port).exists():
        return configured_port

    ports = list_ports()
    if len(ports) == 1:
        return ports[0]

    return configured_port


class PersistentSerialSender:
    def __init__(
        self,
        port: str | None,
        baud: int,
        open_delay: float,
        *,
        direct_opener: Callable[[str], object] | None = None,
        port_resolver: Callable[[str | None], str] = resolve_serial_port,
        use_pyserial: bool = True,
    ) -> None:
        self.port = port
        self.baud = baud
        self.open_delay = open_delay
        self.direct_opener = direct_opener or self._open_direct
        self.port_resolver = port_resolver
        self.use_pyserial = use_pyserial
        self._conn: object | None = None

    def _open_direct(self, port: str) -> object:
        return open(port, "wb", buffering=0)

    def _open(self) -> object:
        serial_port = self.port_resolver(self.port)
        if self.use_pyserial:
            try:
                import serial  # type: ignore
            except ImportError:
                pass
            else:
                conn = serial.Serial(port=serial_port, baudrate=self.baud, timeout=1, write_timeout=1)
                time.sleep(self.open_delay)
                return conn

        time.sleep(self.open_delay)
        return self.direct_opener(serial_port)

    def send(self, line: str) -> None:
        payload = (line.rstrip("\n") + "\n").encode("utf-8")
        if self._conn is None:
            self._conn = self._open()

        try:
            self._conn.write(payload)  # type: ignore[attr-defined]
            self._conn.flush()  # type: ignore[attr-defined]
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        if self._conn is None:
            return
        try:
            self._conn.close()  # type: ignore[attr-defined]
        finally:
            self._conn = None


@dataclass
class LastStatus:
    state: str
    agent: str
    repo: str
    message: str
    updated_at: float


def parse_status_line(line: str, updated_at: float) -> LastStatus | None:
    fields = line.split("\t", 4)
    if len(fields) < 4 or fields[0] != "set":
        return None

    state = fields[1].strip().lower()
    if state not in {"idle", "running", "waiting", "ok", "error"}:
        return None

    return LastStatus(
        state=state,
        agent=fields[2].strip() or "agent",
        repo=fields[3].strip() or "workspace",
        message=fields[4].strip() if len(fields) > 4 else "",
        updated_at=updated_at,
    )


def status_line(status: LastStatus) -> str:
    return "\t".join(("set", status.state, status.agent, status.repo, status.message))


def timeout_line(status: LastStatus) -> str:
    return "\t".join(("set", "ok", status.agent, status.repo, "No active Codex event"))


def should_timeout_running(status: LastStatus | None, now: float, running_timeout: float) -> bool:
    return (
        running_timeout > 0
        and status is not None
        and status.state == "running"
        and now - status.updated_at >= running_timeout
    )


def should_refresh_status(status: LastStatus | None, now: float, last_sent_at: float, refresh_interval: float) -> bool:
    return refresh_interval > 0 and status is not None and now - last_sent_at >= refresh_interval


def follow_queue(
    path: Path,
    *,
    port: str | None,
    baud: int,
    open_delay: float,
    poll_interval: float,
    running_timeout: float,
    refresh_interval: float,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    serial_port = resolve_serial_port(port)
    sender = PersistentSerialSender(serial_port, baud, open_delay)
    last_status: LastStatus | None = None
    last_sent_at = time.monotonic()

    try:
        with path.open("r", encoding="utf-8") as queue:
            queue.seek(0, 2)
            print(f"agent-lamp bridge watching {path}", flush=True)
            print(f"agent-lamp bridge sending to {serial_port}", flush=True)
            while True:
                line = queue.readline()
                if not line:
                    now = time.monotonic()
                    if should_timeout_running(last_status, now, running_timeout):
                        command = timeout_line(last_status)
                        try:
                            sender.send(command)
                            print(f"sent: {command}", flush=True)
                            last_status = parse_status_line(command, now)
                        except Exception as exc:
                            print(f"send failed: {exc}", flush=True)
                        last_sent_at = now
                    elif should_refresh_status(last_status, now, last_sent_at, refresh_interval):
                        command = status_line(last_status)
                        try:
                            sender.send(command)
                            print(f"resent: {command}", flush=True)
                        except Exception as exc:
                            print(f"resend failed: {exc}", flush=True)
                        last_sent_at = now
                    time.sleep(poll_interval)
                    continue

                command = line.rstrip("\n")
                if not command:
                    continue

                now = time.monotonic()
                parsed_status = parse_status_line(command, now)
                try:
                    sender.send(command)
                    print(f"sent: {command}", flush=True)
                    last_status = parsed_status or last_status
                except Exception as exc:
                    print(f"send failed: {exc}", flush=True)
                    last_status = parsed_status or last_status
                last_sent_at = now
    finally:
        sender.close()


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
    parser.add_argument(
        "--running-timeout",
        type=float,
        default=90.0,
        help="Seconds before a running state with no follow-up events is cleared to ok. Use 0 to disable.",
    )
    parser.add_argument(
        "--refresh-interval",
        type=float,
        default=5.0,
        help="Seconds between resending the last known state so USB reconnects recover from the device default screen.",
    )
    args = parser.parse_args()

    try:
        follow_queue(
            Path(args.queue).expanduser(),
            port=args.port,
            baud=args.baud,
            open_delay=args.open_delay,
            poll_interval=args.poll_interval,
            running_timeout=args.running_timeout,
            refresh_interval=args.refresh_interval,
        )
    except KeyboardInterrupt:
        print("\nagent-lamp bridge stopped", flush=True)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
