"""Deterministic mechanics only. No claim of native forestry/crafting/building acceptance."""
import copy,json,unittest
from blockwire import Player,CallableBackend
from blockwire.machine_actions import action_registry
from blockwire.machine_composition import source,operation_cost
from blockwire.machine_crafting import crafting_report
from blockwire.skills.core import run_skill
from test_machine_profile import MachineNative
from test_crafting import CraftNative

EMPTY={'item':None,'count':0}
def stack(item,n):return {'item':'minecraft:'+item,'count':n} if n else dict(EMPTY)
def check(slot,item=None,n=0):return {'slot':slot,**stack(item,n)}
def step(slot,before,after,carried_before,carried_after,button=0):
    return dict(slot=slot,button=button,before=before,after=after,carried_before=carried_before,carried_after=carried_after)
def planks_steps():
    return [
        step(36,[check(36,'oak_log',2)],[check(36)],EMPTY,stack('oak_log',2)),
        step(1,[check(1)],[check(1,'oak_log',1),check(0,'oak_planks',4)],stack('oak_log',2),stack('oak_log',1),1),
        step(36,[check(36)],[check(36,'oak_log',1)],stack('oak_log',1),EMPTY),
        step(0,[check(0,'oak_planks',4),check(1,'oak_log',1)],[check(0),check(1)],EMPTY,stack('oak_planks',4)),
        step(37,[check(37)],[check(37,'oak_planks',4)],stack('oak_planks',4),EMPTY),
    ]

class MenuNative(CraftNative):
    def __init__(self):super().__init__();self.open=True;self.motion=MachineNative()
    def call(self,op,**q):
        if op=='motion_trace':return self.motion.call({'op':op,**q})
        if op=='click_slot' and q['slot']==0 and not self.receipts_only:
            assert q['state_id']==self.state and q['actor_session']==self.session
            assert self.carried is None
            self.calls.append((op,q));self.clicks+=1
            self.carried=self.result();self.grid.clear();self.state+=1;self.after_click()
            return {'submitted':True}
        return super().call(op,**q)
    def player(self):return Player(CallableBackend(lambda q:self.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))

class ManipulationContracts(unittest.TestCase):
    def test_explicit_slot_program_observes_native_shaped_output_and_consumption(self):
        native=MenuNative()
        result=run_skill(action_registry(),native.player(),'slot_program',{'menu_id':0,'steps':planks_steps()})
        self.assertEqual(result.status,'succeeded',result)
        self.assertEqual(native.items,{0:('minecraft:oak_log',1),1:('minecraft:oak_planks',4)})
        self.assertIsNone(native.carried);self.assertEqual(native.grid,{})
        self.assertEqual(native.clicks,5)
        self.assertEqual([q['state_id'] for op,q in native.calls if op=='click_slot'],list(range(5)))
        self.assertTrue(native.open)  # No hidden close or recovery.

    def test_receipts_cannot_authorize_tail_or_retry(self):
        native=MenuNative();native.receipts_only=True
        result=run_skill(action_registry(),native.player(),'slot_program',{'menu_id':0,'steps':planks_steps()})
        self.assertEqual(result.reason,'inventory_effect_not_observed')
        self.assertEqual(native.clicks,1)

    def test_precondition_failure_has_no_click_and_partial_cursor_is_not_closed(self):
        native=MenuNative();native.items={0:('minecraft:oak_log',1)}
        result=run_skill(action_registry(),native.player(),'slot_program',{'menu_id':0,'steps':planks_steps()})
        self.assertEqual(result.reason,'inventory_precondition_changed');self.assertEqual(native.clicks,0)
        native.carried=('minecraft:oak_log',1)
        result=run_skill(action_registry(),native.player(),'inventory_screen',{'opened':False})
        self.assertEqual(result.reason,'cursor_requires_recovery');self.assertTrue(native.open)

    def test_phases_retain_common_key_with_short_leases_and_one_press(self):
        native=MachineNative();held_at_press=[]
        def call(q):
            if q['op']=='action':held_at_press.append(native.held[:])
            return native.call(q)
        result=run_skill(action_registry(),Player(CallableBackend(call)),'input_sequence',{'phases':[
            {'buttons':['sneak'],'seconds':.2},
            {'buttons':['sneak'],'seconds':.2,'look':{'yaw':90.,'pitch':0.}},
            {'buttons':['sneak'],'seconds':.3,'press':'use'}]})
        self.assertEqual(result.status,'succeeded',result)
        self.assertEqual(held_at_press,[['sneak']])
        self.assertEqual(native.yaw,90.)
        drives=[q for q in native.calls if q['op']=='drive']
        self.assertTrue(all(q['ticks']==6 and q['actor_session']=='actor-a' for q in drives))
        first_stop=next(i for i,q in enumerate(native.calls) if q['op']=='stop')
        self.assertFalse(any(q['op']=='drive' for q in native.calls[first_stop:]))

    def test_aim_geometry_and_failed_rotation_do_not_choose_or_use_targets(self):
        native=MachineNative()
        def call(q):
            result=native.call(q)
            if q['op']=='observe':result['eye_position']=[0.,65.,0.]
            return result
        result=run_skill(action_registry(),Player(CallableBackend(call)),'turn',{'point':[1.,65.,0.]})
        self.assertEqual(result.status,'succeeded');self.assertEqual(native.yaw,-90.)
        native=MachineNative()
        def stalled(q):
            if q['op']=='look':native.calls.append(q);return {'submitted':True}
            return native.call(q)
        result=run_skill(action_registry(),Player(CallableBackend(stalled)),'input_sequence',{'phases':[
            {'buttons':['sneak'],'seconds':.1,'look':{'yaw':90.,'pitch':0.}},
            {'buttons':['sneak'],'seconds':.1,'press':'use'}]})
        self.assertEqual(result.reason,'rotation_not_observed')
        self.assertFalse(any(q['op']=='action' for q in native.calls))

    def test_target_and_actor_change_prevent_press(self):
        for replace in (False,True):
            native=MachineNative()
            def call(q):
                result=native.call(q)
                if replace and q['op']=='drive':native.actor='changed'
                return result
            phases=[{'buttons':['sneak'],'seconds':.1},{'buttons':['sneak'],'seconds':.1,'press':'use'}]
            if not replace:phases[0]['target']={'block':'minecraft:oak_log','position':[0,64,0],'face':'up'}
            result=run_skill(action_registry(),Player(CallableBackend(call)),'input_sequence',{'phases':phases})
            self.assertEqual(result.reason,'actor_session_changed' if replace else 'target_changed')
            self.assertFalse(any(q['op']=='action' for q in native.calls))

    def test_provider_exposes_primitives_and_data_notes_not_macro_goals(self):
        from unittest.mock import patch
        from blockwire.tool_decider import OpenAIToolDecider
        from test_tool_decider import reply
        registry=action_registry()
        model=OpenAIToolDecider('http://127.0.0.1:11434/v1/chat/completions','fixture',registry=registry,
            allowed_skills=set(registry._definitions),control_tools=True,composition_tools=True)
        with patch.object(model,'_request',return_value=reply('remember_plan','{"notes":"my own blueprint"}')) as request:
            self.assertEqual(model.decide({}),{'kind':'plan','notes':'my own blueprint'})
            payload=request.call_args.args[0]
            names={t['function']['name'] for t in payload['tools']}
            self.assertTrue({'slot_program','input_sequence','remember_plan'}<=names)
            self.assertFalse({'gather_wood','craft_item','build_house'} & names)
            self.assertEqual(payload['max_tokens'],4096)

    def test_schema_compiler_budget_and_reference_are_bounded(self):
        actions=[{'name':'input_sequence','parameters':{'phases':[{'buttons':['sneak'],'seconds':.2},{'buttons':['sneak'],'seconds':.1,'press':'use'}]}},
                 {'name':'slot_program','parameters':{'menu_id':0,'steps':planks_steps()}}]
        self.assertIn('G3',source(actions));self.assertIn('M6',source(actions))
        self.assertEqual(sum(operation_cost(a['name'],a['parameters']) for a in actions),8)
        invalid=[{'phases':[{'buttons':['attack'],'seconds':30.},{'buttons':[],'seconds':.1}]},
                 {'phases':[{'buttons':['use'],'seconds':.1,'press':'use'}]},
                 {'phases':[{'buttons':['left','right'],'seconds':.1}]}]
        for args in invalid:
            with self.assertRaises(ValueError):action_registry().prepare('input_sequence',args)
        bad=copy.deepcopy(planks_steps());bad[0]['after']=bad[0]['before'];bad[0]['carried_after']=bad[0]['carried_before']
        with self.assertRaises(ValueError):action_registry().prepare('slot_program',{'menu_id':0,'steps':bad})
        report=crafting_report(MenuNative().call('inventory'))
        self.assertEqual(report['grid_slots'],[1,2,3,4])
        self.assertTrue(report['native_result_is_authoritative']);self.assertFalse(report['recipe_catalog_complete'])
        self.assertLess(len(json.dumps(report).encode()),30000)
        self.assertIn('minecraft:oak_door',{r['output'] for r in report['recipes']})

if __name__=='__main__':unittest.main()
