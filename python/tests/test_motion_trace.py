"""Native motion telemetry request contracts; graphical measurements live in the benchmark."""
import unittest
from unittest.mock import Mock
from blockwire import CallableBackend,Player


class MotionTraceContracts(unittest.TestCase):
    def test_MT01_bounded_read_and_actor_fenced_reset(self):
        calls=[];reply={'profile':'native_player_motion_ticks_v1','samples':[]}
        player=Player(CallableBackend(lambda q:calls.append(q) or reply))
        self.assertIs(player.motion_trace(limit=17),reply)
        player.motion_trace(reset=True,actor_session='actor-a')
        self.assertEqual(calls,[{'op':'motion_trace','limit':17},
                                {'op':'motion_trace','limit':4096,'reset':True,'actor_session':'actor-a'}])

    def test_MT02_invalid_limit_never_dispatches(self):
        backend=Mock();player=Player(backend)
        for value in (None,True,0,4097,1.5,'1'):
            with self.subTest(value=value),self.assertRaises(ValueError):player.motion_trace(limit=value)
        backend.call.assert_not_called()


if __name__=='__main__':unittest.main()
