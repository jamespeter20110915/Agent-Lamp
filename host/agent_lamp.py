#!/usr/bin/env python3
"""Send status updates to the M5Stack Tab5 agent lamp."""

from __future__ import annotations

import argparse
import glob
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


VALID_STATES = {"idle", "running", "waiting", "ok", "error"}
ALIASES = {
    "green": "ok",
    "yellow": "running",
    "amber": "running",
    "busy": "running",
    "wait": "waiting",
    "approval": "waiting",
    "red": "error",
    "fail": "error",
    "failed": "error",
    "done": "ok",
    "success": "ok",
}

PORT_PATTERNS = (
    "/dev/cu.usbmodem*",
    "/dev/cu.usbserial*",
    "/dev/cu.wchusbserial*",
    "/dev/cu.SLAB_USBtoUART*",
)
TRANSPORTS = {"auto", "serial", "http"}
DEFAULT_HTTP_PORT = 80


def normalize_state(value: str) -> str:
    state = value.strip().lower()
    state = ALIASES.get(state, state)
    if state not in VALID_STATES:
        raise SystemExit(f"Unknown state {value!r}. Use one of: {', '.join(sorted(VALID_STATES))}")
    return state


def sanitize_field(value: str | None, max_len: int = 180) -> str:
    if not value:
        return ""
    cleaned = value.replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()
    return cleaned[:max_len]


def default_repo() -> str:
    return Path.cwd().name or "workspace"


def list_ports() -> list[str]:
    ports: list[str] = []
    for pattern in PORT_PATTERNS:
        ports.extend(glob.glob(pattern))
    return sorted(set(ports))


def normalize_http_base_url(value: str) -> str:
    candidate = value.strip().rstrip("/")
    if not candidate:
        raise SystemExit("Lamp URL is empty.")
    if "://" not in candidate:
        candidate = f"http://{candidate}"

    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SystemExit(f"Invalid lamp URL {value!r}. Use a value like http://agent-lamp.local.")
    return candidate


def http_base_url(explicit_url: str | None = None, host: str | None = None, port: int = DEFAULT_HTTP_PORT) -> str | None:
    raw_url = explicit_url or os.environ.get("AGENT_LAMP_URL")
    if raw_url:
        return normalize_http_base_url(raw_url)

    raw_host = host or os.environ.get("AGENT_LAMP_HOST")
    if not raw_host:
        return None
    if "://" in raw_host:
        return normalize_http_base_url(raw_host)

    if ":" in raw_host or port == 80:
        return normalize_http_base_url(raw_host)
    return normalize_http_base_url(f"{raw_host}:{port}")


def choose_transport(requested: str | None, lamp_url: str | None = None, lamp_host: str | None = None) -> str:
    transport = (requested or os.environ.get("AGENT_LAMP_TRANSPORT") or "auto").strip().lower()
    if transport not in TRANSPORTS:
        raise SystemExit(f"Unknown transport {transport!r}. Use one of: {', '.join(sorted(TRANSPORTS))}")
    if transport == "auto":
        return "http" if http_base_url(lamp_url, lamp_host) else "serial"
    return transport


def pick_port(explicit_port: str | None) -> str:
    if explicit_port:
        return explicit_port

    env_port = os.environ.get("AGENT_LAMP_PORT")
    if env_port:
        return env_port

    ports = list_ports()
    if not ports:
        raise SystemExit(
            "No likely serial port found. Connect Tab5, then set AGENT_LAMP_PORT=/dev/cu.usbmodemXXXX."
        )
    if len(ports) > 1:
        joined = "\n  ".join(ports)
        raise SystemExit(
            "Multiple likely serial ports found. Pick one with --port or AGENT_LAMP_PORT:\n  "
            + joined
        )
    return ports[0]


def send_http(base_url: str, line: str, timeout: float) -> None:
    payload = (line.rstrip("\n") + "\n").encode("utf-8")
    request = Request(
        base_url.rstrip("/") + "/set",
        data=payload,
        headers={"Content-Type": "text/plain; charset=utf-8"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            if response.status >= 400:
                raise SystemExit(f"Lamp returned HTTP {response.status}.")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace").strip()
        suffix = f": {body}" if body else ""
        raise SystemExit(f"Lamp returned HTTP {exc.code}{suffix}") from exc
    except URLError as exc:
        raise SystemExit(f"Could not reach lamp at {base_url}: {exc.reason}") from exc
    except OSError as exc:
        raise SystemExit(f"Could not reach lamp at {base_url}: {exc}") from exc


def send_with_pyserial(port: str, baud: int, payload: bytes, open_delay: float) -> bool:
    try:
        import serial  # type: ignore
    except ImportError:
        return False

    with serial.Serial(port=port, baudrate=baud, timeout=1, write_timeout=1) as conn:
        time.sleep(open_delay)
        conn.write(payload)
        conn.flush()
    return True


def send_direct(port: str, payload: bytes, open_delay: float) -> None:
    time.sleep(open_delay)
    with open(port, "wb", buffering=0) as conn:
        conn.write(payload)


def send_serial(port: str, baud: int, line: str, open_delay: float) -> None:
    payload = (line.rstrip("\n") + "\n").encode("utf-8")
    if send_with_pyserial(port, baud, payload, open_delay):
        return
    send_direct(port, payload, open_delay)


def send_status(args: argparse.Namespace, line: str) -> None:
    transport = choose_transport(args.transport, args.lamp_url, args.lamp_host)
    if transport == "http":
        base_url = http_base_url(args.lamp_url, args.lamp_host)
        if not base_url:
            raise SystemExit("HTTP transport needs --lamp-url, --lamp-host, AGENT_LAMP_URL, or AGENT_LAMP_HOST.")
        send_http(base_url, line, args.http_timeout)
        return

    port = pick_port(args.port)
    send_serial(port, args.baud, line, args.open_delay)


def make_set_line(args: argparse.Namespace) -> str:
    state = normalize_state(args.state)
    agent = sanitize_field(args.agent or os.environ.get("AGENT_LAMP_AGENT") or "agent")
    repo = sanitize_field(args.repo or os.environ.get("AGENT_LAMP_REPO") or default_repo())
    message = sanitize_field(args.message or "")
    return "\t".join(("set", state, agent, repo, message))


def add_common_transport_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--transport",
        choices=sorted(TRANSPORTS),
        default=None,
        help="Transport to use. auto uses HTTP when a lamp URL/host is configured, otherwise serial.",
    )
    parser.add_argument("--port", help="Serial port, for example /dev/cu.usbmodem1101.")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--open-delay", type=float, default=0.15)
    parser.add_argument("--lamp-url", help="Wireless lamp base URL, for example http://agent-lamp.local.")
    parser.add_argument("--lamp-host", help="Wireless lamp host name or IP address.")
    parser.add_argument("--http-timeout", type=float, default=2.0)
    parser.add_argument("--dry-run", action="store_true", help="Print the protocol line without sending it.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-lamp")
    subparsers = parser.add_subparsers(dest="command", required=True)

    set_parser = subparsers.add_parser("set", help="Set lamp state.")
    set_parser.add_argument("state", help="idle, running, waiting, ok, error, or color aliases.")
    set_parser.add_argument("--agent", help="Agent name shown on the Tab5.")
    set_parser.add_argument("--repo", help="Repository or workspace name shown on the Tab5.")
    set_parser.add_argument("--message", "-m", help="Short status message.")
    add_common_transport_args(set_parser)

    ping_parser = subparsers.add_parser("ping", help="Send ping to the lamp.")
    add_common_transport_args(ping_parser)

    subparsers.add_parser("ports", help="List likely USB serial ports.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "ports":
        for port in list_ports():
            print(port)
        return 0

    line = "ping" if args.command == "ping" else make_set_line(args)

    if args.dry_run:
        print(line)
        return 0

    send_status(args, line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
