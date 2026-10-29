"""FC01–FC17: deterministic combat contracts; NOT real Minecraft combat acceptance."""
import math
import threading
import time
import unittest
from unittest.mock import patch
from pydantic import ValidationError
from blockwire import BridgeError, CallableBackend, Player
from blockwire.skills import default_registry, run_skill
from test_autopilot import AutoPlayer, threat


class Fighter(AutoPlayer):
    def __init__(self):
        super().__init__()
        self.weapon = {"item": "minecraft:iron_sword", "count": 1, "damage": 0, "max_damage": 250, "inventory_index": 0}
        self.hit_override = False
        self.on_attack = lambda: None
        self.on_inventory = lambda: None

    def inventory(self):
        self.on_inventory()
        return {"items": [] if self.weapon is None else [self.weapon.copy()], "selected_hotbar": 0,
                "carried": {"empty": True}, "container_open": False}

    def observe(self):
        s = super().observe()
        s["health"] = self.health
        if self.hit_override is not False:
            s["target"] = self.hit_override
            return s
        # Independent ray/AABB hit fixture; renderer target is NOT copied from the planner's choice.
        eye = s["eye_position"];yaw,pitch=math.radians(self.yaw),math.radians(self.pitch)
        ray = [-math.sin(yaw)*math.cos(pitch), -math.sin(pitch), math.cos(yaw)*math.cos(pitch)]
        hits = []
        for mob in self.threats:
            if not mob["visible"]:continue
            pos=mob["position"];lo,hi=0.,3.
            for axis in range(3):
                a=pos[axis]-(.3 if axis!=1 else 0);b=pos[axis]+(.3 if axis!=1 else 1.8)
                if abs(ray[axis])<1e-10:
                    if not a<=eye[axis]<=b:hi=-1.
                else:
                    t1,t2=(a-eye[axis])/ray[axis],(b-eye[axis])/ray[axis]
                    lo,hi=max(lo,min(t1,t2)),min(hi,max(t1,t2))
            if lo<=hi:hits.append((lo,mob["entity_id"]))
        s.pop("target",None)
        if hits:s["target"]={"kind":"entity","id":min(hits)[1]}
        return s

    def action(self, name, *, actor_session, target_entity_id):
        if actor_session!=self.session:raise BridgeError("actor_session_changed")
        mob=next((t for t in self.threats if t["entity_id"]==target_entity_id),None)
        if mob is None or not mob["visible"] or math.dist(self.position,mob["position"])>3:
            raise BridgeError("target_entity_changed")
        super().action(name,actor_session=actor_session,target_entity_id=target_entity_id)
        self.on_attack()


class FightContracts(unittest.TestCase):
    def execute(self, p, **args):
        return run_skill(default_registry(),p,"fight",{"duration_seconds":2.,"timeout_seconds":3.,**args},clock=p.clock,sleeper=p.sleep)

    def attacks(self,p):return [c for c in p.calls if c[0]=="action"]

    def test_FC01_whitelisted_types_guarded_attack_no_inferred_kill(self):
        for kind in ["zombie","skeleton","spider","creeper"]:
            with self.subTest(mob=kind):
                p=Fighter();p.threats=[threat("minecraft:"+kind)]
                p.on_attack=lambda: p.threats.clear()
                r=self.execute(p,reactions={"creeper":"fight"})
                self.assertEqual(r.reason,"no_selected_enemies_observed")
                self.assertEqual(r.status,"succeeded")
                self.assertEqual(len(self.attacks(p)),1)
                self.assertEqual(self.attacks(p)[0][1:3],("attack",1))
                self.assertIsNone(r.details["kills_confirmed"])
                self.assertEqual(r.details["attacks_submitted"],1)
                self.assertEqual(r.cleanup,"released")

    def test_FC02_evade_overrides_fight_and_ignore_never_attacks(self):
        p=Fighter();p.threats=[threat("minecraft:zombie"),threat(position=(3.5,64.,.5),entity_id=2)]
        order=[];p.on_drive=lambda:p.threats.pop() if len(p.threats)==2 else None
        p.on_attack=lambda:p.threats.clear()
        r=run_skill(default_registry(),p,"fight",{},clock=p.clock,sleeper=p.sleep,publish=lambda s:order.append(s["behavior"]))
        self.assertEqual(r.status,"succeeded");self.assertEqual(order[0],"evade")
        self.assertTrue(p.trace);self.assertLess(p.trace[0][0],1)
        self.assertTrue(all(c[2]==1 for c in self.attacks(p)))
        for key,kind in [("zombies","zombie"),("skeletons","skeleton"),("spiders","spider"),("creeper","creeper")]:
            p=Fighter();p.threats=[threat("minecraft:"+kind)]
            r=self.execute(p,reactions={key:"ignore"})
            self.assertEqual(r.status,"succeeded");self.assertFalse(self.attacks(p));self.assertFalse(p.trace)
            p=Fighter();p.weapon=None;p.threats=[threat("minecraft:"+kind)];p.on_drive=lambda:p.threats.clear()
            r=self.execute(p,reactions={key:"evade"})
            self.assertEqual(r.status,"succeeded");self.assertTrue(p.trace);self.assertFalse(self.attacks(p))

    def test_FC03_unknown_types_and_nonvisible_targets_are_not_attacked(self):
        for kind in ["minecraft:guardian","minecraft:player","minecraft:cave_spider"]:
            p=Fighter();p.threats=[threat(kind)]
            self.assertEqual(self.execute(p).reason,"unsupported_hostile_nearby")
            self.assertFalse(self.attacks(p));self.assertFalse(p.trace)
        p=Fighter();p.threats=[dict(threat("minecraft:zombie"),visible=False)]
        self.assertEqual(self.execute(p,melee_wait_seconds=0.).reason,"no_visible_selected_enemy")
        self.assertFalse(self.attacks(p))

    def test_FC04_native_crosshair_identity_and_late_rejection_no_retry(self):
        for hit in [None,{"kind":"block","id":1},{"kind":"entity","id":99}]:
            p=Fighter();p.threats=[threat("minecraft:zombie")];p.hit_override=hit
            self.assertEqual(self.execute(p,duration_seconds=.5).status,"timed_out")
            self.assertFalse(self.attacks(p))
        p=Fighter();p.threats=[threat("minecraft:zombie")];attempts=[]
        def reject(*args,**kw):attempts.append(kw);raise BridgeError("target_entity_changed")
        p.action=reject
        self.assertEqual(self.execute(p).reason,"target_entity_changed")
        self.assertEqual(attempts,[{"actor_session":"actor-a","target_entity_id":1}])

    def test_FC05_weapon_gate_unarmed_optin_and_cooldown(self):
        for weapon in [None,{"item":"minecraft:dirt","count":2,"inventory_index":0},
                       {"item":"minecraft:iron_sword","count":1,"inventory_index":0,"damage":249,"max_damage":250}]:
            p=Fighter();p.weapon=weapon;p.threats=[threat("minecraft:zombie")]
            self.assertEqual(self.execute(p).reason,"select_usable_hotbar_weapon")
            self.assertFalse(self.attacks(p));self.assertFalse(p.trace)
        for item,interval in [(None,.5),("minecraft:iron_sword",.7),("minecraft:wooden_axe",1.3)]:
            p=Fighter();p.threats=[threat("minecraft:zombie")]
            if item is None:p.weapon=None
            else:p.weapon["item"]=item
            r=self.execute(p,allow_unarmed=True,duration_seconds=3.,timeout_seconds=4.)
            self.assertEqual(r.status,"timed_out")
            attacks=self.attacks(p);self.assertGreaterEqual(len(attacks),2)
            self.assertTrue(all(b[3]-a[3]>=interval for a,b in zip(attacks,attacks[1:])))
            self.assertIsNone(r.details.get("kills_confirmed"))

    def test_FC06_pursuit_uses_safe_flat_route_and_can_be_disabled(self):
        p=Fighter();p.threats=[threat("minecraft:skeleton",position=(4.5,64.,.5))]
        p.on_attack=lambda:p.threats.clear()
        r=self.execute(p,duration_seconds=8.,timeout_seconds=9.)
        self.assertEqual(r.status,"succeeded");self.assertTrue(p.trace);self.assertTrue(self.attacks(p))
        self.assertTrue(all(c[2]<=1 for c in p.calls if c[0]=="drive"))
        p=Fighter();p.threats=[threat("minecraft:skeleton",position=(4.5,64.,.5))]
        self.assertEqual(self.execute(p,pursue=False,melee_wait_seconds=0.).reason,"enemy_out_of_reach");self.assertFalse(p.trace)
        p=Fighter();p.cells={(0,64,0)};p.threats=[threat("minecraft:zombie",position=(4.5,64.,.5))]
        self.assertEqual(self.execute(p).reason,"no_known_safe_route");self.assertFalse(p.trace)

    def test_FC07_creeper_fight_hit_then_retreat_and_no_chase(self):
        p=Fighter();p.threats=[threat()]
        p.on_attack=lambda:p.threats[0]["position"].__setitem__(0,3.7)
        p.on_drive=lambda:p.threats.clear()
        r=self.execute(p,reactions={"creeper":"fight"})
        self.assertEqual(r.status,"succeeded");self.assertEqual(len(self.attacks(p)),1)
        self.assertTrue(p.trace);self.assertLess(p.position[0],.5)
        p=Fighter();p.threats=[threat(position=(5.5,64.,.5))]
        self.assertEqual(self.execute(p,reactions={"creeper":"fight"},duration_seconds=.5).status,"timed_out")
        self.assertFalse(p.trace);self.assertFalse(self.attacks(p))
        p=Fighter();p.threats=[threat(position=(1.5,64.,.5))];p.on_drive=lambda:p.threats.clear()
        self.execute(p,reactions={"creeper":"fight"});self.assertFalse(self.attacks(p));self.assertTrue(p.trace)

    def test_FC08_no_escape_and_unsafe_cells_fail_closed(self):
        p=Fighter();p.cells={(0,64,0)};p.threats=[threat()]
        self.assertEqual(self.execute(p,reactions={"creeper":"fight"}).reason,"no_known_escape_route")
        self.assertFalse(self.attacks(p));self.assertFalse(p.trace)
        p=Fighter();p.hazards.add((0,64,0));p.threats=[threat("minecraft:zombie")]
        self.assertEqual(self.execute(p).reason,"unsafe_current_cell");self.assertFalse(self.attacks(p))

    def test_FC09_low_health_boundary_and_damage_during_aim(self):
        for hp in [8.,8.001]:
            p=Fighter();p.health=hp;p.threats=[threat("minecraft:zombie")];p.on_attack=lambda:p.threats.clear()
            r=self.execute(p)
            self.assertEqual(r.reason,"low_health" if hp==8. else "no_selected_enemies_observed")
            self.assertEqual(bool(self.attacks(p)),hp>8.)
        p=Fighter();p.threats=[threat("minecraft:zombie")];original=p.look
        def damage(*args,**kw):original(*args,**kw);p.health=8.
        p.look=damage
        self.assertEqual(self.execute(p).reason,"low_health");self.assertFalse(self.attacks(p))
        self.assertLessEqual(len(p.drive_trace),1)

    def test_FC10_actor_replacement_before_attack_never_rebinds(self):
        p=Fighter();p.threats=[threat("minecraft:zombie")];original=p.look
        def replace(*args,**kw):original(*args,**kw);p.session="replacement"
        p.look=replace
        self.assertEqual(self.execute(p).reason,"actor_session_changed")
        self.assertFalse(self.attacks(p));self.assertFalse(p.held)
        p=Fighter();p.threats=[threat("minecraft:zombie")]
        def replace_after_hit():p.threats.clear();p.session="replacement"
        p.on_attack=replace_after_hit
        self.assertEqual(self.execute(p).reason,"actor_session_changed")  # Never claim victory in another world.

    def test_FC11_knockback_waits_without_actions_and_recovers(self):
        p=Fighter();p.threats=[threat("minecraft:zombie")]
        def airborne(s):
            if 2<=p.samples<=5:
                return {k:v for k,v in dict(s,ready=False,reason="not_grounded").items()
                        if k in {"profile","actor_session","position","health","alive","on_fire","ready","reason"}}
            return s
        p.transform=airborne
        def attack():self.assertGreater(p.samples,5);p.threats.clear()
        p.on_attack=attack
        self.assertEqual(self.execute(p).status,"succeeded");self.assertFalse(p.trace)

    def test_FC12_validation_precedes_all_effects(self):
        for args in [{"reactions":{"zombies":"hide"}},{"reactions":{"zombie":"fight"}},
                     {"reactions":{"timeout_seconds":1.}},{"min_health":0.},{"radius":9.},
                     {"allow_unarmed":1},{"pursue":"yes"},{"duration_seconds":float('nan')}]:
            p=Fighter()
            with self.subTest(args=args),self.assertRaises(ValidationError):self.execute(p,**args)
            self.assertEqual(p.calls,[])

    def test_FC13_cancel_deadline_and_unconfirmed_cleanup(self):
        p=Fighter();p.threats=[threat("minecraft:zombie")];event=threading.Event();p.on_attack=event.set
        r=run_skill(default_registry(),p,"fight",{},clock=p.clock,sleeper=p.sleep,cancel_event=event)
        self.assertEqual(r.status,"cancelled");self.assertEqual(len(self.attacks(p)),1);self.assertEqual(r.cleanup,"released")
        p=Fighter();p.threats=[threat("minecraft:zombie")];p.on_inventory=lambda:setattr(p,'now',p.now+1.)
        self.assertEqual(self.execute(p,duration_seconds=.2).status,"timed_out")
        self.assertFalse(any(c[0] in {"look","drive","action"} for c in p.calls))
        p=Fighter();p.stop=lambda:(_ for _ in ()).throw(BridgeError("fixture"))
        r=self.execute(p);self.assertEqual(r.status,"failed");self.assertEqual(r.cleanup,"not_confirmed")

    def test_FC14_late_evader_preempts_attack(self):
        p=Fighter();p.threats=[threat("minecraft:zombie")]
        def arrive(s):
            if p.samples==2:p.threats.append(threat(position=(3.5,64.,.5),entity_id=2))
            return s
        p.transform=arrive;p.on_drive=lambda:p.threats.clear()
        self.assertEqual(self.execute(p).status,"succeeded");self.assertFalse(self.attacks(p));self.assertTrue(p.trace)

    def test_FC15_mcp_background_policy_validation_ownership_and_cancel(self):
        from blockwire.mcp_server import create_server
        p=Fighter();p.threats=[threat("minecraft:zombie")]
        with patch("blockwire.mcp_server.Bridge.from_env"),patch("blockwire.mcp_server.Player",return_value=p):server=create_server()
        def call(name,**kw):return server._tool_manager.get_tool(name).fn(**kw)
        with self.assertRaises(ValidationError):call("fight",reactions={"zombies":"hide"})
        arg_model=server._tool_manager.get_tool("fight").fn_metadata.arg_model
        for bad in [{"allow_unarmed":1},{"pursue":"true"},{"min_health":"8"},{"reactions":{"creeper":"hide"}}]:
            with self.subTest(arguments=bad),self.assertRaises(ValidationError):arg_model.model_validate(bad)
        self.assertFalse(p.calls)
        job=call("fight",reactions={"zombies":"fight","creeper":"evade"})
        try:
            with self.assertRaises(RuntimeError):call("select_hotbar",slot=0)
            call("cancel_skill",job_id=job["id"])
            for _ in range(100):
                r=call("skill_status",job_id=job["id"])
                if r["status"]!="running":break
                time.sleep(.01)
            self.assertEqual(r["status"],"cancelled");self.assertEqual(r["result"]["cleanup"],"released")
        finally:call("cancel_skill",job_id=job["id"])

    def test_FC16_python_convenience_and_no_world(self):
        p=Player(CallableBackend(lambda q:{"profile":"flat_full_blocks_v1","ready":False,"reason":"not_in_world"}))
        self.assertEqual(p.fight(reactions={"creeper":"evade"})["reason"],"not_in_world")

    def test_FC17_radius_fire_and_observation_profile_guards(self):
        p=Fighter();p.threats=[threat("minecraft:zombie",position=(4.5,64.,.5))]
        p.cells.update((x,64,z) for x in range(16,25) for z in range(-4,5))
        p.on_drive=lambda:setattr(p,'position',[20.5,64.,.5])
        self.assertEqual(self.execute(p).reason,"activity_radius_exceeded")
        self.assertFalse(self.attacks(p))
        for patch_state,reason in [(dict(on_fire=True),'on_fire'),(dict(threat_profile='old'),'fight_observation_required'),
                                   (dict(ready=False,reason='screen_or_pause'),'screen_or_pause')]:
            p=Fighter();p.threats=[threat("minecraft:zombie")];original=p.navigation
            p.navigation=lambda f=original,fields=patch_state:dict(f(),**fields)
            self.assertEqual(self.execute(p).reason,reason);self.assertFalse(self.attacks(p));self.assertFalse(p.trace)
        p=Fighter();p.threats=[threat("minecraft:zombie")];p.fire=False
        nav,look=p.navigation,p.look
        p.navigation=lambda:dict(nav(),on_fire=p.fire)
        def ignite(*args,**kwargs):look(*args,**kwargs);p.fire=True
        p.look=ignite
        self.assertEqual(self.execute(p).reason,"on_fire");self.assertFalse(self.attacks(p))


if __name__ == '__main__':unittest.main()
