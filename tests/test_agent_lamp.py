from pathlib import Path
import os
import sys
import unittest
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "host"))

from agent_lamp import choose_transport, http_base_url, normalize_http_base_url, send_http  # noqa: E402


class HttpTransportConfigTests(unittest.TestCase):
    def test_normalizes_host_only_url_to_http(self) -> None:
        self.assertEqual(normalize_http_base_url("agent-lamp.local"), "http://agent-lamp.local")

    def test_keeps_explicit_http_url_without_trailing_slash(self) -> None:
        self.assertEqual(normalize_http_base_url("http://192.168.1.42/"), "http://192.168.1.42")

    def test_lamp_host_adds_port_when_needed(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(http_base_url(host="192.168.1.42", port=8080), "http://192.168.1.42:8080")

    def test_auto_transport_uses_http_when_lamp_url_is_configured(self) -> None:
        with mock.patch.dict(os.environ, {"AGENT_LAMP_URL": "http://agent-lamp.local"}, clear=True):
            self.assertEqual(choose_transport("auto"), "http")

    def test_auto_transport_uses_serial_without_wireless_target(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(choose_transport("auto"), "serial")

    def test_env_transport_is_used_when_argument_is_omitted(self) -> None:
        with mock.patch.dict(os.environ, {"AGENT_LAMP_TRANSPORT": "http"}, clear=True):
            self.assertEqual(choose_transport(None), "http")


class SendHttpTests(unittest.TestCase):
    def test_posts_protocol_line_to_set_endpoint(self) -> None:
        response = mock.MagicMock()
        response.__enter__.return_value.status = 200

        with mock.patch("agent_lamp.urlopen", return_value=response) as urlopen:
            send_http("http://agent-lamp.local", "set\trunning\tcodex\tAgent-Lamp\tWorking", 2.0)

        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://agent-lamp.local/set")
        self.assertEqual(request.data, b"set\trunning\tcodex\tAgent-Lamp\tWorking\n")
        self.assertEqual(request.get_header("Content-type"), "text/plain; charset=utf-8")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 2.0)


if __name__ == "__main__":
    unittest.main()
