"""Clean supported inventory transition only; no blanket GUI dismissal."""
import threading
import unittest
from blockwire import Player,CallableBackend
from blockwire.skills.crafting import ensure_gameplay
from blockwire.skills.core import SkillStop,SkillContext
from test_crafting import CraftNative


class GameplayUIContracts(unittest.TestCase):
    def context(self,native,screen_type='CraftingScreen',replace=False):
        def call(q):
            op=q['op'];params={k:v for k,v in q.items() if k!='op'}
            if op=='menu':
                if replace:native.session='replacement'
                return {'type':screen_type}
            value=native.call(op,**params)
            if op=='observe':value['screen']='Crafting' if native.open else None
            return value
        return SkillContext(Player(CallableBackend(call)),threading.Event(),30.,lambda _:None,lambda:0.,lambda _:None)
    def test_UI01_clean_supported_inventory_closed_with_actor_fence(self):
        n=CraftNative(width=3);ensure_gameplay(self.context(n))
        self.assertFalse(n.open)
        self.assertEqual(next(q for op,q in n.calls if op=='close_screen')['actor_session'],n.session)
    def test_UI02_partial_grid_or_cursor_never_closed(self):
        for grid in (True,False):
            n=CraftNative(width=3)
            if grid:n.grid={1:('minecraft:oak_planks',1)}
            else:n.carried=('minecraft:oak_planks',1)
            with self.assertRaises(SkillStop):ensure_gameplay(self.context(n))
            self.assertTrue(n.open)
            self.assertFalse(any(op=='close_screen' for op,_ in n.calls))
    def test_UI04_actor_replacement_before_inventory_binding_never_closes_new_gui(self):
        n=CraftNative(width=3)
        with self.assertRaises(SkillStop) as error:ensure_gameplay(self.context(n,replace=True))
        self.assertEqual(error.exception.reason,'actor_session_changed')
        self.assertTrue(n.open)
        self.assertFalse(any(op=='close_screen' for op,_ in n.calls))

    def test_UI03_pause_chat_and_unknown_screens_never_dismissed(self):
        for kind in ('PauseScreen','ChatScreen','UnknownScreen'):
            n=CraftNative(width=3);ensure_gameplay(self.context(n,kind))
            self.assertTrue(n.open)
            self.assertFalse(any(op=='close_screen' for op,_ in n.calls))


if __name__=='__main__':unittest.main()
