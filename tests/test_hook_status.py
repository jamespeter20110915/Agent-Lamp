from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "host"))

from hook_status import (  # noqa: E402
    message_for_payload,
    protocol_line,
    read_previous_state,
    state_for_event,
    write_state_file,
)


class HookStatusTests(unittest.TestCase):
    def test_successful_post_tool_use_does_not_refresh_running_state(self) -> None:
        payload = {"tool_response": {"success": True, "exit_code": 0}}

        self.assertIsNone(state_for_event("codex", "PostToolUse", payload))
        self.assertIsNone(state_for_event("codex", "PostToolUse", payload, previous_state="running"))

    def test_successful_post_tool_use_clears_waiting_state(self) -> None:
        payload = {"tool_response": {"success": True, "exit_code": 0}}

        self.assertEqual(state_for_event("codex", "PostToolUse", payload, previous_state="waiting"), "running")

    def test_codex_permission_request_is_silent_by_default(self) -> None:
        self.assertIsNone(state_for_event("codex", "PermissionRequest", {"tool_name": "Bash"}))

    def test_codex_permission_request_can_be_shown_explicitly(self) -> None:
        self.assertEqual(
            state_for_event(
                "codex",
                "PermissionRequest",
                {"tool_name": "Bash"},
                show_permission_requests=True,
            ),
            "waiting",
        )

    def test_failed_post_tool_use_reports_error(self) -> None:
        payload = {"tool_response": {"success": False, "exit_code": 1}}

        self.assertEqual(state_for_event("codex", "PostToolUse", payload), "error")

    def test_stop_message_does_not_use_assistant_output_body(self) -> None:
        payload = {"last_assistant_message": "```python\nprint('long code')\n```"}

        self.assertEqual(message_for_payload(payload, "ok"), "Agent finished")

    def test_protocol_line_sanitizes_and_truncates_fields(self) -> None:
        line = protocol_line("codex", "Agent-Lamp", "ok", "line 1\n" + ("x" * 200))

        self.assertNotIn("\n", line)
        self.assertLessEqual(len(line.split("\t")[-1]), 120)

    def test_state_file_round_trip(self) -> None:
        path = Path("/private/tmp/agent-lamp-test-state.json")
        try:
            write_state_file(
                str(path),
                state="waiting",
                agent="codex",
                repo="Agent-Lamp",
                message="Waiting",
                event="PermissionRequest",
            )

            self.assertEqual(read_previous_state(str(path)), "waiting")
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
