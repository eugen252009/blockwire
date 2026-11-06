#!/usr/bin/env python3
"""Isolated lifecycle/lease/task-supervision mutations; no Minecraft connection."""
import os
from pathlib import Path
import run_bcl_mutations as runner
runner.OUT=Path(os.environ.get('BLOCKWIRE_VERIFICATION_DIR',runner.ROOT/'build/building-verification/gateway-mutations'))
runner.OUT.mkdir(parents=True,exist_ok=True)
runner.MUTATIONS=[
 ('respawn_opt_in','bcl/gateway.py',"or role!='controller' or not self.allow_respawn:","or role!='controller':",'test_gateway_hardening.HardeningContracts.test_GH11_respawn_is_explicit_fenced_and_requires_new_actor_binding'),
 ('natural_wall_proof','bcl/verification.py','if len(closed)>=3 and openings:','if openings:','test_building_verification.BuildingAcceptance.test_BU03_natural_earth_shelter_still_requires_native_entrance_and_headroom'),
 ('declared_roof_proof','bcl/verification.py','if roof not in expected or observed.get(roof) not in SOLIDS:continue','if observed.get(roof) not in SOLIDS:continue','test_building_verification.BuildingAcceptance.test_BU03_natural_earth_shelter_still_requires_native_entrance_and_headroom'),
 ('pose_actor_fence','skills/item_actions.py',"if nav.get('actor_session')!=ui.session:raise SkillStop('blocked','actor_session_changed')\n        if not nav.get('ready'):return blocked('placement_navigation_not_ready')","if False:raise SkillStop('blocked','actor_session_changed')\n        if not nav.get('ready'):return blocked('placement_navigation_not_ready')",'test_placement.PlacementContracts.test_PL04_optional_pose_uses_known_geometry_and_same_postcondition'),
 ('controller_lease','bcl/gateway.py',"if role=='controller' and actor_key in self.controllers:",'if False:','test_gateway_hardening.HardeningContracts.test_GH01_second_controller_denied_observer_reads_without_native_control'),
 ('observer_permissions','bcl/gateway.py',"report=compile_report(msg['source'],self.registry,permissions={'observe','settings','events'})","report=compile_report(msg['source'],self.registry,permissions=self.jobs.permissions)",'test_gateway_hardening.HardeningContracts.test_GH01_second_controller_denied_observer_reads_without_native_control'),
 ('late_reaper','bcl/gateway.py','self.reapers.add(task)','task.cancel();self.reapers.add(task)','test_gateway_hardening.HardeningContracts.test_GH02_late_cleanup_reaper_releases_binding_after_grace'),
 ('operation_not_transport','bcl/gateway.py','if classify(e) in {FaultKind.TRANSPORT,FaultKind.INVARIANT}:self.failed=True','if True:self.failed=True','test_gateway_hardening.HardeningContracts.test_GH03_typed_recoverable_rejection_does_not_latch_transport'),
 ('death_lifecycle','bcl/gateway.py',"if life in {'player.dead','player.not_in_world'}:",'if False:','test_gateway_hardening.HardeningContracts.test_GH04_dead_is_not_transport_failure_and_modal_queries_remain_live'),
 ('sender_supervision','bcl/gateway.py',"asyncio.create_task(ws.close(1011,'Gateway background task terminated'))",'pass # suppressed background failure','test_gateway_hardening.HardeningContracts.test_GH05_sender_failure_closes_connection_and_releases_session'),
 ('send_deadline','bcl/gateway.py','await asyncio.wait_for(ws.send(json.dumps(message,allow_nan=False)),self.send_timeout)','await ws.send(json.dumps(message,allow_nan=False))','test_gateway_hardening.HardeningContracts.test_GH06_slow_sender_times_out_instead_of_stalling_forever'),
 ('worker_base_exception','bcl/runtime.py',"except BaseException as e:result={'status':'failed','reason':'worker_terminated'","except Exception as e:result={'status':'failed','reason':'worker_terminated'",'test_gateway_hardening.HardeningContracts.test_GH08_worker_base_exception_does_not_strand_session_or_queue'),
 ('goal_scope','bcl/runtime.py',"result['objective_verified']=False  # BCL cannot attest an external free-text build/Survival goal.","result['objective_verified']=True",'test_bcl.RuntimeContracts.test_BR01_dispatch_sequential_verification_and_shared_cleanup'),
 ('placement_face','skills/item_actions.py',"hit.get('face') == goal.face","hit.get('face') == 'up'",'test_placement.PlacementContracts.test_PL03_face_destination_and_exact_face_are_required'),
]
if __name__=='__main__':raise SystemExit(runner.main())
