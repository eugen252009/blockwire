"""Trusted placement arrival predicates refine, never widen, ordinary walking."""
import threading
import unittest
from blockwire.skills.core import SkillContext, SkillStop
from blockwire.skills.walking import WalkTo, walk_to
from test_skills import FlatPlayer


class RecordedArrivalContracts(unittest.TestCase):
    def context(self,player,event=None):
        return SkillContext(player,event or threading.Event(),30.,lambda _:None,player.clock,player.sleep)

    def test_RA01_placement_predicate_is_additional_to_the_unchanged_radius(self):
        goal=WalkTo(x=.6,y=64.,z=.5,movement='sneak',arrival_radius=.08)
        normal=FlatPlayer();plain=walk_to(self.context(normal),goal)
        constrained=FlatPlayer();observed=[]
        def permitted(state):
            self.assertLessEqual(abs(state['position'][0]-.6),.08)
            observed.append(state['position'][0])
            return state['position'][0]>=.58
        result=walk_to(self.context(constrained),goal,arrival_check=permitted)
        self.assertEqual(result.status,'succeeded',result)
        self.assertEqual(plain.status,'succeeded',plain)
        self.assertLess(normal.position[0],.58)
        self.assertGreaterEqual(constrained.position[0],.58)
        self.assertLessEqual(abs(constrained.position[0]-.6),.08)
        self.assertTrue(any(p<.58 for p in observed))
        self.assertEqual(sum(c[0]=='drive' and 'forward' in c[1] for c in normal.calls),1)
        self.assertEqual(sum(c[0]=='drive' and 'forward' in c[1] for c in constrained.calls),2)

    def test_RA02_predicate_cancel_and_deadline_precede_any_native_input(self):
        for status in ('cancelled','timed_out'):
            with self.subTest(status=status):
                player=FlatPlayer();event=threading.Event();context=self.context(player,event)
                def stop(state):
                    if status=='cancelled':event.set()
                    else:player.now=31.
                    return True
                with self.assertRaises(SkillStop) as raised:
                    walk_to(context,WalkTo(x=.55,y=64.,z=.5,arrival_radius=.08),arrival_check=stop)
                self.assertEqual(raised.exception.status,status)
                self.assertFalse(any(c[0]=='drive' for c in player.calls))

    def test_RA03_trusted_predicate_must_be_callable_and_return_strict_bool(self):
        player=FlatPlayer()
        with self.assertRaises(ValueError):
            walk_to(self.context(player),WalkTo(x=.55,y=64.,z=.5),arrival_check='not executable data')
        for value in (None,1,'yes'):
            player=FlatPlayer()
            with self.assertRaises(ValueError):
                walk_to(self.context(player),WalkTo(x=.55,y=64.,z=.5),arrival_check=lambda state:value)
            self.assertFalse(any(c[0]=='drive' for c in player.calls))

    def test_RA04_interaction_predicate_follows_native_settling_without_more_direction(self):
        player=FlatPlayer();samples=iter((.02,.005,.004,0.,0.));base=player.navigation
        def navigation():
            state=base();state['horizontal_speed']=next(samples,0.);return state
        player.navigation=navigation;seen=[]
        def permitted(state):
            self.assertLessEqual(state['horizontal_speed'],.004)
            seen.append(state['position'][:]);return True
        result=walk_to(self.context(player),WalkTo(x=.55,y=64.,z=.5,arrival_radius=.08),arrival_check=permitted)
        self.assertEqual(result.status,'succeeded');self.assertTrue(seen)
        self.assertFalse(any(c[0]=='drive' for c in player.calls))


if __name__=='__main__':unittest.main()
