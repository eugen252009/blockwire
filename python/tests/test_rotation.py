"""Time-based rotation contracts; graphical timing acceptance lives in tests/rotation."""
import math
import threading
import unittest
from unittest.mock import Mock
from blockwire import CallableBackend,Player
from blockwire.skills.core import SkillContext
from blockwire.skills.motion import rotate_view_timed,_yaw_delta
from test_approach import ApproachPlayer


class RotationContracts(unittest.TestCase):
    def context(self,player):return SkillContext(player,threading.Event(),player.now+5.,lambda _:None,player.clock,player.sleep)

    def test_RT01_python_look_preserves_legacy_and_adds_strict_timed_envelope(self):
        calls=[];player=Player(CallableBackend(lambda q:calls.append(q) or {'status':'active'}))
        player.look(10.,-5.,actor_session='a')
        player.look(90.,0.,actor_session='a',duration_ms=200,rotation_profile='smoothstep')
        self.assertEqual(calls,[{'op':'look','yaw':10.,'pitch':-5.,'actor_session':'a'},
          {'op':'look','yaw':90.,'pitch':0.,'actor_session':'a','duration_ms':200,'rotation_profile':'smoothstep'}])
        backend=Mock();player=Player(backend)
        for kwargs in ({'duration_ms':True},{'duration_ms':0},{'duration_ms':5001},{'duration_ms':1.5},
                       {'rotation_profile':'linear'},{'duration_ms':200,'rotation_profile':'spring'}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):player.look(0.,0.,**kwargs)
        backend.call.assert_not_called()

    def test_RT02_shortest_wrap_is_scheduled_without_snap(self):
        player=ApproachPlayer([]);player.yaw=179.;context=self.context(player)
        self.assertTrue(rotate_view_timed(context,(179.,0.),(-179.,0.),player.session))
        request=player.rotation_request_trace[-1]
        self.assertEqual((request['yaw'],request['duration_ms'],request['rotation_profile']),(-179.,200,'smoothstep'))
        self.assertGreater(player.yaw,179.);self.assertLess(player.yaw,180.)
        player.sleep(.15)
        self.assertLess(abs(_yaw_delta(-179.,player.yaw)),1e-6)

    def test_RT03_irregular_intervals_use_elapsed_time_not_update_count(self):
        player=ApproachPlayer([]);player.yaw=0.
        player.look(90.,0.,actor_session=player.session,duration_ms=200,rotation_profile='linear')
        player.sleep(.03);self.assertAlmostEqual(player.yaw,13.5,places=6)
        player.sleep(.07);self.assertAlmostEqual(player.yaw,45.,places=6)
        player.sleep(.11);self.assertAlmostEqual(player.yaw,90.,places=6)
        self.assertIsNone(player.rotation)

    def test_RT04_new_target_starts_from_actual_view_and_cancel_stops_it(self):
        player=ApproachPlayer([]);player.yaw=0.
        player.look(90.,0.,actor_session=player.session,duration_ms=200,rotation_profile='smoothstep')
        player.sleep(.08);actual=player.yaw;self.assertGreater(actual,0.);self.assertLess(actual,90.)
        player.look(150.,0.,actor_session=player.session,duration_ms=200,rotation_profile='smoothstep')
        self.assertAlmostEqual(player.rotation[1],actual)
        player.sleep(.05);self.assertGreater(player.yaw,actual)
        stopped=player.yaw;player.stop();player.sleep(.5)
        self.assertAlmostEqual(player.yaw,stopped);self.assertIsNone(player.rotation)

    def test_RT05_same_target_is_idempotent_and_pitch_is_simultaneous(self):
        player=ApproachPlayer([]);player.yaw=0.;player.pitch=20.
        player.look(90.,-30.,actor_session=player.session,duration_ms=200,rotation_profile='smoothstep')
        plan=player.rotation;player.sleep(.05)
        player.look(90.,-30.,actor_session=player.session,duration_ms=200,rotation_profile='smoothstep')
        self.assertEqual(player.rotation[0],plan[0])
        self.assertGreater(player.yaw,0.);self.assertLess(player.pitch,20.)
        player.sleep(.15);self.assertAlmostEqual(player.yaw,90.);self.assertAlmostEqual(player.pitch,-30.)

    def test_RT06_tolerance_avoids_micro_rotation_and_deadline_precedes_request(self):
        player=ApproachPlayer([]);player.yaw=10.;player.pitch=2.;context=self.context(player)
        self.assertFalse(rotate_view_timed(context,(10.,2.),(10.1,2.1),player.session))
        self.assertFalse(player.rotation_request_trace)
        context.deadline=player.now
        with self.assertRaises(Exception):rotate_view_timed(context,(10.,2.),(90.,0.),player.session)
        self.assertFalse(player.rotation_request_trace)


if __name__=='__main__':unittest.main()
