from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "host"))

from hook_status import (  # noqa: E402
    event_log_record,
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

    def test_codex_permission_request_is_hidden_by_default(self) -> None:
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

    def test_user_prompt_submit_uses_generic_running_message(self) -> None:
        payload = {"hook_event_name": "UserPromptSubmit", "prompt": "请测试一下状态灯"}

        self.assertEqual(message_for_payload(payload, "running"), "Agent is working")

    def test_user_prompt_submit_redacts_sensitive_values(self) -> None:
        payload = {"hook_event_name": "Notification", "message": "SSID: Hmds16，密码：example-password"}

        self.assertEqual(message_for_payload(payload, "waiting"), "SSID: Hmds16，密码：[redacted]")

    def test_tool_use_running_message_can_use_tool_name(self) -> None:
        payload = {"hook_event_name": "PreToolUse", "prompt": "请测试一下状态灯", "tool_name": "Bash"}

        self.assertEqual(message_for_payload(payload, "running"), "Bash")

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
                payload={
                    "session_id": "session-1",
                    "turn_id": "turn-1",
                    "transcript_path": "/tmp/transcript.jsonl",
                },
            )

            self.assertEqual(read_previous_state(str(path)), "waiting")
            data = path.read_text(encoding="utf-8")
            self.assertIn('"turn_id": "turn-1"', data)
            self.assertIn('"transcript_path": "/tmp/transcript.jsonl"', data)
        finally:
            path.unlink(missing_ok=True)

    def test_event_log_record_keeps_stop_metadata_without_assistant_body(self) -> None:
        record = event_log_record(
            agent="codex",
            event="Stop",
            payload={
                "hook_event_name": "Stop",
                "last_assistant_message": "large final body",
                "session_id": "session-1",
                "turn_id": "turn-1",
                "stop_hook_active": False,
            },
            previous_state="running",
            state="ok",
        )

        self.assertEqual(record["event"], "Stop")
        self.assertEqual(record["previous_state"], "running")
        self.assertEqual(record["state"], "ok")
        self.assertEqual(record["session_id"], "session-1")
        self.assertIn("last_assistant_message", record["payload_keys"])
        self.assertNotIn("large final body", str(record))


if __name__ == "__main__":
    unittest.main()
