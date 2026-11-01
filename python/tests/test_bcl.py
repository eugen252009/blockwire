"""Offline grammar/contracts and simulated runtime integration, NOT Minecraft evidence."""
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pydantic import TypeAdapter
from blockwire import Player,CallableBackend
from blockwire.bcl import *
from blockwire.bcl.compiler import arguments,registry_digest
from blockwire.bcl.runtime import BCLRunner,reachable_height
from blockwire.skills import default_registry,SkillDefinition,SkillParameters,SkillResult
from test_agent import Native,registry as fixture_skills


class ParserContracts(unittest.TestCase):
    def setUp(self):self.r=default_commands()
    def test_BC01_equivalent_syntax_normalizes_to_same_operation(self):
        variants=['M0 120 64 30 fast','M0 X120 Y64 Z30 Ffast','M0 X=120 Y=64 Z=30 F=fast','M0 120 64 30 Ffast']
        rows=[compile_bcl(s,self.r).operations[0] for s in variants]
        self.assertTrue(all(x.bindings==rows[0].bindings for x in rows))
        for s in ['M0 120 64 30','M0 X120 Z30','M0 X120 Z30 Ffast','M0 X=120 Z=30 F=fast','M0 -120 64.5 30 sneak']:
            self.assertEqual(len(compile_bcl(s,self.r).operations),1)
    def test_BC02_missing_and_explicit_null_are_distinct(self):
        a=compile_bcl('M1',self.r).operations[0];b=compile_bcl('M1 Pnull',self.r).operations[0]
        self.assertFalse(a.bindings[1].supplied);self.assertTrue(b.bindings[1].supplied)
        self.assertIsNone(b.to_dict()['bindings'][1]['value'])
        self.assertFalse(compile_bcl('M0 X120 Z30',self.r).operations[0].bindings[1].supplied)
        with self.assertRaises(BCLError):compile_bcl('M0 Ynull',self.r)
    def test_BC03_structured_errors_and_source_locations(self):
        cases={'M000':'UNKNOWN_COMMAND','Q0':'UNKNOWN_COMMAND','create:M0':'UNKNOWN_NAMESPACE','M9':'UNKNOWN_COMMAND',
            'M0 Q1':'UNKNOWN_PARAMETER','M0 1 X2':'DUPLICATE_ARGUMENT','M0 X1 2':'DUPLICATE_ARGUMENT',
            'M0 1 2 3 fast 4':'INVALID_ARGUMENT','M0 Fwarp':'INVALID_ENUM_VALUE','C0':'MISSING_REQUIRED_ARGUMENT',
            'M0 X1.2.3':'INVALID_ARGUMENT','M0 XNaN':'INVALID_ARGUMENT','M0 X1e999':'INVALID_ARGUMENT',
            'M0 Xtrue':'INVALID_ARGUMENT','M0 X30000000':'INVALID_ARGUMENT','M0 F':'INVALID_ENUM_VALUE',
            'M0 "unterminated':'INVALID_STRING','M0 X="12"':'INVALID_ARGUMENT','M0 F="fast"x':'INVALID_STRING',
            'S0 "agent.display_name" "Builder One"':'INVALID_ENUM_VALUE','BCL/2\nI0':'UNSUPPORTED_VERSION'}
        for source,code in cases.items():
            with self.subTest(source=source):
                r=compile_report(source,self.r);self.assertFalse(r['ok']);self.assertEqual(r['diagnostics'][0]['code'],code,r)
                self.assertGreaterEqual(r['diagnostics'][0]['column'],1)
        self.assertEqual(compile_report('I0\nM0 Q1',self.r)['diagnostics'][0]['line'],2)
    def test_BC04_bounds_whitespace_comments_and_versions(self):
        p=compile_bcl(' # note\nBCL/1\n\tM0\t-120 64.5 30 sneak ;comment\n\nI0\r\n',self.r)
        self.assertEqual(len(p.operations),2)
        for text in ['','I0\n'*33,' '*16385,'I0\nBCL/1','I0','M0 ' + '1 '*34]:
            report=compile_report(text,self.r,version='BCL/9' if text=='I0' else 'BCL/1')
            self.assertFalse(report['ok'])
    def test_BC05_permissions_checked_for_entire_program(self):
        r=compile_report('I0\nM0 1 64 2',self.r,permissions={'observe'})
        self.assertEqual(r['diagnostics'][0]['code'],'PERMISSION_DENIED')
    def test_BC06_namespaces_conflicts_and_resource_ids(self):
        self.r.namespace('create')
        c=Command('create','C0','crafting.item','Alias to installed existing skill.',self.r.resolve('core','C0').parameters,'craft_item',frozenset({'crafting'}))
        self.r.register(c)
        self.assertEqual(compile_bcl('create:C0 create:shaft 1',self.r).operations[0].namespace,'create')
        for invalid in [c,replace(c,namespace='core'),replace(c,namespace='core',opcode='S9',name='settings.extra'),replace(c,language='BCL/2')]:
            with self.assertRaises(ValueError):self.r.register(invalid)
        self.assertEqual(compile_report('C0 bad:item:extra 1',self.r)['diagnostics'][0]['code'],'INVALID_ARGUMENT')
    def test_BC07_strings_boolean_integer_positions_and_escaping(self):
        # Trusted extension uses an existing fixture skill model: ordinary data, never evaluated.
        class P(SkillParameters):
            key:str;value:str
        self.r.skills.register(SkillDefinition('labels','fixture',P,lambda *_:None,False))
        self.r.namespace('labels')
        self.r.register(Command('labels','S0','settings.label','fixture',(
            Parameter('K','key','string',TypeAdapter(str)),Parameter('V','value','string',TypeAdapter(str))),
            'labels',frozenset({'observe'})))
        p=compile_bcl('labels:S0 "agent.display_name" "Builder One\\n\\\"Two\\\""',self.r)
        values=arguments(p.operations[0],self.r.resolve('labels','S0'))
        self.assertEqual(values['value'],'Builder One\n"Two"')
        for s in ['M1 P[1,64,3] Etrue','M1 P="[1, 64, 3]" E=false','C0 minecraft:oak_planks 16','C0 I=minecraft:oak_planks N16']:
            self.assertTrue(compile_report(s,self.r)['ok'],s)
        for s in ['M1 E1','M1 ETrue','C0 minecraft:oak_planks 1.5','C0 minecraft:oak_planks true','M1 P[1,2]']:
            self.assertFalse(compile_report(s,self.r)['ok'],s)
    def test_BC09_generated_reference_matches_registry_and_core_opcode_identities_are_stable(self):
        document=json.loads((Path(__file__).resolve().parents[2]/'docs/bcl-commands.json').read_text())
        definitions=[self.r.describe(('' if c.namespace=='core' else c.namespace+':')+c.opcode) for c in self.r._commands.values()]
        self.assertEqual(document,{'language':'BCL/1','commands':definitions,'events':self.r.events})
        self.assertEqual({c.opcode:c.name for c in self.r._commands.values() if c.category=='setting'},
                         {'S0':'execution_mode','S1':'coordinate_mode','S2':'movement_mode','S3':'error_mode','S4':'timeout_seconds'})
        self.assertNotIn(('core','S6'),self.r._commands)

    def test_BC08_discovery_is_capabilities_not_mechanics_and_schema_is_shared(self):
        rows=self.r.discover('movement');self.assertTrue(any(r['opcode']=='M0' for r in rows))
        self.assertTrue(all('parameters' not in r for r in rows))
        d=self.r.describe('C0');self.assertEqual(d['parameters'][1]['schema']['maximum'],16)
        self.assertTrue(self.r.describe('S0')['available'])


class RuntimeContracts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.native=Native();self.player=Player(CallableBackend(self.native.call))
        skills=default_registry()
        for definition in fixture_skills()._definitions.values():skills.register(definition)
        self.r=default_commands(skills);self.r.namespace('test')
        for code,skill in [('I0','effect'),('I1','missing')]:
            self.r.register(Command('test',code,'fixture.'+skill,'fixture',(),skill,frozenset({'inventory'})))
        self.identity={'agent_id':'bcl','world_id':'fixture','player_id':'player-a'}
    def runner(self,source,**kw):
        return BCLRunner(source,self.r,self.player,Path(self.tmp.name)/'session.sqlite',self.identity,'actor-a',**kw)
    def test_BR01_dispatch_sequential_verification_and_shared_cleanup(self):
        r=self.runner('test:I0\nI0\ntest:I0').run()
        self.assertEqual(r['status'],'succeeded',r);self.assertEqual(len(r['operations']),3)
        self.assertTrue(r['program_verified']);self.assertFalse(r['objective_verified'])
        self.assertIn('NOT the external',r['verification_scope'])
        self.assertEqual(sum(q['op']=='action' for q in self.native.calls),2)
        self.assertEqual(r['cleanup'],'released');self.assertFalse(r['rollback_performed'])
    def test_BR02_late_compile_error_has_no_observation_effect_or_state_file(self):
        with self.assertRaises(BCLError):self.runner('test:I0\nM0 Q1')
        self.assertEqual(self.native.calls,[]);self.assertFalse((Path(self.tmp.name)/'session.sqlite').exists())
    def test_BR03_first_failed_postcondition_stops_batch(self):
        r=self.runner('test:I0\ntest:I1\ntest:I0').run()
        self.assertNotEqual(r['status'],'succeeded');self.assertEqual(sum(q['op']=='action' for q in self.native.calls),1)
        self.assertEqual(r['operations'][-1]['reason'],'missing_materials')
    def test_BR04_expected_actor_and_player_identity_are_checked_before_foreign_cleanup(self):
        self.native.actor='wrong'
        r=self.runner('test:I0').run();self.assertEqual(r['diagnostics'][0]['code'],'ACTOR_MISMATCH')
        self.assertEqual([q['op'] for q in self.native.calls],['observe'])
    def test_BR05_reused_execution_state_is_never_replayed(self):
        self.assertEqual(self.runner('test:I0').run()['status'],'succeeded')
        before=sum(q['op']=='action' for q in self.native.calls)
        r=self.runner('test:I0').run()
        self.assertEqual(r['diagnostics'][0]['code'],'INTERRUPTED_SESSION')
        self.assertEqual(sum(q['op']=='action' for q in self.native.calls),before)
    def test_BR06_cancellation_and_timeout_are_terminal(self):
        runner=self.runner('test:I0');runner.cancel();r=runner.run()
        self.assertEqual(r['diagnostics'][0]['code'],'EXECUTION_CANCELLED')
        self.assertFalse(any(q['op']=='action' for q in self.native.calls))
        class P(SkillParameters):pass
        self.r.skills.register(SkillDefinition('waiting','fixture',P,lambda c,g:(c.pause(1.),None)[1]))
        self.r.register(Command('test','I2','fixture.wait','fixture',(),'waiting',frozenset({'inventory'})))
        r=BCLRunner('test:I2',self.r,self.player,Path(self.tmp.name)/'other.sqlite',self.identity,'actor-a',duration_seconds=.15).run()
        self.assertEqual(r['diagnostics'][0]['code'],'EXECUTION_TIMEOUT',r)
    def test_BR07_registry_revision_invalidates_compiled_program(self):
        runner=self.runner('test:I0');self.r.namespace('later')
        r=runner.run();self.assertEqual(r['diagnostics'][0]['code'],'UNSUPPORTED_VERSION')
        self.assertFalse(any(q['op']=='action' for q in self.native.calls))
    def test_BR08_actor_replacement_between_operations_is_not_rebound(self):
        self.native.before_action=lambda:setattr(self.native,'actor','new')
        r=self.runner('test:I0\ntest:I0').run()
        self.assertNotEqual(r['status'],'succeeded')
        self.assertEqual(sum(q['op']=='action' for q in self.native.calls),1)
    def test_BR11_unsupported_file_lock_platform_fails_before_native_or_state_effects(self):
        from unittest.mock import patch
        with patch('blockwire.agent.fcntl',None):
            self.assertTrue(compile_report('M0 X1 Z1',self.r)['ok'])
            with self.assertRaisesRegex(RuntimeError,'POSIX'):
                self.runner('test:I0')
        self.assertEqual(self.native.calls,[])
        self.assertFalse((Path(self.tmp.name)/'session.sqlite').exists())

    def test_BR10_discarded_stale_decision_is_not_acknowledged_as_executed(self):
        from types import SimpleNamespace
        from blockwire.bcl.runtime import BatchDriver
        p=compile_bcl('test:I0\ntest:I0',self.r);d=BatchDriver(p,self.r)
        d.runtime=SimpleNamespace(state={},store=SimpleNamespace(save=lambda _:None),_publish=lambda **_:None)
        context={'completed_actions':{},'history':[],'observation':{'position':[.5,64.,.5]}}
        self.assertEqual(d.decide(context)['kind'],'act')
        self.assertEqual(d.decide(context)['kind'],'act')
        self.assertEqual(d.index,0)
        context.update(completed_actions={'effect':1},history=[{'status':'succeeded','reason':'verified'}])
        self.assertEqual(d.decide(context)['kind'],'act');self.assertEqual(d.index,1)

    def test_BR09_auto_height_uses_only_safe_connected_cells_not_highest_surface(self):
        nav={'profile':'stepped_full_blocks_v1','ready':True,'current_cell':[0,64,0],'current_center_access':True,
             'cells':[{'position':p,'hazards':h} for p,h in [([0,64,0],[]),([1,64,0],[]),([1,65,0],[]),([2,64,0],['lava'])]],'edges':[[0,1],[0,3]]}
        o={'position':[.5,64.,.5],'navigation':nav}
        self.assertEqual(reachable_height(o,1.5,.5),64.)
        for x in (2.5,100.):
            with self.assertRaises(ValueError):reachable_height(o,x,.5)


if __name__=='__main__':unittest.main()
