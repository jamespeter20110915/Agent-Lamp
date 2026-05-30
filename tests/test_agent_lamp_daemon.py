from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "host"))

from agent_lamp_daemon import (  # noqa: E402
    PersistentSerialSender,
    abort_status_from_state,
    parse_status_line,
    should_refresh_status,
    should_timeout_running,
    status_line,
    transcript_has_turn_aborted,
    timeout_line,
)


class FakeConnection:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.closed = False

    def write(self, payload: bytes) -> None:
        self.writes.append(payload)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class FailingConnection(FakeConnection):
    def write(self, payload: bytes) -> None:
        raise OSError("serial write failed")


class PersistentSerialSenderTests(unittest.TestCase):
    def test_reuses_one_connection_for_multiple_status_lines(self) -> None:
        opened_ports: list[str] = []
        conn = FakeConnection()

        def opener(port: str) -> FakeConnection:
            opened_ports.append(port)
            return conn

        sender = PersistentSerialSender(
            "/dev/fake",
            115200,
            0,
            direct_opener=opener,
            port_resolver=lambda port: port or "/dev/fake",
            use_pyserial=False,
        )

        sender.send("set\trunning\tcodex\tAgent-Lamp\tWorking")
        sender.send("set\tok\tcodex\tAgent-Lamp\tDone\n")
        sender.close()

        self.assertEqual(opened_ports, ["/dev/fake"])
        self.assertEqual(
            conn.writes,
            [
                b"set\trunning\tcodex\tAgent-Lamp\tWorking\n",
                b"set\tok\tcodex\tAgent-Lamp\tDone\n",
            ],
        )
        self.assertTrue(conn.closed)

    def test_closes_failed_connection_so_next_send_can_reconnect(self) -> None:
        connections: list[FakeConnection] = [FailingConnection(), FakeConnection()]

        def opener(_port: str) -> FakeConnection:
            return connections.pop(0)

        sender = PersistentSerialSender(
            "/dev/fake",
            115200,
            0,
            direct_opener=opener,
            port_resolver=lambda port: port or "/dev/fake",
            use_pyserial=False,
        )

        with self.assertRaises(OSError):
            sender.send("set\trunning")

        sender.send("set\tok")

        self.assertEqual(connections, [])

    def test_resolves_port_each_time_it_reconnects(self) -> None:
        opened_ports: list[str] = []
        resolved_ports = iter(["/dev/old", "/dev/new"])
        connections: list[FakeConnection] = [FailingConnection(), FakeConnection()]

        def opener(port: str) -> FakeConnection:
            opened_ports.append(port)
            return connections.pop(0)

        sender = PersistentSerialSender(
            "/dev/configured",
            115200,
            0,
            direct_opener=opener,
            port_resolver=lambda _port: next(resolved_ports),
            use_pyserial=False,
        )

        with self.assertRaises(OSError):
            sender.send("set\trunning")

        sender.send("set\tok")

        self.assertEqual(opened_ports, ["/dev/old", "/dev/new"])


class StatusLineTests(unittest.TestCase):
    def test_parses_protocol_status_line(self) -> None:
        status = parse_status_line("set\trunning\tcodex\tAgent-Lamp\tBash", 12.5)

        self.assertIsNotNone(status)
        assert status is not None
        self.assertEqual(status.state, "running")
        self.assertEqual(status.agent, "codex")
        self.assertEqual(status.repo, "Agent-Lamp")
        self.assertEqual(status.message, "Bash")
        self.assertEqual(status.updated_at, 12.5)

    def test_rebuilds_status_line_for_refresh(self) -> None:
        status = parse_status_line("set\trunning\tcodex\tAgent-Lamp\tWorking", 12.5)

        self.assertIsNotNone(status)
        assert status is not None
        self.assertEqual(status_line(status), "set\trunning\tcodex\tAgent-Lamp\tWorking")

    def test_builds_ok_timeout_line_for_stale_running_state(self) -> None:
        status = parse_status_line("set\trunning\tcodex\tAgent-Lamp\tBash", 12.5)

        self.assertIsNotNone(status)
        assert status is not None
        self.assertEqual(timeout_line(status), "set\tok\tcodex\tAgent-Lamp\tNo active Codex event")

    def test_detects_turn_aborted_in_transcript(self) -> None:
        path = Path("/private/tmp/agent-lamp-test-transcript.jsonl")
        try:
            path.write_text(
                '{"type":"event_msg","payload":{"type":"turn_aborted","turn_id":"turn-1"}}\n',
                encoding="utf-8",
            )

            self.assertTrue(transcript_has_turn_aborted(str(path), "turn-1"))
            self.assertFalse(transcript_has_turn_aborted(str(path), "turn-2"))
        finally:
            path.unlink(missing_ok=True)

    def test_builds_interrupted_status_from_state_file(self) -> None:
        state_path = Path("/private/tmp/agent-lamp-test-state.json")
        transcript_path = Path("/private/tmp/agent-lamp-test-transcript.jsonl")
        try:
            transcript_path.write_text(
                '{"type":"event_msg","payload":{"type":"turn_aborted","turn_id":"turn-1"}}\n',
                encoding="utf-8",
            )
            state_path.write_text(
                (
                    '{"state":"running","agent":"codex","repo":"Agent-Lamp",'
                    '"message":"Agent is working","turn_id":"turn-1",'
                    f'"transcript_path":"{transcript_path}"}}'
                ),
                encoding="utf-8",
            )

            status = abort_status_from_state(str(state_path), now=42.0)

            self.assertIsNotNone(status)
            assert status is not None
            self.assertEqual(status.state, "ok")
            self.assertEqual(status.message, "Turn interrupted")
        finally:
            state_path.unlink(missing_ok=True)
            transcript_path.unlink(missing_ok=True)

    def test_running_timeout_only_applies_to_stale_running_state(self) -> None:
        running = parse_status_line("set\trunning\tcodex\tAgent-Lamp\tWorking", 10.0)
        ok = parse_status_line("set\tok\tcodex\tAgent-Lamp\tDone", 10.0)

        self.assertTrue(should_timeout_running(running, now=101.0, running_timeout=90.0))
        self.assertFalse(should_timeout_running(running, now=50.0, running_timeout=90.0))
        self.assertFalse(should_timeout_running(ok, now=101.0, running_timeout=90.0))
        self.assertFalse(should_timeout_running(running, now=101.0, running_timeout=0.0))

    def test_refresh_interval_resends_last_known_state(self) -> None:
        status = parse_status_line("set\trunning\tcodex\tAgent-Lamp\tWorking", 10.0)

        self.assertTrue(should_refresh_status(status, now=15.0, last_sent_at=10.0, refresh_interval=5.0))
        self.assertFalse(should_refresh_status(status, now=14.9, last_sent_at=10.0, refresh_interval=5.0))
        self.assertFalse(should_refresh_status(status, now=15.0, last_sent_at=10.0, refresh_interval=0.0))
        self.assertFalse(should_refresh_status(None, now=15.0, last_sent_at=10.0, refresh_interval=5.0))


if __name__ == "__main__":
    unittest.main()
