"""Execution-scope reuse contracts on fake state; NOT Minecraft acceptance."""
import math
import threading
import unittest
from blockwire import CallableBackend,Player,BridgeError
from blockwire.skills.core import ExecutionOptions,SkillDefinition,SkillParameters,SkillRegistry,SkillResult,run_skill
from blockwire.skills.item_actions import PlaceBlock,place_block
from test_crafting import CraftNative


class ReuseWorld(CraftNative):
    def __init__(self):
        super().__init__({0:('minecraft:cobblestone',12)})
        self.support_x=1;self.placed=set();self.uses=0;self.stops=0;self.drives=0;self.observes=0
        self.crouched=False;self.now=0.;self.yaw=0.;self.pitch=0.;self.after_use=lambda:None
        self.stances_at_use=[]
    def clock(self):return self.now
    def sleep(self,seconds):self.now+=seconds
    def call(self,op,**q):
        if op=='drive':
            if q['actor_session']!=self.session:
                from blockwire.client import NativeRejected
                raise NativeRejected('actor_session_changed')
            assert q['buttons']==['sneak'] and 1<=q['ticks']<=8
            self.crouched=True;self.drives+=1;return {}
        if op=='stop':self.stops+=1;self.crouched=False
        if op=='look':
            assert q['actor_session']==self.session
            self.yaw,self.pitch=q['yaw'],q['pitch'];return {}
        if op=='action':
            assert q['actor_session']==self.session and q['name']=='use'
            self.uses+=1;self.placed.add(self.support_x);self.stances_at_use.append(self.crouched)
            self.items[0]=('minecraft:cobblestone',12-self.uses)
            self.after_use();return {}
        value=super().call(op,**q)
        if op=='observe':
            self.observes+=1
            value.update(position=[1.5,64.,-1.5],eye_position=[1.5,64.+(1.27 if self.crouched else 1.62),-1.5],
                yaw=self.yaw,pitch=self.pitch,on_ground=True,visibility={'profile':'sampled_surfaces_v1'},
                target={'kind':'block','id':'minecraft:grass_block','position':[self.support_x,63,0],'face':'up'},
                sight_target={'id':'minecraft:grass_block','position':[self.support_x,63,0]},
                visible_blocks={'encoding':'palette_x_runs_v1','origin':[0,64,0],
                    'palette':['minecraft:grass_block','minecraft:cobblestone'],
                    'runs':[[0,x,-1,0,1] for x in (1,2,3)]+[[1,x,0,0,1] for x in sorted(self.placed)]})
        return value


class ReuseContracts(unittest.TestCase):
    def execute(self,options,world=None,cancel=None):
        world=world or ReuseWorld();player=Player(CallableBackend(lambda q:world.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        def sequence(context,goal):
            self.last_context=context
            results=[]
            for x in (1,2,3):
                context.check();world.support_x=x
                result=place_block(context,PlaceBlock(block='minecraft:cobblestone',support=[x,63,0],recorded_sneak=True),
                                   preserve_recorded_sneak=options.sneak_reuse)
                results.append(result.model_dump())
                if result.status!='succeeded':return result
            return SkillResult(status='succeeded',reason='three_verified',text='Fake sequence',details={'operations':results})
        registry=SkillRegistry();registry.register(SkillDefinition('test_sequence','Fixture',SkillParameters,sequence))
        result=run_skill(registry,player,'test_sequence',{},clock=world.clock,sleeper=world.sleep,
                         cancel_event=cancel,execution_options=options)
        return world,result

    def test_reuse_defaults_off_and_strict_typed_host_options(self):
        self.assertEqual(ExecutionOptions(),ExecutionOptions(False,False,False))
        for value in (1,'true',None):
            with self.assertRaises(ValueError):ExecutionOptions(camera_reuse=value)
        world,result=self.execute(ExecutionOptions())
        self.assertEqual(result.status,'succeeded');self.assertEqual(world.uses,3)
        self.assertEqual(world.stops,4);self.assertFalse(world.crouched)

    def test_independent_reuse_preserves_every_postcondition_and_final_release(self):
        baseline,_=self.execute(ExecutionOptions())
        for options in (ExecutionOptions(camera_reuse=True),ExecutionOptions(sneak_reuse=True),
                        ExecutionOptions(placement_reuse=True),ExecutionOptions(True,True,True)):
            with self.subTest(options=options):
                world,result=self.execute(options)
                self.assertEqual(result.status,'succeeded',result);self.assertEqual(world.uses,3)
                self.assertEqual(world.placed,{1,2,3});self.assertEqual(result.cleanup,'released')
                self.assertFalse(world.crouched)
                self.assertEqual(len(result.details['operations']),3)
                if options.sneak_reuse:self.assertEqual(world.stops,1)
                if options.camera_reuse:self.assertLess(world.now,baseline.now)
                if options.placement_reuse:self.assertLess(world.observes,baseline.observes)

    def test_cached_adapter_still_rejects_actor_replacement_before_next_use(self):
        world=ReuseWorld();world.after_use=lambda:setattr(world,'session','replacement')
        world,result=self.execute(ExecutionOptions(True,True,True),world)
        self.assertEqual(result.status,'blocked');self.assertEqual(result.reason,'actor_session_changed')
        self.assertEqual(world.uses,1);self.assertFalse(world.crouched)
        self.assertEqual(result.cleanup,'released')

    def test_cancel_while_stance_owned_releases_without_another_action(self):
        event=threading.Event();world=ReuseWorld();world.after_use=event.set
        world,result=self.execute(ExecutionOptions(True,True,True),world,event)
        self.assertEqual(result.status,'cancelled');self.assertEqual(world.uses,1)
        self.assertFalse(world.crouched);self.assertEqual(result.cleanup,'released')

    def test_closed_context_cannot_refresh_a_retained_input_or_cached_adapter(self):
        from blockwire.skills.core import SkillStop
        world,result=self.execute(ExecutionOptions(True,True,True))
        self.assertEqual(result.status,'succeeded')
        context=self.last_context;before=world.drives
        self.assertFalse(context.active);self.assertIsNone(context.retained_sneak_session)
        self.assertIsNone(context.placement_session)
        with self.assertRaises(SkillStop) as error:context.renew_retained_sneak({'actor_session':world.session,'in_world':True,'alive':True})
        self.assertEqual(error.exception.reason,'execution_context_closed')
        self.assertEqual(world.drives,before)

    def test_fresh_actor_is_required_before_renewing_retained_stance(self):
        from blockwire.skills.core import SkillContext,SkillStop
        world=ReuseWorld();player=Player(CallableBackend(lambda q:world.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        context=SkillContext(player,threading.Event(),30.,lambda _:None,world.clock,world.sleep,ExecutionOptions(sneak_reuse=True))
        context.retain_sneak(world.session)
        context.renew_retained_sneak({'actor_session':world.session,'in_world':True,'alive':True})
        self.assertEqual(world.drives,1)
        with self.assertRaises(SkillStop):context.renew_retained_sneak({'actor_session':'replacement','in_world':True,'alive':True})
        self.assertEqual(world.drives,1)

    def test_unrequested_sneak_is_released_before_an_ordinary_placement(self):
        from blockwire.skills.core import SkillContext
        world=ReuseWorld();player=Player(CallableBackend(lambda q:world.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        context=SkillContext(player,threading.Event(),30.,lambda _:None,world.clock,world.sleep,ExecutionOptions(True,True,True))
        first=place_block(context,PlaceBlock(block='minecraft:cobblestone',support=[1,63,0],recorded_sneak=True),preserve_recorded_sneak=True)
        self.assertEqual(first.status,'succeeded');self.assertTrue(world.crouched)
        world.support_x=2
        second=place_block(context,PlaceBlock(block='minecraft:cobblestone',support=[2,63,0]))
        self.assertEqual(second.status,'succeeded');self.assertEqual(world.stances_at_use,[True,False])
        self.assertIsNone(context.retained_sneak_session)
        player.stop()

    def test_only_known_interactive_full_cube_requires_crouch(self):
        for support_id,expected in (('minecraft:crafting_table','succeeded'),('minecraft:chest','blocked')):
            with self.subTest(support_id=support_id):
                world=ReuseWorld();original=world.call
                def call(op,**q):
                    value=original(op,**q)
                    if op=='observe':
                        value['target']['id']=support_id;value['sight_target']['id']=support_id
                        value['visible_blocks']['palette'][0]=support_id
                    return value
                world.call=call
                player=Player(CallableBackend(lambda q:world.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
                from blockwire.skills import default_registry
                result=run_skill(default_registry(),player,'place_block',{'block':'minecraft:cobblestone','support':[1,63,0]},clock=world.clock,sleeper=world.sleep)
                self.assertEqual(result.status,expected,result)
                self.assertEqual(world.stances_at_use,[True] if expected=='succeeded' else [])
                self.assertFalse(world.crouched);self.assertEqual(result.cleanup,'released')

    def test_inventory_transport_loss_is_not_retried(self):
        world=ReuseWorld();original=world.call
        def call(op,**q):
            if op=='inventory' and world.uses:raise BridgeError('uncertain connection')
            return original(op,**q)
        world.call=call
        world,result=self.execute(ExecutionOptions(True,True,True),world)
        self.assertEqual(result.status,'failed');self.assertEqual(result.reason,'transport_error')
        self.assertEqual(world.uses,1);self.assertFalse(world.crouched)

if __name__=='__main__':unittest.main()
