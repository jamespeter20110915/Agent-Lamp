from pathlib import Path
import json
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOOK_COMMAND = "$CLAUDE_PROJECT_DIR/hooks/claude/status-hook.sh"


class ClaudeCodeConfigTests(unittest.TestCase):
    def test_project_settings_install_agent_lamp_hooks(self) -> None:
        settings = json.loads((ROOT / ".claude/settings.json").read_text(encoding="utf-8"))
        hooks = settings["hooks"]

        for event in (
            "SessionStart",
            "UserPromptSubmit",
            "PreToolUse",
            "PostToolUse",
            "Notification",
            "Stop",
            "SubagentStop",
        ):
            self.assertIn(event, hooks)
            self.assertEqual(hooks[event][0]["hooks"][0]["command"], HOOK_COMMAND)

        self.assertEqual(hooks["PreToolUse"][0]["matcher"], "*")
        self.assertEqual(hooks["PostToolUse"][0]["matcher"], "*")

    def test_claude_example_matches_project_settings(self) -> None:
        project_settings = json.loads((ROOT / ".claude/settings.json").read_text(encoding="utf-8"))
        example_settings = json.loads((ROOT / "hooks/claude/settings.example.json").read_text(encoding="utf-8"))

        self.assertEqual(example_settings, project_settings)

    def test_claude_hook_defaults_to_queue_bridge(self) -> None:
        hook_script = (ROOT / "hooks/claude/status-hook.sh").read_text(encoding="utf-8")

        self.assertIn('AGENT_LAMP_QUEUE="${AGENT_LAMP_QUEUE:-/private/tmp/agent-lamp-queue.tsv}"', hook_script)


if __name__ == "__main__":
    unittest.main()
