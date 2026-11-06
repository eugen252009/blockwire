#!/usr/bin/env python3
"""Isolated negative contracts for explicit machine manipulation. No real game/model."""
import os,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CASES=[
 ('short_phase_lease','machine_manipulation.py','context.player.drive(phase.buttons,6,','context.player.drive(phase.buttons,100,','test_machine_manipulation.ManipulationContracts.test_phases_retain_common_key_with_short_leases_and_one_press'),
 ('single_press','machine_manipulation.py','actor_session=actor);pressed=True','actor_session=actor);pressed=False','test_machine_manipulation.ManipulationContracts.test_phases_retain_common_key_with_short_leases_and_one_press'),
 ('retained_keys','machine_manipulation.py','for index,phase in enumerate(parameters.phases):','for index,phase in enumerate(parameters.phases):\n        context.player.stop()','test_machine_manipulation.ManipulationContracts.test_phases_retain_common_key_with_short_leases_and_one_press'),
 ('target_guard','machine_manipulation.py','if target is None:return','if True:return','test_machine_manipulation.ManipulationContracts.test_target_and_actor_change_prevent_press'),
 ('slot_precondition','machine_manipulation.py','if not matches(value,step.before,step.carried_before):','if False:','test_machine_manipulation.ManipulationContracts.test_precondition_failure_has_no_click_and_partial_cursor_is_not_closed'),
 ('slot_postcondition','machine_manipulation.py','if matches(value,step.after,step.carried_after):break','if True:break','test_machine_manipulation.ManipulationContracts.test_receipts_cannot_authorize_tail_or_retry'),
 ('fresh_slot_identity','machine_manipulation.py',"state_id=value['state_id']","state_id=0",'test_machine_manipulation.ManipulationContracts.test_explicit_slot_program_observes_native_shaped_output_and_consumption'),
 ('uncertain_slot_halts','bcl/runtime.py',"'input_release_not_observed','inventory_effect_not_observed','actor_session_changed'","'input_release_not_observed','actor_session_changed'",'test_machine_profile.MachineWire.test_uncertain_slot_effect_halts_queued_work'),
 ('operation_budget','machine_composition.py',"if name=='slot_program':return len(params.steps)","if name=='slot_program':return 1",'test_machine_manipulation.ManipulationContracts.test_schema_compiler_budget_and_reference_are_bounded'),
 ('aim_geometry','machine_actions.py','math.atan2(-dx,dz)','math.atan2(dx,dz)','test_machine_manipulation.ManipulationContracts.test_aim_geometry_and_failed_rotation_do_not_choose_or_use_targets'),
]

def main():
 failed=[]
 for name,filename,before,after,test in CASES:
  with tempfile.TemporaryDirectory(prefix='blockwire-machine-construction-') as directory:
   root=Path(directory);shutil.copytree(ROOT/'python/src',root/'src',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
   path=root/'src/blockwire'/filename;source=path.read_text();assert source.count(before)==1,name
   source=source.replace(before,after);compile(source,str(path),'exec');path.write_text(source)
   env={**os.environ,'PYTHONPATH':str(root/'src')+os.pathsep+str(ROOT/'python/tests')}
   result=subprocess.run([sys.executable,'-m','unittest',test],cwd=root,env=env,capture_output=True,text=True,timeout=30)
   killed=result.returncode!=0 and any(kind+test.split('.')[-1] in result.stderr for kind in ('FAIL: ','ERROR: '))
   print(name,'KILLED' if killed else 'NOT_KILLED',flush=True)
   if not killed:failed.append(name);print(result.stdout+result.stderr)
 return bool(failed)
if __name__=='__main__':sys.exit(main())
