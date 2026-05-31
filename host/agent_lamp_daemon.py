#!/usr/bin/env python3
"""Forward queued hook status updates to the agent lamp."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
import json
from pathlib import Path
import time
from typing import TextIO

from agent_lamp import choose_transport, http_base_url, list_ports, pick_port, send_http

DEFAULT_STATE_FILE = "/private/tmp/agent-lamp-state.json"


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


class HttpSender:
    def __init__(
        self,
        lamp_url: str,
        timeout: float,
        *,
        http_sender: Callable[[str, str, float], None] = send_http,
    ) -> None:
        self.lamp_url = lamp_url
        self.timeout = timeout
        self.http_sender = http_sender

    def send(self, line: str) -> None:
        self.http_sender(self.lamp_url, line, self.timeout)

    def close(self) -> None:
        return


@dataclass
class LastStatus:
    state: str
    agent: str
    repo: str
    message: str
    updated_at: float
    turn_id: str = ""
    transcript_path: str = ""


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


def interrupted_line(status: LastStatus) -> str:
    return "\t".join(("set", "ok", status.agent, status.repo, "Turn interrupted"))


def should_timeout_running(status: LastStatus | None, now: float, running_timeout: float) -> bool:
    return (
        running_timeout > 0
        and status is not None
        and status.state == "running"
        and now - status.updated_at >= running_timeout
    )


def should_refresh_status(status: LastStatus | None, now: float, last_sent_at: float, refresh_interval: float) -> bool:
    return refresh_interval > 0 and status is not None and now - last_sent_at >= refresh_interval


def rewind_if_queue_was_truncated(queue: TextIO, path: Path) -> bool:
    try:
        if path.stat().st_size < queue.tell():
            queue.seek(0)
            return True
    except OSError:
        return False
    return False


def read_state_file(state_path: str, now: float) -> LastStatus | None:
    path = Path(state_path).expanduser()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    state = data.get("state")
    if state not in {"idle", "running", "waiting", "ok", "error"}:
        return None

    return LastStatus(
        state=state,
        agent=str(data.get("agent") or "agent"),
        repo=str(data.get("repo") or "workspace"),
        message=str(data.get("message") or ""),
        updated_at=now,
        turn_id=str(data.get("turn_id") or ""),
        transcript_path=str(data.get("transcript_path") or ""),
    )


def write_state_file(state_path: str, status: LastStatus, *, event: str) -> None:
    path = Path(state_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "state": status.state,
                "agent": status.agent,
                "repo": status.repo,
                "message": status.message,
                "event": event,
                "turn_id": status.turn_id,
                "transcript_path": status.transcript_path,
                "updated_at": time.time(),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def transcript_has_turn_aborted(transcript_path: str, turn_id: str) -> bool:
    if not transcript_path or not turn_id:
        return False

    path = Path(transcript_path).expanduser()
    try:
        with path.open("r", encoding="utf-8") as transcript:
            for line in transcript:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                payload = event.get("payload")
                if not isinstance(payload, dict):
                    continue
                if payload.get("type") == "turn_aborted" and payload.get("turn_id") == turn_id:
                    return True
    except Exception:
        return False

    return False


def transcript_has_task_complete(transcript_path: str, turn_id: str) -> bool:
    if not transcript_path or not turn_id:
        return False

    path = Path(transcript_path).expanduser()
    try:
        with path.open("r", encoding="utf-8") as transcript:
            for line in transcript:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                payload = event.get("payload")
                if not isinstance(payload, dict):
                    continue
                if payload.get("type") == "task_complete" and payload.get("turn_id") == turn_id:
                    return True
    except Exception:
        return False

    return False


def abort_status_from_state(state_path: str, now: float) -> LastStatus | None:
    status = read_state_file(state_path, now)
    if status is None or status.state != "running":
        return None
    if not transcript_has_turn_aborted(status.transcript_path, status.turn_id):
        return None
    return LastStatus(
        state="ok",
        agent=status.agent,
        repo=status.repo,
        message="Turn interrupted",
        updated_at=now,
        turn_id=status.turn_id,
        transcript_path=status.transcript_path,
    )


def completed_status_from_state(state_path: str, now: float) -> LastStatus | None:
    status = read_state_file(state_path, now)
    if status is None or status.state != "running":
        return None
    if not transcript_has_task_complete(status.transcript_path, status.turn_id):
        return None
    return LastStatus(
        state="ok",
        agent=status.agent,
        repo=status.repo,
        message="Agent finished",
        updated_at=now,
        turn_id=status.turn_id,
        transcript_path=status.transcript_path,
    )


def finished_status_from_state(state_path: str, now: float) -> LastStatus | None:
    aborted = abort_status_from_state(state_path, now)
    if aborted is not None:
        return aborted
    return completed_status_from_state(state_path, now)


def restore_status_from_state(state_path: str, now: float) -> LastStatus | None:
    finished = finished_status_from_state(state_path, now)
    if finished is not None:
        return finished
    return read_state_file(state_path, now)


def follow_queue(
    path: Path,
    *,
    state_path: str,
    transport: str | None,
    port: str | None,
    baud: int,
    open_delay: float,
    lamp_url: str | None,
    lamp_host: str | None,
    http_timeout: float,
    poll_interval: float,
    running_timeout: float,
    refresh_interval: float,
    abort_check_interval: float,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    resolved_transport = choose_transport(transport, lamp_url, lamp_host)
    if resolved_transport == "http":
        resolved_url = http_base_url(lamp_url, lamp_host)
        if not resolved_url:
            raise SystemExit("HTTP transport needs --lamp-url, --lamp-host, AGENT_LAMP_URL, or AGENT_LAMP_HOST.")
        sender = HttpSender(resolved_url, http_timeout)
        target = resolved_url
    else:
        target = resolve_serial_port(port)
        sender = PersistentSerialSender(target, baud, open_delay)
    now = time.monotonic()
    last_status = restore_status_from_state(state_path, now)
    last_sent_at = time.monotonic()
    last_abort_check_at = 0.0

    try:
        with path.open("r", encoding="utf-8") as queue:
            queue.seek(0, 2)
            print(f"agent-lamp bridge watching {path}", flush=True)
            print(f"agent-lamp bridge sending to {target}", flush=True)
            if last_status is not None:
                command = status_line(last_status)
                try:
                    sender.send(command)
                    print(f"restored: {command}", flush=True)
                except Exception as exc:
                    print(f"restore failed: {exc}", flush=True)
            while True:
                line = queue.readline()
                if not line:
                    if rewind_if_queue_was_truncated(queue, path):
                        continue
                    now = time.monotonic()
                    if (
                        abort_check_interval > 0
                        and last_status is not None
                        and last_status.state == "running"
                        and now - last_abort_check_at >= abort_check_interval
                    ):
                        last_abort_check_at = now
                        finished_status = finished_status_from_state(state_path, now)
                        if finished_status is not None:
                            command = status_line(finished_status)
                            try:
                                sender.send(command)
                                print(f"sent: {command}", flush=True)
                                write_state_file(state_path, finished_status, event="TurnFinished")
                                last_status = finished_status
                                last_sent_at = now
                            except Exception as exc:
                                print(f"send failed: {exc}", flush=True)
                    elif should_timeout_running(last_status, now, running_timeout):
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
    parser.add_argument(
        "--transport",
        choices=("auto", "serial", "http"),
        default=None,
        help="Transport to use. auto uses HTTP when a lamp URL/host is configured, otherwise serial.",
    )
    parser.add_argument("--port", help="Serial port, for example /dev/cu.usbmodem1101.")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--open-delay", type=float, default=0.15)
    parser.add_argument("--lamp-url", help="Wireless lamp base URL, for example http://agent-lamp.local.")
    parser.add_argument("--lamp-host", help="Wireless lamp host name or IP address.")
    parser.add_argument("--http-timeout", type=float, default=2.0)
    parser.add_argument("--poll-interval", type=float, default=0.1)
    parser.add_argument(
        "--running-timeout",
        type=float,
        default=0.0,
        help="Optional seconds before a running state with no follow-up events is cleared to ok. Default 0 disables it.",
    )
    parser.add_argument(
        "--refresh-interval",
        type=float,
        default=0.0,
        help="Seconds between resending the last known state. Default 0 disables periodic redraws.",
    )
    parser.add_argument(
        "--state-file",
        default=DEFAULT_STATE_FILE,
        help="State file written by hooks.",
    )
    parser.add_argument(
        "--abort-check-interval",
        type=float,
        default=0.5,
        help="Seconds between checks for Codex turn_aborted events in the transcript.",
    )
    args = parser.parse_args()

    try:
        follow_queue(
            Path(args.queue).expanduser(),
            state_path=args.state_file,
            transport=args.transport,
            port=args.port,
            baud=args.baud,
            open_delay=args.open_delay,
            lamp_url=args.lamp_url,
            lamp_host=args.lamp_host,
            http_timeout=args.http_timeout,
            poll_interval=args.poll_interval,
            running_timeout=args.running_timeout,
            refresh_interval=args.refresh_interval,
            abort_check_interval=args.abort_check_interval,
        )
    except KeyboardInterrupt:
        print("\nagent-lamp bridge stopped", flush=True)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
