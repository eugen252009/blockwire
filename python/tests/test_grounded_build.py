"""Grounded builder contracts with an independent tiny voxel fixture.

The fixture mocks walking and vanilla GUI/placement. It is NOT Minecraft physics,
Creative GUI/mixin qualification, or acceptance of the user's house.
"""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import tempfile
import threading
import unittest
from unittest.mock import patch

from pydantic import ValidationError
from blockwire.client import Bridge, Player, BridgeError
from blockwire.creative import CreativeRequest, ObservedState, PROFILE
from blockwire.grounded_build import (BuildParameters, Builder, GuardedBackend, Ledger, run_build,
                                     poses, matches, static_state, main)
from blockwire.skills.core import SkillContext, SkillResult, SkillStop
from blockwire.ownership import claim_control, release_control
from blockwire.schematic import compile_schematic
from test_schematic import source_for

IDENTITY = '00000000-0000-0000-0000-000000000001'
AIR = {'id': 'minecraft:air', 'properties': {}}
DIRS = {'up': (0,1,0), 'down': (0,-1,0), 'east': (1,0,0), 'west': (-1,0,0), 'south': (0,0,1), 'north': (0,0,-1)}
SOLIDS = {'minecraft:oak_planks', 'minecraft:dirt', 'minecraft:cobblestone', 'minecraft:stone_bricks', 'minecraft:oak_log', 'minecraft:oak_wood'}


class Clock:
    def __init__(self): self.now = 0.
    def __call__(self): return self.now
    def sleep(self, seconds): self.now += seconds


class NativeFixture:
    """Independent ray/voxel fixture, deliberately not a native implementation."""
    def __init__(self, clock):
        self.clock, self.position, self.yaw, self.pitch = clock, [1.5,64.,2.5], 0., 0.
        self.actor, self.world, self.items, self.slot, self.watches = 'actor-A', {}, {}, 0, {}
        self.calls, self.closed, self.scene_patch = [], False, {}
        self.effect, self.material_effect, self.remove_effect = True, True, True
        self.stale_watch = self.stale_trace = self.owned_inputs = self.consume = False
        self.break_on = self.on_call = None
        self.rotation_id, self.rotation_active = 0, False
        for x in range(-4,7):
            for z in range(-4,7): self.world[x,63,z] = {'id':'minecraft:dirt','properties':{}}

    def state(self, pos): return copy.deepcopy(self.world.get(tuple(pos), AIR))
    def stamp(self): return {'profile':PROFILE,'actor_session':self.actor,'actor_tick':int(round(self.clock()*20))}
    def scene(self):
        return {'in_world':True,'alive':True,'actor_session':self.actor,'player_uuid':IDENTITY,'dimension':'minecraft:overworld',
            'creative_build_profile':PROFILE,'game_mode':'creative','flying':False,'fall_flying':False,'riding':False,
            'minecraft_data_version':5023,'health':20.,'position':self.position[:],
            'eye_position':[self.position[0],self.position[1]+1.62,self.position[2]],
            'rotation':{'rotation_id':self.rotation_id,'actor_session':self.actor,'active':self.rotation_active,'status':'completed'},
            'yaw':self.yaw,'pitch':self.pitch,'on_ground':True,'holding':copy.deepcopy(self.items.get(self.slot,{'item':'','count':0})),
            **self.scene_patch}

    def navigation(self):
        cells = []
        ox, oz = math.floor(self.position[0]), math.floor(self.position[2])
        for x in range(ox-4,ox+5):
            for z in range(oz-4,oz+5):
                solid = [p[1] for p, s in self.world.items() if p[0]==x and p[2]==z and s['id'] in SOLIDS]
                if not solid: continue
                y = max(solid)+1
                if abs(y-round(self.position[1])) > 2: continue
                if self.state((x,y,z)) != AIR or self.state((x,y+1,z)) != AIR: continue
                cells.append({'position':[x,y,z],'hazards':[]})
        transitions, edges = [], []
        for i, a in enumerate(cells):
            for j, b in enumerate(cells[:i]):
                dx,dy,dz = [abs(a['position'][k]-b['position'][k]) for k in range(3)]
                if dx+dz == 1 and dy <= 1:
                    edges.append([i,j]); transitions.append({'a':i,'b':j,'kind':'step' if dy else 'flat'})
        return {'profile':'stepped_full_blocks_v1','radius':4,'ready':True,'actor_session':self.actor,'position':self.position[:],
            'velocity':[0.,-.0784,0.],'on_ground':True,'current_cell':[math.floor(self.position[0]),round(self.position[1]),math.floor(self.position[2])],
            'current_center_access':True,'cells':cells,'edges':edges,'transitions':transitions,'nearby_hostiles':[], 'on_fire':False}

    def probe(self):
        eye = self.scene()['eye_position']; yaw,pitch = map(math.radians,(self.yaw,self.pitch))
        direction = (-math.sin(yaw)*math.cos(pitch),-math.sin(pitch),math.cos(yaw)*math.cos(pitch))
        hits = []
        for pos in self.world:
            near, far, face = -float('inf'),float('inf'),None
            for axis in range(3):
                if abs(direction[axis]) < 1e-10:
                    if not pos[axis] < eye[axis] < pos[axis]+1: far=-1;break
                    continue
                values = sorted(((pos[axis]-eye[axis])/direction[axis], (pos[axis]+1-eye[axis])/direction[axis]))
                if values[0] > near:
                    near = values[0]
                    delta = tuple((-1 if direction[axis]>0 else 1) if k==axis else 0 for k in range(3))
                    face = next(f for f,d in DIRS.items() if d==delta)
                far = min(far, values[1])
            if .00001 < near <= min(far,3.): hits.append((near,pos,face))
        out = {**self.stamp(),'hit':False,'placement_available':False}
        if not hits: return out
        distance,pos,face = min(hits)
        aim = [eye[i]+direction[i]*distance for i in range(3)]
        out.update(hit=True,position=list(pos),face=face,state=self.state(pos),aim_position=aim,hit_token='a'*64)
        item = self.items.get(self.slot,{}).get('item','')
        dest = tuple(pos[i]+DIRS[face][i] for i in range(3))
        if self.state(pos)['id'] not in SOLIDS or self.state(dest)!=AIR or not item: return out
        properties = {}
        facing = ('south','west','north','east')[int(math.floor(self.yaw/90+.5))%4]
        if item in {'minecraft:oak_log','minecraft:oak_wood'}:
            properties['axis'] = 'xyz'[next(i for i,d in enumerate(DIRS[face]) if d)]
        if item == 'minecraft:oak_stairs':
            properties = {'facing':facing,'half':'top' if face=='down' or (face not in {'up','down'} and aim[1]-pos[1]>.5) else 'bottom',
                          'shape':'straight','waterlogged':'false'}
        if item == 'minecraft:spruce_door':
            if self.state((dest[0],dest[1]+1,dest[2])) != AIR: return out
            properties={'facing':facing,'half':'lower','hinge':'left','open':'false','powered':'false'}
        out.update(placement_available=True,destination=list(dest),candidate={'id':item,'properties':properties},
                   destination_was_air=True,placement_token='b'*64)
        return out

    def close(self): self.closed=True
    def call(self, op, **q):
        self.calls.append((op,copy.deepcopy(q)))
        if self.on_call: self.on_call(op,q)
        if self.break_on == (op,q.get('action')): raise BridgeError('fixture_lost_response')
        if op=='observe': return self.scene()
        if op=='navigation': return self.navigation()
        if op=='inventory':
            return {'actor_session':self.actor,'guarded_inventory':True,'container_open':False,'carried':{'empty':True},
                    'items':[dict(inventory_index=i,**v) for i,v in self.items.items()]}
        if op=='motion_trace':
            return {'profile':'native_player_motion_ticks_v1','actor_session':self.actor,'samples':[{
                'actor_session':self.actor,'client_tick':0 if self.stale_trace else int(round(self.clock()*20)),
                'position':self.position[:], 'on_ground':True, 'sneaking':False,
                'bounding_box':[self.position[0]-.3,self.position[1],self.position[2]-.3,
                                self.position[0]+.3,self.position[1]+1.8,self.position[2]+.3],
                'inputs':{k:False for k in ('forward','back','left','right','jump','sneak','sprint','attack','use')},
                'remote_owned_inputs':['forward'] if self.owned_inputs else []}]}
        if op=='look':
            self.yaw,self.pitch=q['yaw'],q['pitch'];self.rotation_id+=1
            return {'rotation_id':self.rotation_id}
        if op=='drive': return {}
        if op=='stop': return {}
        if op=='hotbar': self.slot=q['slot'];return {}
        if op!='creative': raise AssertionError(op)
        CreativeRequest.model_validate(q)
        action=q['action'];out=self.stamp()
        if action=='probe': return self.probe()
        if action=='material':
            old=self.items.get(q['slot'],{'item':'','count':0})
            assert (q['expected_item'],q['expected_count'])==(old['item'],old['count'])
            if self.material_effect: self.items[q['slot']]={'item':q['item'],'count':64}
            return dict(out,submitted=True)
        if action in {'place','remember'}:
            pos=tuple(q['position']);ticket=hashlib.sha256(str(len(self.watches)).encode()).hexdigest()
            parts=[pos]
            if action=='place':
                probe=self.probe();assert probe['destination']==list(pos) and q['token']==probe['placement_token']
                state=probe['candidate']
                if state['id']=='minecraft:spruce_door': parts.append((pos[0],pos[1]+1,pos[2]))
                if self.effect:
                    self.world[pos]=state
                    if len(parts)==2: self.world[parts[1]]={'id':state['id'],'properties':dict(state['properties'],half='upper')}
                if self.consume: self.items[self.slot]['count']-=1
            self.watches[ticket]=(parts,action=='place')
            return dict(out,submitted=True,destination_was_air=True,ticket=ticket)
        if action=='check':
            parts,placed=self.watches[q['ticket']]
            if self.stale_watch: out['actor_tick']=0
            return dict(out,ticket=q['ticket'],source='explicit_client_known_watch_v1',visual_observation=False,
                        placed_by_this_controller=placed,states=[dict(self.state(p),position=list(p)) for p in parts])
        if action=='toggle':
            pos=tuple(q['position'])
            for p in (pos,(pos[0],pos[1]+1,pos[2])): self.world[p]['properties']['open']=str(q['open']).lower()
            return dict(out,submitted=True)
        if action=='remove':
            if self.remove_effect: self.world.pop(tuple(q['position']))
            return dict(out,submitted=True,ticket=q['ticket'])
        raise AssertionError(action)


def simulated_walk(context, params, *, expected_session, pose_handoff):
    assert expected_session=='actor-A' and pose_handoff is True
    context.player.drive(['forward'],ticks=1,wait=False,actor_session=expected_session)
    context.player.backend.backend.position=[params.x,params.y,params.z]
    context.player.stop()
    return SkillResult(status='succeeded',reason='fixture_walk',text='NOT NATIVE')


class GroundedBuildContracts(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.clock=Clock();self.native=NativeFixture(self.clock)
        self.player=Player(self.native);self.cancel=threading.Event()
        self.source=source_for([('minecraft:oak_planks',{})])
        self.params=BuildParameters(player_uuid=IDENTITY,world_id='fixture-only',origin=[1,64,1])
        self.walk=patch('blockwire.grounded_build.walk_to',side_effect=simulated_walk);self.walk.start();self.addCleanup(self.walk.stop)

    def run_builder(self, **kwargs):
        return run_build(self.player,self.source,self.params,self.root/'run',cancel=self.cancel,
                         clock=self.clock,sleeper=self.clock.sleep,**kwargs)

    def unit(self):
        ledger=Ledger(self.root/'unit');self.addCleanup(ledger.close)
        plan=compile_schematic(self.source,origin=self.params.origin)
        ctx=SkillContext(self.player,self.cancel,100.,lambda _:None,self.clock,self.clock.sleep)
        guard=GuardedBackend(self.native,ctx,self.params,ledger,plan);ctx.player=Player(guard)
        builder=Builder(ctx,self.params,plan,guard,ledger);builder.scene()
        return builder,guard,ledger

    def test_GB01_full_disclosed_simulation_and_durable_intents(self):
        result=self.run_builder()
        self.assertEqual((result.status,result.cleanup),('succeeded','released'),result)
        self.assertFalse(result.details['unknown_no_retry']);self.assertEqual(self.native.state((1,64,1))['id'],'minecraft:oak_planks')
        self.assertEqual(self.native.position,[1.5,64.,2.5]);self.assertEqual(self.native.items[0]['count'],64)
        rows=[json.loads(s) for s in (self.root/'run/journal.jsonl').read_text().splitlines()]
        intents=[r for r in rows if r['event']=='intent']
        self.assertTrue(any(r['op']=='creative' and r['arguments']['action']=='place' for r in intents))
        for op,args in self.native.calls:
            if op in {'look','drive'}:
                self.assertIs(args['grounded_creative'],True);self.assertEqual(args['actor_session'],'actor-A')
        for file in (self.root/'run').iterdir(): self.assertEqual(stat.S_IMODE(file.stat().st_mode),0o600)
        self.assertEqual(stat.S_IMODE((self.root/'run').stat().st_mode),0o700)
        self.assertEqual(json.loads((self.root/'run/FINISHED.json').read_text())['result_sha256'],hashlib.sha256((self.root/'run/result.json').read_bytes()).hexdigest())
        self.assertEqual(json.loads((self.root/'run/plan.json').read_text())['execution_ready'],False)

    def test_GB02_receipt_without_material_readback_never_places(self):
        self.native.material_effect=False
        result=self.run_builder();self.assertNotEqual(result.status,'succeeded');self.assertTrue(result.details['unknown_no_retry'])
        self.assertFalse(any(q.get('action')=='place' for _,q in self.native.calls))

    def test_GB03_receipt_without_placement_postcondition_is_not_success(self):
        self.native.effect=False
        result=self.run_builder();self.assertNotEqual(result.status,'succeeded');self.assertTrue(result.details['unknown_no_retry'])
        self.assertEqual(sum(q.get('action')=='place' for _,q in self.native.calls),1)

    def test_GB04_no_resume_or_overwrite_even_empty_directory(self):
        (self.root/'run').mkdir()
        result=self.run_builder();self.assertNotEqual(result.status,'succeeded');self.assertEqual(self.native.calls,[])
        lease=claim_control(self.player,self.cancel.set);release_control(self.player,lease)

    def test_GB05_strict_parameters_and_native_envelopes(self):
        for updates in ({'origin':[True,64,0]},{'allow_scaffolds':'yes'},{'timeout_seconds':float('nan')},{'max_scaffolds':257},{'player_uuid':'wrong'}):
            with self.assertRaises(ValidationError): BuildParameters(**(self.params.model_dump()|updates))
        for request in ({'action':'check','ticket':'a'*64,'position':[0,64,0]}, {'action':'place','token':'a'*64,'position':[True,64,0]},
            {'action':'material','item':'minecraft:command_block','slot':0,'expected_item':'','expected_count':0}, {'action':'probe','item':None}):
            with self.assertRaises(ValidationError): CreativeRequest(actor_session='actor',**request)
        with self.assertRaises(ValidationError): ObservedState(id='minecraft:dirt',properties={},position=[0,True,0])
        self.assertEqual(self.player.creative('probe',actor_session='actor-A')['profile'],PROFILE)

    def test_GB06_cancel_before_first_read_has_no_actions(self):
        self.cancel.set();result=self.run_builder()
        self.assertEqual(result.status,'cancelled');self.assertEqual(self.native.calls,[])
        self.assertEqual(result.cleanup,'not_required')
        self.cancel.clear();_,guard,_=self.unit();before=len(self.native.calls);self.cancel.set()
        with self.assertRaises(SkillStop): guard.call('observe')
        self.assertEqual(len(self.native.calls),before)

    def test_GB07_preflight_mode_identity_version_or_ui_failure_has_no_effects(self):
        for field,value in [('game_mode','survival'),('flying',True),('fall_flying',True),('riding',True),('minecraft_data_version',1),
                            ('player_uuid','other'),('creative_build_profile','old'),('screen','inventory')]:
            with self.subTest(field=field):
                self.native.scene_patch={field:value}
                result=run_build(self.player,self.source,self.params,self.root/field,clock=self.clock,sleeper=self.clock.sleep)
                self.assertNotEqual(result.status,'succeeded');self.assertEqual(result.details['native_effects'],0)
        self.assertTrue(all(op=='observe' for op,_ in self.native.calls))

    def test_GB08_actor_or_damage_change_during_actions_stops(self):
        builder,guard,_=self.unit()
        self.native.actor='other'
        with self.assertRaises(SkillStop): builder.aim((1.5,64,1.5))
        self.assertFalse(any(op=='look' for op,_ in self.native.calls))
        self.native.actor='actor-A';self.native.scene_patch={'health':19.}
        with self.assertRaises(SkillStop): builder.aim((1.5,64,1.5))

    def test_GB09_unknown_transport_latches_even_cleanup_no_reconnect(self):
        self.native.break_on=('creative','place')
        result=self.run_builder();self.assertEqual(result.reason,'unknown_no_retry')
        self.assertTrue(result.details['unknown_no_retry']);self.assertEqual(result.cleanup,'not_confirmed');self.assertTrue(self.native.closed)
        self.assertEqual(self.native.calls[-1][1]['action'],'place')

    def test_GB10_deadline_after_dispatch_never_replays(self):
        def timeout(op,q):
            if q.get('action')=='place': self.clock.now=1801.
        self.native.on_call=timeout
        result=self.run_builder();self.assertEqual(result.status,'timed_out');self.assertTrue(result.details['unknown_no_retry'])
        self.assertEqual(sum(q.get('action')=='place' for _,q in self.native.calls),1)
        self.assertEqual(result.cleanup,'released')

    def test_GB11_stale_ticks_never_verify_effect(self):
        self.native.stale_watch=True
        result=self.run_builder();self.assertNotEqual(result.status,'succeeded');self.assertTrue(result.details['unknown_no_retry'])

    def test_GB12_unconfirmed_release_invalidates_success(self):
        self.native.owned_inputs=True
        result=self.run_builder();self.assertEqual((result.status,result.cleanup),('failed','not_confirmed'))
        self.assertTrue(result.details['unknown_no_retry'])

    def test_GB13_survival_consumption_is_not_accepted_as_creative(self):
        self.native.consume=True
        result=self.run_builder();self.assertNotEqual(result.status,'succeeded');self.assertEqual(result.reason,'creative_material_count_changed')

    def test_GB14_full_state_and_only_explicit_deferred_properties(self):
        desired={'id':'minecraft:oak_stairs','properties':{'half':'bottom','facing':'south','shape':'inner_left','waterlogged':'false'}}
        actual=copy.deepcopy(desired);actual['properties']['shape']='straight'
        self.assertTrue(matches(actual,desired));self.assertFalse(matches(actual,desired,final=True))
        actual['properties']['waterlogged']='true';self.assertFalse(matches(actual,desired))
        for axis in ('x','z'):
            self.assertFalse(matches({'id':'minecraft:oak_log','properties':{'axis':axis}},{'id':'minecraft:oak_log','properties':{'axis':'y'}}))

    def test_GB15_owned_hotbar_cannot_replace_foreign_changed_contents(self):
        builder,_,_=self.unit();builder.material('minecraft:dirt')
        self.native.items[builder.slot]={'item':'minecraft:oak_log','count':64}
        before=len(self.native.calls)
        with self.assertRaises(SkillStop): builder.material('minecraft:oak_planks')
        self.assertFalse(any(q.get('action')=='material' for _,q in self.native.calls[before:]))

    def test_GB16_motion_is_fenced_bounded_and_not_a_mining_interface(self):
        _,guard,_=self.unit()
        for params in ({'buttons':['jump'],'ticks':9,'actor_session':'actor-A'}, {'buttons':['attack'],'ticks':1,'actor_session':'actor-A'},
                       {'buttons':['forward'],'ticks':1,'actor_session':'other'}):
            with self.assertRaises(SkillStop): guard.call('drive',**params)
        with self.assertRaises(SkillStop): guard.call('action',name='attack',actor_session='actor-A')
        self.assertFalse(any(op in {'drive','action'} for op,_ in self.native.calls))

    def test_GB17_navigation_does_not_invent_unknown_cells_or_gap_routes(self):
        builder,_,_=self.unit();nav=builder.nav()
        self.assertTrue(poses(nav,(1,64,1)))
        self.assertFalse(poses(nav,(40,64,40)))
        original=self.native.navigation
        def gap():
            data=original()
            for item in data['transitions']: item['kind']='gap_jump'
            return data
        self.native.navigation=gap
        self.assertEqual(builder.nav()['edges'],[])

    def test_GB18_no_scaffold_authorization_means_none(self):
        builder,_,_=self.unit();nav=builder.nav()
        self.assertEqual(builder.scaffold_candidates(list(builder.targets.values()),nav),[])
        with self.assertRaises(SkillStop): builder.install((0,64,0),{'id':'minecraft:cobblestone','properties':{}},temporary=True)
        self.assertFalse(any(q.get('action')=='place' for _,q in self.native.calls))

    def test_GB19_scaffold_observed_ownership_and_removal(self):
        self.params=self.params.model_copy(update={'allow_scaffolds':True})
        builder,_,_=self.unit()
        self.assertTrue(builder.install((0,64,1),{'id':'minecraft:cobblestone','properties':{}},temporary=True))
        self.assertEqual(set(builder.scaffolds),{(0,64,1)})
        builder.cleanup_scaffolds()
        self.assertEqual(builder.removed,{(0,64,1)});self.assertEqual(self.native.state((0,64,1)),AIR)
        self.assertTrue(any(q.get('action')=='remove' for _,q in self.native.calls))

    def test_GB20_foreign_changed_scaffold_is_not_removed(self):
        self.params=self.params.model_copy(update={'allow_scaffolds':True})
        builder,_,_=self.unit();builder.install((0,64,1),{'id':'minecraft:cobblestone','properties':{}},temporary=True)
        self.native.world[0,64,1]={'id':'minecraft:oak_planks','properties':{}}
        with self.assertRaises(SkillStop): builder.cleanup_scaffolds()
        self.assertFalse(any(q.get('action')=='remove' for _,q in self.native.calls))

    def test_GB21_door_pair_and_open_postcondition(self):
        props={'facing':'south','half':'lower','hinge':'left','open':'true','powered':'false'}
        self.source=source_for([('minecraft:spruce_door',props),('minecraft:spruce_door',dict(props,half='upper'))])
        result=self.run_builder();self.assertEqual(result.status,'succeeded',result)
        self.assertEqual(sum(q.get('action')=='place' for _,q in self.native.calls),1)
        self.assertEqual(sum(q.get('action')=='toggle' for _,q in self.native.calls),1)
        self.assertEqual(self.native.state((1,65,1))['properties']['open'],'true')

    def test_GB22_final_neighbor_verification_is_not_just_placement(self):
        self.source=source_for([('minecraft:oak_stairs',{'facing':'south','half':'bottom','shape':'inner_left','waterlogged':'false'})])
        result=self.run_builder();self.assertNotEqual(result.status,'succeeded');self.assertEqual(result.reason,'final_block_state_mismatch')
        self.assertEqual(sum(q.get('action')=='place' for _,q in self.native.calls),1)

    def test_GB23_audit_failure_before_send_denies_effect(self):
        builder,guard,ledger=self.unit()
        with patch.object(ledger,'append',side_effect=OSError('disk fixture')):
            with self.assertRaises(OSError): builder.aim((1.5,64,1.5))
        self.assertFalse(any(op=='look' for op,_ in self.native.calls))
        guard.call('stop');self.assertEqual(self.native.calls[-1][0],'stop')

    def test_GB24_cleanup_attempts_stop_after_bad_trace(self):
        _,guard,_=self.unit();original=self.native.call
        def call(op,**q):
            if op=='motion_trace': return {'bad':True}
            return original(op,**q)
        self.native.call=call
        self.assertFalse(guard.release_proof());self.assertEqual(self.native.calls[-1][0],'stop')

    def test_GB25_owned_control_excludes_parallel_builder(self):
        lease=claim_control(self.player,lambda:None)
        try:
            with self.assertRaises(RuntimeError): self.run_builder()
            self.assertFalse((self.root/'run').exists())
        finally: release_control(self.player,lease)

    def test_GB26_cli_requires_explicit_authorization_before_connection(self):
        with patch('blockwire.grounded_build.Bridge.from_env') as bridge:
            with self.assertRaises(SystemExit): main(['unselected.litematic'])
            bridge.assert_not_called()

    def test_GB27_removal_receipt_without_air_postcondition_stops(self):
        self.params=self.params.model_copy(update={'allow_scaffolds':True})
        builder,guard,_=self.unit();builder.install((0,64,1),{'id':'minecraft:cobblestone','properties':{}},temporary=True)
        self.native.remove_effect=False
        with self.assertRaises(SkillStop): builder.cleanup_scaffolds()
        self.assertTrue(guard.uncertain);self.assertFalse(builder.removed)
        self.assertEqual(sum(q.get('action')=='remove' for _,q in self.native.calls),1)

    def test_GB28_cancel_after_dispatch_does_not_start_scaffold_cleanup(self):
        def cancel(op,q):
            if q.get('action')=='place': self.cancel.set()
        self.native.on_call=cancel
        result=self.run_builder()
        self.assertEqual(result.status,'cancelled');self.assertTrue(result.details['unknown_no_retry'])
        self.assertEqual(result.cleanup,'released')
        self.assertFalse(any(q.get('action')=='remove' for _,q in self.native.calls))

    def test_GB29_revalidate_mutated_parameters_before_connection(self):
        self.params=self.params.model_copy(update={'timeout_seconds':float('inf')})
        with self.assertRaises(ValidationError): self.run_builder()
        self.assertEqual(self.native.calls,[]);self.assertFalse((self.root/'run').exists())

    def test_GB30_mismatched_native_prediction_never_places(self):
        self.source=source_for([('minecraft:oak_log',{'axis':'y'})])
        builder,_,_=self.unit();original=self.native.probe
        def wrong():
            value=original()
            if value.get('placement_available'): value['candidate']['properties']['axis']='x'
            return value
        self.native.probe=wrong
        placed=False
        try: placed=builder.install((1,64,1),{'id':'minecraft:oak_log','properties':{'axis':'y'}})
        except SkillStop: pass
        self.assertFalse(placed)
        self.assertFalse(any(q.get('action')=='place' for _,q in self.native.calls))

    def test_GB31_scaffold_only_one_material_and_fresh_native_floor(self):
        self.params=self.params.model_copy(update={'allow_scaffolds':True})
        builder,_,_=self.unit()
        with self.assertRaises(SkillStop): builder.install((0,64,1),{'id':'minecraft:dirt','properties':{}},temporary=True)
        self.assertTrue(builder.install((0,64,1),{'id':'minecraft:cobblestone','properties':{}},temporary=True))
        records=[json.loads(s) for s in (self.root/'unit/journal.jsonl').read_text().splitlines()]
        self.assertTrue(any(row['event']=='scaffold_plan' and row['full_floor_below_observed'] is True for row in records))

    def test_GB32_matching_angles_are_not_completed_camera_plan(self):
        self.native.rotation_active=True
        result=self.run_builder()
        self.assertEqual(result.reason,'aim_not_observed')
        self.assertFalse(any(q.get('action')=='place' for _,q in self.native.calls))

    def test_GB33_native_watch_position_or_ticket_cannot_change(self):
        builder,_,_=self.unit()
        builder.install((1,64,1),{'id':'minecraft:oak_planks','properties':{}})
        ticket=builder.proofs[(1,64,1)]
        original=self.native.call
        def changed(op,**q):
            value=original(op,**q)
            if q.get('action')=='check': value['ticket']='c'*64
            return value
        self.native.call=changed
        with self.assertRaises(SkillStop): builder.watch(ticket)

    def test_GB34_unobserved_floor_cannot_authorize_a_scaffold(self):
        self.params=self.params.model_copy(update={'allow_scaffolds':True})
        builder,_,_=self.unit()
        original=builder.nav
        count=[0]
        def missing():
            count[0]+=1;value=original()
            if count[0]>1:
                # Deliberately retain all geometry, but mark the prospective
                # scaffold's floor unsafe in the fresh post-approach snapshot.
                for c in value['cells']:
                    if c['position']==[0,64,1]: c['hazards']=['unknown_floor_fixture']
            return value
        builder.nav=missing
        with self.assertRaises(SkillStop): builder.install((0,64,1),{'id':'minecraft:cobblestone','properties':{}},temporary=True)
        self.assertFalse(any(q.get('action')=='place' for _,q in self.native.calls))

    def test_GB35_transport_fault_cannot_be_reopened_for_reads_or_cleanup(self):
        _,guard,_=self.unit();self.native.break_on=('observe',None)
        with self.assertRaises(BridgeError): guard.transport('observe')
        before=len(self.native.calls);self.native.break_on=None
        with self.assertRaises(RuntimeError): guard.transport('observe')
        with self.assertRaises(RuntimeError): guard.call('stop')
        self.assertEqual(len(self.native.calls),before)

    def test_GB36_watch_without_controller_ownership_never_removes(self):
        self.params=self.params.model_copy(update={'allow_scaffolds':True})
        builder,_,_=self.unit();builder.install((0,64,1),{'id':'minecraft:cobblestone','properties':{}},temporary=True)
        ticket=builder.scaffolds[(0,64,1)];parts,_=self.native.watches[ticket]
        self.native.watches[ticket]=(parts,False)
        try: builder.cleanup_scaffolds()
        except SkillStop: pass
        self.assertFalse(any(q.get('action')=='remove' for _,q in self.native.calls))

    def test_GB37_geometric_nearby_is_not_observed_support(self):
        builder,_,_=self.unit();nav=builder.nav()
        for cell in nav['cells']:
            if cell['position']==[1,64,1]: cell['hazards']=['unknown_floor_fixture']
        self.assertFalse(poses(nav,(1,64,1)))

    def test_GB38_actual_bridge_socket_identity_is_pinned(self):
        _,guard,_=self.unit();bridge=Bridge('a'*64);guard.backend=bridge
        def connect():
            bridge._socket=object();return bridge
        with patch.object(bridge,'connect',side_effect=connect) as connections, patch.object(bridge,'call',return_value={}) as calls, patch.object(bridge,'close'):
            guard.transport('observe')
            bridge._socket=None  # External closure without a preceding RPC exception.
            with self.assertRaises(BridgeError): guard.transport('observe')
            self.assertEqual(connections.call_count,1);self.assertEqual(calls.call_count,1)
            self.assertTrue(guard.lost)

    def test_GB39_keyboard_interrupt_during_rpc_is_unknown_without_reconnect(self):
        def interrupt(op,q):
            if q.get('action')=='place': raise KeyboardInterrupt()
        self.native.on_call=interrupt
        result=self.run_builder()
        self.assertEqual(result.status,'cancelled');self.assertTrue(result.details['unknown_no_retry'])
        self.assertEqual(result.cleanup,'not_confirmed');self.assertTrue(self.native.closed)
        self.assertEqual(self.native.calls[-1][1]['action'],'place')

    def test_GB40_run_directory_parent_is_durable_before_first_rpc(self):
        synced=set();original=os.fsync
        def fsync(fd):
            synced.add(os.fstat(fd).st_ino);original(fd)
        def check(op,q):
            assert self.root.stat().st_ino in synced, 'Parent directory was not durably reserved'
        self.native.on_call=check
        with patch('blockwire.grounded_build.os.fsync',side_effect=fsync): result=self.run_builder()
        self.assertEqual(result.status,'succeeded',result)

    def test_GB41_final_read_must_cover_every_door_half(self):
        props={'facing':'south','half':'lower','hinge':'left','open':'true','powered':'false'}
        self.source=source_for([('minecraft:spruce_door',props),('minecraft:spruce_door',dict(props,half='upper'))])
        original=self.native.call;opened_reads=[0]
        def partial(op,**q):
            value=original(op,**q)
            if q.get('action')=='check' and all(row['properties'].get('open')=='true' for row in value['states']):
                opened_reads[0]+=1
                if opened_reads[0]>=3: value['states']=value['states'][:1]
            return value
        self.native.call=partial
        result=self.run_builder()
        self.assertNotEqual(result.status,'succeeded');self.assertEqual(result.reason,'final_target_observation_incomplete')


if __name__=='__main__': unittest.main()
