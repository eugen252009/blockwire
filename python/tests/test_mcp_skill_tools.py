"""Exercise actual MCP validation/dispatch, without native effects."""
import asyncio
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from blockwire.skills import default_registry
from blockwire.mcp_skill_tools import register_skill_tools


class NamedSkills(unittest.TestCase):
    def server(self):
        from mcp.server.fastmcp import FastMCP
        server = FastMCP('fixture')
        start = Mock(return_value={'id': 'fixture-job', 'status': 'running'})
        register_skill_tools(server, default_registry(), start, threading.RLock())
        return server, start

    def test_all_schemas_are_the_real_strict_skill_schema(self):
        server, start = self.server()
        for row in default_registry().describe():
            self.assertEqual(server._tool_manager.get_tool('skill_' + row['name']).parameters, row['parameters'])
        start.assert_not_called()

    def test_mcp_call_dispatches_named_goal_once_not_bcl(self):
        server, start = self.server()
        result = asyncio.run(server._tool_manager.call_tool('skill_gather_wood', {'count': 1}))
        self.assertEqual(result['id'], 'fixture-job')
        start.assert_called_once()
        self.assertEqual(start.call_args.args[0], 'gather_wood')
        self.assertEqual(start.call_args.args[1]['count'], 1)

    def test_schema_rejections_precede_dispatch(self):
        server, start = self.server()
        for params in [{'count': '1'}, {'count': True}, {'count': 999}, {'count': 1, 'unknown': 1},
                       {'count': 1, 'timeout_seconds': float('nan')}]:
            with self.subTest(params=params), self.assertRaises(Exception):
                asyncio.run(server._tool_manager.call_tool('skill_gather_wood', params))
        start.assert_not_called()

    def test_existing_policy_is_not_bypassed_by_named_alias(self):
        from blockwire.mcp_server import create_server
        with tempfile.TemporaryDirectory() as directory, patch('blockwire.mcp_server.Bridge.from_env'):
            server = create_server(bcl_state_directory=directory + '/bcl',
                feedback_directory=directory + '/feedback',
                feedback_identity={'agent_id': 'a', 'world_id': 'w', 'player_id': 'p'})
            with patch('blockwire.mcp_server.SkillManager.start') as start:
                with self.assertRaises(Exception):
                    asyncio.run(server._tool_manager.call_tool('skill_gather_wood', {'count': 1}))
                start.assert_not_called()
            self.assertIsNotNone(server._tool_manager.get_tool('cancel_skill'))
            self.assertIsNotNone(server._tool_manager.get_tool('skill_status'))


if __name__ == '__main__': unittest.main()
