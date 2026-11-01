import io
import unittest
from unittest.mock import Mock, patch
from blockwire import CallableBackend, Player
from blockwire.cli import main


class CommandTests(unittest.TestCase):
    def test_exact_single_dispatch_and_optional_actor_guard(self):
        calls = []
        receipt = {"submitted": True, "text": "Submitted, not confirmed"}
        player = Player(CallableBackend(lambda q: calls.append(q) or receipt))
        self.assertIs(player.command("/time set day"), receipt)
        player.command("/x a/b; c", actor_session="a")
        self.assertEqual(calls, [
            {"op": "command", "command": "/time set day"},
            {"op": "command", "command": "/x a/b; c", "actor_session": "a"},
        ])

    def test_invalid_never_dispatches(self):
        backend = Mock()
        player = Player(backend)
        for command in [None, True, 1, [], "", "/", "help", "//help", "/ help",
                        "/\u00a0help", "/" + "a" * 256, "/x\nstop", "/x\rstop",
                        "/x\tstop", "/x\x00", "/x\x7f", "/x\x85", "/x§a",
                        "/x\u2028stop", "/x\u2029stop", "/x\ud800", "/x\udc00"]:
            with self.subTest(command=repr(command)), self.assertRaises(ValueError):
                player.command(command)
        backend.call.assert_not_called()

    def test_utf16_boundary_and_unicode(self):
        calls = []
        player = Player(CallableBackend(lambda q: calls.append(q) or {}))
        player.command("/" + "a" * 255)
        player.command("/x " + "😀" * 126 + "a")
        with self.assertRaises(ValueError):
            player.command("/x " + "😀" * 127)
        self.assertEqual(len(calls), 2)

    def test_no_retry_after_uncertain_failure(self):
        backend = Mock()
        backend.call.side_effect = TimeoutError("uncertain")
        with self.assertRaises(TimeoutError):
            Player(backend).command("/time set day")
        backend.call.assert_called_once_with("command", command="/time set day")

    def test_cli_quoted_command_and_json_receipt(self):
        with patch("blockwire.cli.Bridge.from_env") as connect, \
                patch("sys.argv", ["blockwire", "command", "/time set day", "--json"]), \
                patch("sys.stdout", new_callable=io.StringIO) as output:
            backend = connect.return_value.__enter__.return_value
            backend.call.return_value = {"submitted": True, "text": "Submitted"}
            main()
        backend.call.assert_called_once_with("command", command="/time set day")
        self.assertIn('"submitted": true', output.getvalue())

    def test_mcp_dispatch_and_ownership(self):
        try:
            from blockwire.mcp_server import create_server
            import mcp
        except ImportError:
            self.skipTest("MCP not installed")
        with patch("blockwire.mcp_server.Bridge.from_env"), \
                patch("blockwire.mcp_server.Player") as player_class, \
                patch("blockwire.mcp_server.SkillManager") as manager_class:
            server = create_server()
            tool = server._tool_manager.get_tool("run_command")
            player = player_class.return_value
            player.command.return_value = {"submitted": True}
            self.assertEqual(tool.fn("/help"), {"submitted": True})
            manager_class.return_value.ensure_idle.assert_called_once_with()
            player.command.assert_called_once_with("/help")
            player.command.reset_mock()
            manager_class.return_value.ensure_idle.side_effect = RuntimeError("actor busy")
            with self.assertRaisesRegex(RuntimeError, "actor busy"):
                tool.fn("/help")
            player.command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
