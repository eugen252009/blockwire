import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from blockwire import Bridge, BridgeError, CallableBackend, Player


class ClientContractTests(unittest.TestCase):
    def test_endpoint_shape(self):
        for url in ["http://example.com/v1", "wss:///v1", "ws://127.0.0.1/v1",
                    "wss://127.0.0.1/v2", "wss://x@127.0.0.1/v1", "wss://127.0.0.1/v1?token=secret"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                Bridge("a" * 64, url)

    def test_explicit_remote_and_tls_endpoints(self):
        for url in ["wss://192.0.2.1:8877/v1", "wss://bridge.example/v1", "wss://[::1]:8877/v1"]:
            self.assertEqual(Bridge("Custom_key-" * 4, url).url, url)

    def test_missing_certificate_fails_before_network(self):
        bridge = Bridge("a" * 64)
        with patch("websockets.sync.client.connect") as connect:
            with self.assertRaisesRegex(BridgeError, "trusted instance certificate"):
                bridge.connect()
            connect.assert_not_called()

    def test_certificate_override_for_remote_client(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "token"
            path.write_text("a" * 64)
            path.chmod(0o600)
            with patch.dict(os.environ, {"BLOCKWIRE_CERT_FILE": "/trusted/remote.pem"}):
                self.assertEqual(Bridge.from_token_file(path).certificate, Path("/trusted/remote.pem"))

    def test_token_format(self):
        for token in ["", "secret", "a" * 31, "a" * 257, "a" * 32 + " ", "ü" * 64]:
            with self.subTest(token=token), self.assertRaises(ValueError):
                Bridge(token)

    def test_private_token_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "token"
            path.write_text("a" * 64 + "\n")
            path.chmod(0o600)
            self.assertEqual(Bridge.from_token_file(path).url, "wss://127.0.0.1:8765/v1")
            if os.name == "posix":
                path.chmod(0o644)
                with self.assertRaises(ValueError):
                    Bridge.from_token_file(path)

    def test_config_file_and_wildcard_client_address(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            path.write_text('{"enabled":true,"server_ip":"0.0.0.0","port":8877,"mcp_api_key":"' + "b"*40 + '"}')
            path.chmod(0o600)
            with patch.dict(os.environ, {}, clear=True):
                bridge = Bridge.from_config(path)
                self.assertEqual(bridge.url, "wss://127.0.0.1:8877/v1")
                self.assertEqual(bridge.certificate, path.parent / "tls/certificate.pem")
                with patch.dict(os.environ, {"BLOCKWIRE_CONFIG": str(path)}):
                    self.assertEqual(Bridge.from_env().url, bridge.url)

    def test_menu_adapter_preserves_fresh_screen_id(self):
        calls = []
        player = Player(CallableBackend(lambda q: calls.append(q) or {}))
        player.click_widget(7, 3)
        player.menu_text(8, "Name", replace=True)
        player.menu_key(9, "tab", ["shift"])
        self.assertEqual(calls, [
            {"op": "menu_click", "screen_id": 7, "widget_id": 3, "button": 0},
            {"op": "menu_text", "screen_id": 8, "text": "Name", "replace": True},
            {"op": "menu_key", "screen_id": 9, "key": "tab", "modifiers": ["shift"]},
        ])

    def test_direct_python_route_preserves_actor_arguments(self):
        calls = []
        player = Player(CallableBackend(lambda q: calls.append(q) or {"text": "accepted"}))
        player.hotbar(2)
        player.click_slot(7, menu_id=1, state_id=9, button=1)
        self.assertEqual(calls, [
            {"op": "hotbar", "slot": 2},
            {"op": "click_slot", "slot": 7, "button": 1, "mode": "pickup", "menu_id": 1, "state_id": 9},
        ])

    def test_drive_boundaries_and_no_dispatch_on_invalid_duration(self):
        calls = []
        player = Player(CallableBackend(lambda q: calls.append(q) or {}))
        for ticks in [0, 101, -1, 2.5, True]:
            with self.subTest(ticks=ticks), self.assertRaises(ValueError):
                player.drive(["forward"], ticks, wait=False)
        self.assertEqual(calls, [])
        for ticks in [1, 100]:
            player.drive(["forward"], ticks, wait=False)
        self.assertEqual([q["ticks"] for q in calls], [1, 100])

    def test_look_at_uses_native_eye_height(self):
        calls = []
        def dispatch(q):
            calls.append(q)
            return {"in_world": True, "eye_position": [0, 2, 0]} if q["op"] == "observe" else {}
        player = Player(CallableBackend(dispatch))
        player.look_at(1, 2, 0)
        self.assertAlmostEqual(calls[-1]["yaw"], -90)
        self.assertAlmostEqual(calls[-1]["pitch"], 0)
        player.look_at(0, 3, 0)
        self.assertAlmostEqual(calls[-1]["pitch"], -90)
        before = len(calls)
        with self.assertRaises(ValueError):
            player.look_at(math.nan, 0, 0)
        self.assertEqual(len(calls), before)

    def test_request_id_and_server_error(self):
        bridge = Bridge("a" * 64)
        class Socket:
            def send(self, payload): self.payload = payload
            def recv(self, **kwargs): return '{"id":1,"ok":false,"error":"stale_menu"}'
            def close(self): pass
        socket = Socket()
        bridge._socket = socket
        with self.assertRaisesRegex(BridgeError, "stale_menu"):
            bridge.call("inventory")
        self.assertIn('"op": "inventory"', socket.payload)

    def test_nonfinite_and_oversize_never_sent(self):
        bridge = Bridge("a" * 64)
        with patch.object(bridge, "connect") as connect:
            with self.assertRaises(ValueError):
                bridge.call("look", yaw=math.inf, pitch=0)
            with self.assertRaises(ValueError):
                bridge.call("unknown", payload="x" * 9000)
            connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
