"""MCP facade contracts, no native Minecraft acceptance."""
from pathlib import Path
import tempfile,time,unittest
from unittest.mock import patch
from blockwire import Player,CallableBackend
from test_agent import Native

class BCLMCPContracts(unittest.TestCase):
    def test_BM01_offline_compile_discovery_and_invalid_execute_never_observe_or_mutate(self):
        try:from blockwire.mcp_server import create_server
        except ImportError:self.skipTest('Optional MCP dependency absent')
        native=Native();player=Player(CallableBackend(native.call))
        with tempfile.TemporaryDirectory() as folder,patch('blockwire.mcp_server.Bridge.from_env'),patch('blockwire.mcp_server.Player',return_value=player):
            s=create_server(bcl_state_directory=folder)
            fn=lambda name:s._tool_manager.get_tool(name).fn
            self.assertTrue(fn('compile_bcl')('M0 X120 Z30')['ok'])
            self.assertTrue(fn('discover_bcl_commands')('navigation'))
            self.assertEqual(fn('describe_bcl_command')('M0')['skill'],'walk_to')
            result=fn('execute_bcl')('I0\nM0 Q1','a','w','player-a','actor-a',1,'test-session')
            self.assertFalse(result['ok']);self.assertEqual(native.calls,[])
            self.assertEqual(list(Path(folder).iterdir()),[])
    def test_BM02_existing_status_cancel_and_raw_control_gate_are_shared(self):
        try:from blockwire.mcp_server import create_server
        except ImportError:self.skipTest('Optional MCP dependency absent')
        native=Native();player=Player(CallableBackend(native.call))
        with tempfile.TemporaryDirectory() as folder,patch('blockwire.mcp_server.Bridge.from_env'),patch('blockwire.mcp_server.Player',return_value=player):
            s=create_server(bcl_state_directory=folder);fn=lambda name:s._tool_manager.get_tool(name).fn
            job=fn('execute_bcl')('I0','a','w','player-a','actor-a',1,'test-session')
            for _ in range(200):
                result=fn('skill_status')(job['id'])
                if result.get('phase')=='terminal' or result.get('status') in {'succeeded','blocked','failed','cancelled'}:break
                time.sleep(.01)
            self.assertEqual(result['status'],'succeeded',result)
            self.assertEqual(result['operations'][0]['output']['inventory'],{})
            self.assertFalse(fn('cancel_skill')(job['id'])['cancellation_requested'])
            # Explicit startup reservation covers the interval before AgentRuntime acquires native ownership.
            batches=fn('execute_bcl').__closure__
            manager=next(c.cell_contents for c in batches if hasattr(c.cell_contents,'active') and hasattr(c.cell_contents,'jobs'))
            manager.active='reserved'
            try:
                with self.assertRaises(RuntimeError):fn('look')(0.,0.)
            finally:manager.active=None
            self.assertFalse(any(q['op']=='look' for q in native.calls))

if __name__=='__main__':unittest.main()
