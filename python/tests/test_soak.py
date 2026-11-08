"""Soak prerequisites: strict model/host boundary, not autonomous Minecraft acceptance."""
import asyncio,json,struct,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import AsyncMock
from blockwire.soak import (prepare_decision,dispatch_decision,NoCommandBudget,UnknownNoRetry,
    SessionLifecycle,FINALIZATION_PROOFS,REQUIRED_GATES,campaign_blockers,require_campaign_ready,verify_replay)
from blockwire.bcl import default_commands,compile_bcl,BCLError
import test_bcl_websocket as fixture

class Decisions(unittest.IsolatedAsyncioTestCase):
    def setUp(self):self.registry=default_commands();self.client=AsyncMock();self.checks=0
    def check(self):self.checks+=1
    async def test_SK01_empty_whitespace_comments_headers_do_not_schedule(self):
        for source in ['', ' \t\r\n', '# Just observing\n; no commands', 'BCL/1\n# observation']:
            p=prepare_decision({'source':source,'note':'Observing','memory':{'blocked':True}},self.registry)
            self.assertEqual(p.operation_count,0);r=await dispatch_decision(p,self.client,feedback_id='empty',check=self.check)
            self.assertFalse(r['bcl_submitted']);self.assertFalse(r['gameplay_verified']);self.assertEqual(r['kind'],'observation_only')
        self.client.send.assert_not_called();self.client.wait.assert_not_called();self.client.cancel.assert_not_called();self.client.request_feature.assert_not_called()
    async def test_SK02_finish_feedback_without_bcl_is_not_lost(self):
        self.client.request_feature.return_value={'status':'recorded','result':{'status':'pending_review'}}
        p=prepare_decision({'source':'','finish':True,'feedback':{'title':'Gap','description':'Observed limitation'}},self.registry)
        result=await dispatch_decision(p,self.client,feedback_id='last-proposal',check=self.check)
        self.assertEqual(result['kind'],'finish_unverified');self.assertTrue(result['finish_proposed']);self.assertFalse(result['gameplay_verified'])
        self.client.request_feature.assert_awaited_once();self.client.send.assert_not_called()
    async def test_SK03_malformed_full_decision_has_no_effects(self):
        for source in ['Reasoning: I should gather wood','INVALID','S2 sneak\nM0 Q1','BCL/2','BCL/1\nM00']:
            with self.assertRaises(BCLError):prepare_decision({'source':source,'feedback':{'title':'Not yet','description':'Must not be sent'}},self.registry)
        self.client.send.assert_not_called();self.client.request_feature.assert_not_called()
    async def test_SK04_reasoning_only_is_distinct_from_malformed_json(self):
        p=prepare_decision({'note':'No supported action available','memory':{'observation':'hypothesis'}},self.registry)
        self.assertEqual(p.kind,'observation_only')
        for raw in ['I am thinking', '{} trailing', '{"source":null}', '{"source":true}', '{"unknown":1}']:
            with self.assertRaises(ValueError):prepare_decision(raw,self.registry)
    async def test_SK05_valid_multicommand_uses_existing_compiler_and_one_submission(self):
        source='S2 sneak\nV0\nI0';p=prepare_decision({'source':source},self.registry)
        self.assertEqual(p.program,compile_bcl(source,self.registry));self.client.send.return_value={'status':'completed','result':{'program_verified':True}}
        r=await dispatch_decision(p,self.client,feedback_id='valid',check=self.check)
        self.client.send.assert_awaited_once_with(source);self.assertTrue(r['program_verified']);self.assertFalse(r['gameplay_verified'])
    async def test_SK06_empty_never_becomes_valid_bcl_syntax(self):
        for source in ['', ' \n', '# no op']:
            with self.assertRaises(BCLError) as error:compile_bcl(source,self.registry)
            self.assertEqual(error.exception.diagnostic.code,'EMPTY_PROGRAM')
    async def test_SK07_no_command_loop_budget_includes_feedback(self):
        limiter=NoCommandBudget(2);p=prepare_decision({'feedback':{'title':'Gap','description':'Not progress'}},self.registry)
        self.assertFalse(limiter.accept(p));self.assertTrue(limiter.accept(p));self.assertEqual(limiter.consecutive,2)
        limiter.accept(prepare_decision({'source':'I0'},self.registry));self.assertEqual(limiter.consecutive,0)
    async def test_SK08_check_precedes_every_effect_and_deadline_prevents_submission(self):
        p=prepare_decision({'source':'I0'},self.registry)
        def stopped():raise ValueError('deadline')
        with self.assertRaises(ValueError):await dispatch_decision(p,self.client,feedback_id='stopped',check=stopped)
        self.client.send.assert_not_called()
    async def test_SK09_lost_receipt_is_unknown_without_retry(self):
        self.client.send.side_effect=ConnectionError('lost acknowledgement');p=prepare_decision({'source':'I0'},self.registry)
        with self.assertRaises(UnknownNoRetry):await dispatch_decision(p,self.client,feedback_id='lost',check=self.check)
        self.client.send.assert_awaited_once();self.client.cancel.assert_not_called()
    async def test_SK10_cancel_known_task_uses_same_owned_task_once(self):
        self.client.send.return_value={'status':'accepted','task_id':'owned'};self.client.wait.side_effect=[asyncio.CancelledError(),{'status':'cancelled'}]
        with self.assertRaises(asyncio.CancelledError):await dispatch_decision(prepare_decision({'source':'I0'},self.registry),self.client,feedback_id='cancel',check=self.check)
        self.client.cancel.assert_awaited_once_with('owned');self.assertEqual(self.client.send.await_count,1)
    async def test_SK11_uncertain_cancel_never_claims_cleanup(self):
        self.client.send.return_value={'status':'accepted','task_id':'owned'};self.client.wait.side_effect=asyncio.CancelledError();self.client.cancel.side_effect=ConnectionError('lost')
        with self.assertRaises(UnknownNoRetry):await dispatch_decision(prepare_decision({'source':'I0'},self.registry),self.client,feedback_id='cancel',check=self.check)
        self.assertEqual(self.client.send.await_count,1)
    async def test_SK12_submission_interrupted_before_ack_is_unknown(self):
        self.client.send.side_effect=asyncio.CancelledError()
        with self.assertRaises(UnknownNoRetry):await dispatch_decision(prepare_decision({'source':'I0'},self.registry),self.client,feedback_id='inflight',check=self.check)
    async def test_SK13_frame_memory_and_chat_validated_before_effects(self):
        for raw in [{'source':'I0\nI0'},{'memory':{'large':'x'*8193}},{'chat':'/op'},{'chat':'bad\nline'}]:
            with self.assertRaises(ValueError):prepare_decision(raw,self.registry,max_operations=1)
        self.client.send.assert_not_called()
    async def test_SK14_explicit_transport_fault_is_not_recoverable_gameplay(self):
        self.client.send.return_value={'status':'failed','diagnostics':[{'code':'transport.disconnected'}]}
        with self.assertRaises(UnknownNoRetry):await dispatch_decision(prepare_decision({'source':'I0'},self.registry),self.client,feedback_id='fault',check=self.check)

class Lifecycle(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
    def journal(self):return SessionLifecycle(self.root/'state.json',{'agent_id':'a','world_id':'w','player_id':'p'})
    def finalizing(self,j):
        for state in ['PREPARING','RUNNING','STOPPING','FINALIZING']:j.transition(state)
    def test_SK15_complete_requires_all_independent_artifacts(self):
        j=self.journal();self.finalizing(j)
        with self.assertRaises(ValueError):j.transition('COMPLETED',proofs={'processes_gone':True})
        proofs={k:True for k in FINALIZATION_PROOFS};j.transition('COMPLETED',proofs=proofs);self.assertFalse(j.value['goal_verified']);self.assertFalse(j.transition('COMPLETED',proofs=proofs))
    def test_SK16_unknown_is_sticky_and_never_continuable_completion(self):
        j=self.journal();j.transition('PREPARING');j.transition('RUNNING');j.transition('STOPPING');j.transition('STOPPING',unknown=True);j.transition('FINALIZING')
        with self.assertRaises(ValueError):j.transition('COMPLETED',proofs={k:True for k in FINALIZATION_PROOFS})
        j.transition('BLOCKED');self.assertTrue(j.value['unknown'])
    def test_SK17_memory_durable_and_existing_session_not_implicitly_resumed(self):
        j=self.journal();j.save_memory({'objective':'Observe fresh state'});stored=json.loads(j.path.read_text());self.assertEqual(stored['memory'],{'objective':'Observe fresh state'});self.assertEqual(j.path.stat().st_mode&0o777,0o600)
        with self.assertRaises(ValueError):self.journal()
    def test_SK18_skipped_lifecycle_and_missing_gates_block(self):
        j=self.journal()
        with self.assertRaises(ValueError):j.transition('RUNNING')
        checks={k:'PASS' for k in REQUIRED_GATES};checks['replay_finalization']='NOT_RUN'
        self.assertEqual(campaign_blockers(checks),['replay_finalization'])
        with self.assertRaises(RuntimeError):require_campaign_ready(checks)
        checks['replay_finalization']='PASS';require_campaign_ready(checks)
    def test_SK19_partial_replay_is_not_finalization(self):
        p=self.root/'partial.mcpr.tmp';p.write_bytes(b'partial')
        with self.assertRaises(ValueError):verify_replay(p)
    def test_SK20_replay_integrity_not_viewer_or_just_zip(self):
        p=self.root/'sample.mcpr'
        with zipfile.ZipFile(p,'w') as z:z.writestr('metaData.json','{}');z.writestr('recording.tmcpr',struct.pack('>ii',0,1)+b'X')
        result=verify_replay(p);self.assertEqual(result['integrity'],'PASS');self.assertEqual(result['viewer_playback'],'NOT_RUN')
        with zipfile.ZipFile(p,'w') as z:z.writestr('metaData.json','{}');z.writestr('recording.tmcpr',b'bad')
        with self.assertRaises(ValueError):verify_replay(p)

class GatewayBoundary(unittest.IsolatedAsyncioTestCase):
    client=fixture.WebSocketContracts.client;disconnected=fixture.WebSocketContracts.disconnected
    asyncSetUp=fixture.WebSocketContracts.asyncSetUp;asyncTearDown=fixture.WebSocketContracts.asyncTearDown
    async def test_SK21_real_tls_no_command_does_not_create_job_or_change_modal(self):
        async with self.client() as c:
            session=self.gateway.jobs.sessions['session'];before=list(self.native.calls);modal=session.modal.to_dict()
            r=await dispatch_decision(prepare_decision({'source':' \n','note':'Observe only'},self.registry),c,feedback_id='idle',check=lambda:None)
            self.assertFalse(r['bcl_submitted']);self.assertEqual(self.gateway.jobs.jobs,{})
            self.assertEqual(session.modal.to_dict(),modal);self.assertEqual(self.native.calls,before)
    async def test_SK22_direct_empty_gateway_frame_still_explicit_error(self):
        async with self.client() as c:
            r=await c.send(' \n');self.assertEqual(r['status'],'failed');self.assertEqual(r['diagnostics'][0]['code'],'EMPTY_PROGRAM')
            self.assertEqual(self.gateway.jobs.jobs,{})

if __name__=='__main__':unittest.main()
