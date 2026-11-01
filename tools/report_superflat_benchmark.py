"""Finalize existing benchmark evidence; no native connection or action replay."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from building.reference import House
from building.anvil import voxels
from building.snapshots import validate
from building.reference import verify
from building.audit import fixture_audit


def read(path):return json.loads(path.read_text()) if path.exists() else None
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=Path('build/superflat-benchmark'));args=parser.parse_args()
    root=args.root;house=House();runs=[];artifacts={};programs=[];model_programs=[];storage=[]
    for directory in sorted(p for p in root.iterdir() if p.is_dir() and re.fullmatch(r'[ABFR][0-9]{2}[-a-z0-9]*',p.name)):
        result=read(directory/'result.json');startup=read(directory/'startup-failure.json');disk=read(directory/'storage-failure.json')
        if result and 'metadata' in result:
            metadata=result['metadata'];row={'id':directory.name,'test':metadata['test'],'resume_from':metadata.get('resume_from'),'fault':metadata.get('fault'),
                'snapshot_identity':metadata['snapshot_identity'],'passed':bool(result['passed']),
                'llm_calls':result.get('llm_calls',0),'elapsed_seconds':result['elapsed_seconds'],
                'executed_skill_operations':result['executed_operations'],'failed_actions':result['failed_actions'],
                'placement_events':result.get('verified_native_placement_events'),
                'plan_revisions':result.get('plan_revisions',0),'feedback_conditioned_decisions':result.get('feedback_conditioned_decisions',0),
                'failure':None if not result.get('failure') else {k:v for k,v in result['failure'].items() if k not in {'result','source'}},
                'verification':{k:v for k,v in result['verification'].items() if k not in {'requirements','unexpected_or_unknown_cells'}},
                'fault_probe_passed':result.get('fault_probe_passed')}
            nav=result.get('native',{}).get('navigation',{});scene=result.get('native',{}).get('scene',{})
            row['native_final']={k:nav.get(k) for k in ('profile','ready','current_cell','current_center_access','on_ground')}
            row['native_final'].update(position=scene.get('position'),health=scene.get('health'),source_node_present=any(c.get('position')==nav.get('current_cell') for c in nav.get('cells',[])))
            if result.get('agent_result'):
                a=result['agent_result'];row['builder_terminal']={k:a.get(k) for k in ('status','reason','objective_verified')}
                row['builder_terminal']['counters']=a.get('project',{}).get('counters',{})
            row['model_configuration']=metadata.get('model')
            failure=result.get('failure') or {};failed_task=failure.get('result',{}).get('result',{})
            failed_ops=failed_task.get('operations',[])
            row.update(failed_frame_source=failure.get('source'),
                failed_operation=next((o for o in failed_ops if o.get('status')!='succeeded'),None),
                last_success_before_failure=next((o for o in reversed(failed_ops) if o.get('status')=='succeeded'),None),
                failure_diagnostics=failed_task.get('diagnostics',[]),
                observed_final_position=result.get('native',{}).get('scene',{}).get('position'))
            if (directory/'ended-world.manifest.json').exists():
                manifest=validate(directory/'ended-world')
                # Identical FINAL independent predicate for retained runs, without
                # rewriting their original terminal results or inventing native proof.
                replay=verify(house,voxels(directory/'ended-world',house.workspace()|house.floors()),native=result.get('native',{}))
                row['final_common_predicate']=replay['objective_verified'];row['ended_snapshot_identity']=manifest['identity']
            if metadata['test']=='B':
                for reply in sorted((directory/'model').glob('*-reply.json')):
                    decision=read(reply)
                    model_programs.append({'run':directory.name,'model_call':int(reply.name.split('-')[0]),
                        'source':decision.get('source',''),'note':decision.get('note',''),
                        'finish_proposed':decision.get('finish',False),'verification_requested':decision.get('begin_verification',False),
                        'plan_submitted':bool(decision.get('plan')),
                        'provenance':'Actual external tool-free CLI reply; not a supplied script. Execution/rejection recorded separately in exchanges.'})
                    artifacts[str(reply)]=sha(reply)
            admitted=0;events=[]
            for file in sorted(directory.glob('*-exchange.json')):
                try:event=read(file)
                except json.JSONDecodeError:storage.append({'artifact':str(file),'status':'retained_invalid_or_incomplete_JSON'});continue
                events.append(event)
                if metadata['test']=='B':
                    programs.append({'run':directory.name,'source':event['source'],'status':event['response'].get('status'),
                        'scope':'Audited exchanges including host observations and local compiler rejections; model-only sources are listed separately',
                        'phase':event['response'].get('phase','gateway'),
                        'diagnostics':event['response'].get('result',{}).get('diagnostics',event['response'].get('diagnostics',[]))})
            from blockwire.bcl import default_commands,compile_bcl
            reg=default_commands()
            for event in events:
                if event['response'].get('phase')=='compile':continue
                try:admitted+=len(compile_bcl(event['source'],reg).operations)
                except ValueError:pass  # Historical registry versions are retained, not reinterpreted as effects.
            row['submitted_valid_bcl_operations']=admitted;runs.append(row)
        elif result:
            runs.append({'id':directory.name,'test':'recovery_probe','passed':result.get('passed',False),
                'scope':result.get('scope'),'inventory_unchanged':result.get('inventory_unchanged'),
                'actor_replaced':result.get('actor_replaced'),'no_placement':result.get('no_placement'),
                'pending_cleared_without_replay':result.get('pending_cleared_without_replay')})
        elif startup or disk:runs.append({'id':directory.name,'test':'host_failure','passed':False,'scope':(startup or disk).get('scope','host storage failure'),'verification':{k:v for k,v in (startup or disk)['verification'].items() if k not in {'requirements','unexpected_or_unknown_cells'}}})
        for file in directory.iterdir():
            if file.is_file() and file.suffix in {'.json','.bcl'}:
                artifacts[str(file)]=sha(file)
                if file.suffix=='.json':
                    try:read(file)
                    except json.JSONDecodeError:
                        if not any(x['artifact']==str(file) for x in storage):storage.append({'artifact':str(file),'status':'retained_invalid_or_incomplete_JSON'})
    accepted=[r for r in runs if r['test']=='A' and not r.get('fault') and not r.get('resume_from') and r.get('passed') and r.get('final_common_predicate')]
    cohort=read(root/'qualification-cohort.json')
    cohort_ok=False
    if cohort:
        by_id={r['id']:r for r in accepted}
        cohort_ok=(len(cohort['ids'])>=3 and all(i in by_id and by_id[i]['snapshot_identity']==cohort['snapshot_identity'] for i in cohort['ids'])
                   and all(Path(p).exists() and sha(Path(p))==h for p,h in cohort['source_sha256'].items()))
        artifacts[str(root/'qualification-cohort.json')]=sha(root/'qualification-cohort.json')
    b=[r for r in runs if r['test']=='B'];b_ok=any(r.get('passed') and r.get('final_common_predicate') for r in b)
    counts={}
    paths={'building':root/'checks/building-mutations/results.json','projects':root/'checks/projects/project-mutations/results.json',
           'skills':root/'checks/skills-final/skill-mutations/results.json','bcl':root/'checks/bcl/mutations/results.json',
           'native':root/'checks/native/mutations/results.json','gateway':root/'checks/gateway/results.json',
           'controller':root/'checks/controller/controller-mutations/results.json','campaign':root/'checks/campaign/mutations/results.json'}
    for name,path in paths.items():
        values=read(path)
        if values is not None:counts[name]={'total':len(values),'all_killed':all(x['status']=='KILLED' for x in values)};artifacts[str(path)]=sha(path)
    tests=(root/'python-final.log').read_text();match=re.search(r'Ran (\d+) tests',tests)
    tls=read(root/'checks/tls/interop.json')
    for name in ('python-final.log','gradle-final.log','native-final.log','tls-final.log','skills-final.log','project-mutations-final.log','building-mutations-final.log','controller-final.log','campaign-final.log','bcl-final.log','gateway-final.log','final-client.json'):
        file=root/name
        if file.exists():artifacts[str(file)]=sha(file)
    checks={'python':{'total':int(match[1]) if match else None,'passed':'\nOK\n' in tests},'mutations':counts,'mutation_total':sum(v['total'] for v in counts.values()),
            'gradle_passed':'BUILD SUCCESSFUL' in (root/'gradle-final.log').read_text(),'TLS':tls}
    sources=list(Path('tests/building').rglob('*.py'))+list(Path('tests/building/fixtures').iterdir())
    sources += [Path(p) for p in ['python/src/blockwire/skills/woodcutting.py','python/src/blockwire/skills/removing.py','python/src/blockwire/skills/__init__.py','python/src/blockwire/projects.py','python/src/blockwire/skills/mining.py','python/src/blockwire/skills/walking.py','python/src/blockwire/skills/item_actions.py','python/src/blockwire/project_agent.py','python/src/blockwire/bcl/registry.py','tools/superflat_benchmark.py','tools/report_superflat_benchmark.py','docs/superflat-building.md','python/tests/test_building_benchmark.py','python/tests/test_benchmark_lifecycle.py','tests/run_building_mutations.py']]
    document={'schema_version':1,'scope':'Supplied-material deterministic/real-LLM mechanical building, NOT unprepared Survival or hostile reliability',
        'assessment':{'A':'GO' if cohort_ok else 'CONDITIONAL GO' if accepted else 'NO-GO','B':'GO' if b_ok else 'NO-GO' if b else 'NOT RUN'},
        'fixture':fixture_audit(root/'private/baseline'),'reference':house.document(),
        'reference_sha256':house.digest(),'final_client':read(root/'final-client.json'),'architecture':'BCL/1 -> existing compiler/IR -> BCLJobs -> existing runtime/skills -> pinned native TLS bridge',
        'verification':'Fresh actor-bracketed native geometry plus bounded read-only CLOSED test-save voxels; never placement counts/model claims',
        'fresh_accepted_A_ids':[r['id'] for r in accepted],'unchanged_source_repeat_cohort':cohort,'repeat_cohort_passed':cohort_ok,'real_model_B_runs':len(b),
        'trial_accounting':'All original failures retained; debug continuations, fault probes, startup/storage failures and fresh building runs are separate. Consecutive post-fix successes do not erase earlier failures.',
        'runs':runs,'actual_B_programs':programs,'model_generated_B_programs':model_programs,'incomplete_artifacts':storage,'automated_checks':checks,
        'private_evidence_root':str(root),'artifact_sha256':artifacts,'source_sha256':{str(p):sha(p) for p in sources},
        'limitations':['One fixed seed/snapshot and supplied resources; Peaceful only','Native key-pulse counts and model tokens/cost NOT measured','Closed-save audit is privileged TEST-ONLY, never an agent API','No release/deployment authorized']}
    for run in sorted({p['run'] for p in model_programs}):
        selected=[p for p in model_programs if p['run']==run and p['source']]
        path=Path('docs/evidence')/('superflat-building-'+run+'.bcl')
        body='; HISTORICAL ACTUAL MODEL DECISIONS, including rejected/partial batches.\n; NOT a replayable complete program; never replay uncertain effects.\n'
        body+='\n; @frame\n'.join('; model call '+str(p['model_call'])+'\n'+p['source'] for p in selected)+'\n'
        path.write_text(body);document.setdefault('model_source_exports',[]).append(str(path))
        document['artifact_sha256'][str(path)]=sha(path)
    out=Path('docs/evidence/superflat-building.json');out.write_text(json.dumps(document,indent=2)+'\n')
    print(document['assessment'], 'accepted A',document['fresh_accepted_A_ids'],'checks',checks['python'],checks['mutation_total'])
if __name__=='__main__':main()
