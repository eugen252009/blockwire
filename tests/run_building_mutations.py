#!/usr/bin/env python3
"""Isolated benchmark-verifier/snapshot mutations. No graphical client/model."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ.get('BLOCKWIRE_VERIFICATION_DIR',ROOT/'build/superflat-benchmark/checks'))/'building-mutations'
MUTATIONS=[
 ('inspection_actor_bracket','live.py',"if before.get('actor_session')!=actor:",'if False:','test_benchmark_lifecycle.BenchmarkLifecycle.test_native_inspection_is_actor_bracketed'),
 ('atomic_evidence_publication','evidence.py','os.replace(temporary,path)','path.write_text(temporary.read_text())','test_benchmark_lifecycle.BenchmarkLifecycle.test_failed_evidence_publication_preserves_last_complete_record'),
 ('world_list_population_wait','fixture.py','if len(rows)==1:break','if rows:break','test_benchmark_lifecycle.BenchmarkLifecycle.test_async_world_list_population_is_awaited_before_selection'),
 ('material_identity','reference.py','actual==block','actual is not None','BenchmarkReference.test_BM03_wrong_material'),
 ('unknown_not_correct','reference.py',"'UNKNOWN' if actual is None","'CORRECT' if actual is None",'BenchmarkReference.test_BM04_unknown_never_correct_or_missing'),
 ('missing_not_correct','reference.py',"else 'MISSING' if actual in AIR","else 'CORRECT' if actual in AIR",'BenchmarkReference.test_BM02_missing_required_block'),
 ('all_targets_required','reference.py',"counts['CORRECT']==len(rows)","counts['CORRECT']>=0",'BenchmarkReference.test_BM02_missing_required_block'),
 ('no_extra_blocks','reference.py','and not extras and floor','and floor','BenchmarkReference.test_BM08_leftover_scaffold_and_unknown_free_cell'),
 ('floor_intact','reference.py','and floor and roof','and roof','BenchmarkReference.test_BM11_floor_damage'),
 ('native_access','reference.py','and accessible and safe','and safe','BenchmarkReference.test_BM09_native_reachability_not_implied_by_shell'),
 ('safe_player','reference.py','and roof and accessible and safe','and roof and accessible','BenchmarkReference.test_BM10_player_safe_required'),
 ('full_interior_height','reference.py','for z in range(1,self.depth-1) for y in range(self.height)','for z in range(1,self.depth-1) for y in range(2)','BenchmarkReference.test_BM07_hidden_third_height_interior_obstruction'),
 ('roof_predicate','reference.py',"'roof_complete':roof","'roof_complete':True",'BenchmarkReference.test_BM06_roof_hole'),
 ('native_actor','live.py',"and nav.get('actor_session')==actor",'', 'BenchmarkReference.test_BM14_no_native_actor_or_standing_assumption'),
 ('native_centre','live.py',"and nav.get('current_center_access') is True",'', 'BenchmarkReference.test_BM14_no_native_actor_or_standing_assumption'),
 ('native_dimension','live.py',"and scene.get('dimension')==nav.get('dimension')=='minecraft:overworld'",'', 'BenchmarkReference.test_BM14_no_native_actor_or_standing_assumption'),
 ('snapshot_hash','snapshots.py',"manifest['files']!=actual or manifest['identity']!=identity(actual)","False",'BenchmarkSnapshots.test_BM19_tamper_and_unowned_world_rejected'),
 ('world_closed','snapshots.py','require_closed();manifest=validate(snapshot)','manifest=validate(snapshot)','BenchmarkSnapshots.test_BM20_running_world_never_restored'),
 ('world_owner','snapshots.py','owned(destination);archive.parent.mkdir','archive.parent.mkdir','BenchmarkSnapshots.test_BM21_unowned_destination_not_overwritten'),
 ('snapshot_symlink','snapshots.py',"if p.is_symlink(): raise ValueError('Symlink in save tree')",'if False: pass','BenchmarkSnapshots.test_BM22_symlinks_forbidden'),
 ('nbt_negative_length','anvil.py',"if not 0<=n<=1000000:raise ValueError('NBT array bound')",'if False:pass','BenchmarkNBT.test_BM23_truncation_and_decompression_bounds'),
 ('missing_chunk_unknown','anvil.py','if value is None:continue',"if value is None:result[(x,y,z)]='minecraft:air';continue",'BenchmarkNBT.test_BM24_missing_chunk_stays_unknown'),
 ('palette_bits','anvil.py','i%per_long)*bits','i%per_long)*(bits+1)','BenchmarkNBT.test_BM25_padded_palette_decoder_string_and_compound'),
 ('portable_point_home','portable.py','POINT_HOME = (2.5, -60.0, -3.5)','POINT_HOME = (2.0, -60.0, -3.5)','test_portable_building.PortableBuildingContracts.test_PB02_relative_fixture_preserves_absolute_test_a_order_and_arguments'),
 ('portable_voxel_home','portable.py','VOXEL_HOME = (2, -60, -4)','VOXEL_HOME = (3, -60, -4)','test_portable_building.PortableBuildingContracts.test_PB03_fractional_home_maps_voxels_and_all_reference_blocks_exactly'),
 ('portable_house_offset','portable.py','HOUSE_ORIGIN_LOCAL = (-2, 0, 4)','HOUSE_ORIGIN_LOCAL = (-1, 0, 4)','test_portable_building.PortableBuildingContracts.test_PB03_fractional_home_maps_voxels_and_all_reference_blocks_exactly'),
 ('portable_home_floor','portable.py','math.floor(float(value))','math.ceil(float(value))','test_portable_building.PortableBuildingContracts.test_PB04_three_origins_share_identical_local_mapping_and_translation'),
 ('portable_explicit_relative','fixtures/superflat-house-relative.bcl','S1 relative','S1 absolute','test_portable_building.PortableBuildingContracts.test_PB01_frozen_source_starts_with_one_explicit_home_and_all_frames_compile'),
 ('portable_program_coordinate','fixtures/superflat-house-relative.bcl','M0 X0 Y0 Z6','M0 X1 Y0 Z6','test_portable_building.PortableBuildingContracts.test_PB02_relative_fixture_preserves_absolute_test_a_order_and_arguments'),
 ('portable_repl_eof','portable_live.py',"REPL_PIPELINE = 'S0 sync\\nS1 relative\\nM0 X0 Y0 Z1\\nM0 X0 Y0 Z0\\n'","REPL_PIPELINE = 'S0 sync\\nS1 relative\\nM0 X0 Y0 Z1\\nM0 X0 Y0 Z0\\n:quit\\n'",'test_portable_building.PortableBuildingContracts.test_PB07_redirected_repl_uses_eof_to_wait_not_explicit_quit_cancellation'),
 ('portable_player_wrapper','tools/portable_bcl_benchmark.py','player = Player(bridge)','player = bridge','test_portable_building.PortableToolContracts.test_PB08_native_entry_wraps_the_authenticated_bridge_in_player'),
]

def main():
    OUT.mkdir(parents=True,exist_ok=True);results=[]
    for name,file,old,new,test in MUTATIONS:
        with tempfile.TemporaryDirectory(prefix='blockwire-building-mutation-') as temp:
            root=Path(temp)
            shutil.copytree(ROOT/'python/src/blockwire',root/'python/src/blockwire',ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copytree(ROOT/'tests/building',root/'tests/building',ignore=shutil.ignore_patterns('__pycache__'))
            (root/'python/tests').mkdir(parents=True);(root/'tools').mkdir(parents=True)
            shutil.copy2(ROOT/'tools/portable_bcl_benchmark.py',root/'tools/portable_bcl_benchmark.py')
            for module in ('test_building_benchmark.py','test_benchmark_lifecycle.py','test_portable_building.py'):
                shutil.copy2(ROOT/'python/tests'/module,root/'python/tests'/module)
            target=(root/file if file.startswith('tools/') else root/'tests/building'/file);source=target.read_text()
            if source.count(old)!=1:status='INVALID_ANCHOR';output=f'Anchor count: {source.count(old)}'
            else:
                target.write_text(source.replace(old,new));env={**os.environ,'PYTHONPATH':str(root/'python/src')+os.pathsep+str(root/'python/tests')}
                call=subprocess.run([sys.executable,'-m','unittest',test if test.startswith('test_') else 'test_building_benchmark.'+test],cwd=root,env=env,text=True,capture_output=True,timeout=20)
                output=call.stdout+call.stderr
                expected_portable_freeze = name.startswith('portable_') and 'Portable BCL fixture hash changed' in output
                status='KILLED' if call.returncode and (('FAIL:' in output and 'AssertionError' in output) or expected_portable_freeze) else 'SURVIVED' if not call.returncode else 'INVALID_FAILURE'
            (OUT/(name+'.log')).write_text(output);results.append({'name':name,'status':status});print(name,status,flush=True)
    (OUT/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    return 0 if all(r['status']=='KILLED' for r in results) else 1
if __name__=='__main__':raise SystemExit(main())
