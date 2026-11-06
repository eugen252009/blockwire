#!/usr/bin/env python3
"""Isolated targeted-search mutations. No game/model connection; no source edits in place."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ.get('BLOCKWIRE_VERIFICATION_DIR',ROOT/'build/search/checks'))/'mutations'
PYTHON=[
 ('ordinary_mcp_schema','mcp_server.py',"set_tool_parameters(server, 'search', Search)",'pass # lost strict MCP model','SearchContracts.test_cli_and_mcp_thin_dispatch'),
 ('machine_mcp_schema','machine_mcp.py',"set_tool_parameters(server, 'search', Search)",'pass # lost strict MCP model','SearchWire.test_real_tls_mcp_search_is_not_an_action_and_schema_is_strict'),
 ('async_rpc_bound','mcp_server.py','return await asyncio.shield(search_rpc)','return await search_rpc','SearchAsync.test_ordinary_mcp_deadline_retains_single_inflight_read'),
 ('async_audit','mcp_server.py','if inspect.isawaitable(result):','if False:','SearchAsync.test_async_feedback_audits_completion_not_coroutine_creation'),
 ('ownership','skills/search.py','controls_player=False','controls_player=True','SearchContracts.test_additional_reads_dedup_and_no_ownership_or_actions'),
 ('actor','skills/search.py','r.actor_session != self.actor','False','SearchContracts.test_actor_pose_query_sequence_and_output_validation'),
 ('view','skills/search.py','r.view_id != self.view or pose != self.pose','False','SearchContracts.test_actor_pose_query_sequence_and_output_validation'),
 ('page_sequence','skills/search.py','r.next_page != expected_next','False','SearchContracts.test_actor_pose_query_sequence_and_output_validation'),
 ('identity','skills/search.py',"hit.id in LOGS if self.goal.target == 'logs' else hit.id == self.goal.target",'True','SearchContracts.test_actor_pose_query_sequence_and_output_validation'),
 ('cone','skills/search.py','math.cos(math.radians(self.goal.cone_degrees/2)) - 1e-6','-1.','SearchContracts.test_coherent_hit_outside_cone_or_range_is_rejected'),
 ('range','skills/search.py','distance > self.goal.range+.001','False','SearchContracts.test_coherent_hit_outside_cone_or_range_is_rejected'),
 ('pre_dispatch_cancel','skills/search.py','context.check(); scene = context.player.observe(); context.check()','scene = context.player.observe(); context.check()','SearchContracts.test_cancel_deadline_and_no_replay_after_native_rejection'),
 ('interrupt_generation','bcl/search.py','self.closing or generation != self.machine.generation','False','SearchWire.test_interrupt_does_not_wait_for_search_and_discards_old_page'),
 ('permission','bcl/search.py',"if 'observe' not in g.jobs.permissions:",'if False:','SearchWire.test_observer_and_permission_fence'),
 ('inflight_bound','bcl/search.py','if g.search_busy:','if False:','SearchWire.test_concurrent_search_page_is_rejected_before_native_dispatch'),
 ('agent_budget','machine_agent.py','if operations+search_pages+PAGES>max_actions:','if False:','SearchWire.test_search_budget_rejection_prevents_native_reads'),
]
NATIVE=[
 ('dense_grid','SearchView.java','SIDE=65','SIDE=21','SEARCH_dense_grid_budget'),
 ('ray_budget','SearchView.java','PAGE_SIZE=128','PAGE_SIZE=256','SEARCH_ray_budget'),
 ('cone','SearchView.java','if(direction.dot(forward)<cosine-1e-12)continue;','if(false)continue;','SEARCH_cone_and_behind_excluded'),
 ('range','SearchView.java','eye.add(direction.scale(request.range))','eye.add(direction.scale(64))','SEARCH_short_range_excludes_target'),
 ('view','SearchView.java','if(request.view!=null && !request.view.equals(view))','if(false)','SEARCH_pose_fence'),
 ('result_cap','SearchView.java','MAX_MATCHES=32','MAX_MATCHES=64','SEARCH_result_cap'),
 ('unloaded_opaque','VisibilityView.java','source.loaded(pos)?source.getBlockState(pos):Blocks.BARRIER.defaultBlockState()',
    'source.loaded(pos)?source.getBlockState(pos):Blocks.AIR.defaultBlockState()','SEARCH_unknown_opaque'),
 ('dispatch_actor','Blockwire.java','var request=SearchView.request(q);guardedActor(q);playerRequired();','var request=SearchView.request(q);playerRequired();','SEARCH_dispatch_actor_guard'),
 ('dispatch_read_only','Blockwire.java','var request=SearchView.request(q);guardedActor(q);playerRequired();','var request=SearchView.request(q);guardedActor(q);playerRequired();release();','SEARCH_dispatch_read_only'),
]


def main():
    OUT.mkdir(parents=True,exist_ok=True);results=[]
    for language,cases in [('python',PYTHON),('native',NATIVE)]:
        for name,filename,before,after,test in cases:
            with tempfile.TemporaryDirectory(prefix='blockwire-search-mutation-')as directory:
                root=Path(directory)
                if language=='python':
                    shutil.copytree(ROOT/'python/src',root/'src',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
                    file=root/'src/blockwire'/filename
                    command=[sys.executable,'-m','unittest','test_search.'+test]
                    env={**os.environ,'PYTHONPATH':str(root/'src')+os.pathsep+str(ROOT/'python/tests')}
                else:
                    for f in ['build.gradle','settings.gradle','gradle.properties','gradlew','gradlew.bat','LICENSE']:shutil.copy2(ROOT/f,root/f)
                    for folder in ['gradle','src']:shutil.copytree(ROOT/folder,root/folder)
                    file=root/'src/main/java/dev/blockwire'/filename
                    command=['./gradlew','--console=plain','searchContractTest'];env=os.environ
                source=file.read_text();assert source.count(before)==1,(language,name)
                mutated=source.replace(before,after)
                if language=='python':compile(mutated,str(file),'exec')
                file.write_text(mutated)
                run=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True,timeout=120)
                output=run.stdout+run.stderr;(OUT/f'{language}-{name}.log').write_text(output)
                expected='FAIL: '+test.split('.')[-1] if language=='python' else 'AssertionError: '+test
                killed=run.returncode!=0 and expected in output and 'Compilation failed'not in output
                results.append({'language':language,'mutation':name,'status':'KILLED'if killed else'NOT_KILLED','test':test})
                print(language,name,results[-1]['status'],flush=True)
    (OUT/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    return not all(row['status']=='KILLED'for row in results)


if __name__=='__main__':sys.exit(main())
