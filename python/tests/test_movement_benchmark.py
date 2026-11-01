"""Deterministic movement benchmark contracts; NOT graphical Minecraft acceptance."""
import json,math,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tests'))
from movement.reference import scenarios,document,digest
from movement.metrics import analyse,aggregate,csv_text
from movement.fixture import COMMANDS
from movement.snapshots import OWNER,FIXTURE,DIRECTORY,capture,validate,restore

class MovementBenchmarkContracts(unittest.TestCase):
    def test_MB01_hardcoded_categories_and_repetition_bounds(self):
        rows=scenarios();categories={r.category for r in rows}
        self.assertTrue({'linear','vertical','combined','turns','curves','modes','parkour','building','precision'}<=categories)
        self.assertGreaterEqual(len(rows),40);self.assertEqual(len({r.name for r in rows}),len(rows))
        self.assertTrue(all(1<=r.repeats<=5 and r.max_ticks<=400 for r in rows))
        self.assertFalse(any('llm' in json.dumps(r.document()).lower() for r in rows))

    def test_MB02_reference_is_stable_and_physical_y_is_not_synthetic(self):
        first=digest();self.assertEqual(first,digest());self.assertEqual(document()['minecraft_version'],'26.3')
        vertical=[r for r in scenarios() if r.category in {'vertical','parkour','building'}]
        self.assertTrue(all(r.terrain for r in vertical));self.assertTrue(any(r.jump for r in vertical));self.assertTrue(any(r.target[1]<r.start[1] for r in vertical))

    def test_MB03_fixture_has_flat_axes_safety_parkour_roof_and_no_test_commands(self):
        joined='\n'.join(COMMANDS)
        for fragment in ('-80 63 -60 80 63 30','10 63 40 12 63 43','50 66 40 54 66 44','52 65 45'):
            self.assertIn(fragment,joined)
        self.assertNotIn('/tp @s 52.5 66 46',joined)  # Edge state is per-run preparation, never fixture acceptance.

    def test_MB04_metrics_use_recorded_ticks_velocity_collision_and_failed_runs(self):
        rows=[]
        for i,(x,v,held) in enumerate([(0,.0,False),(.2,.2,True),(.5,.3,True),(.7,.2,False),(.7,0,False)]):
            rows.append({'client_tick':i,'actor_tick':i,'game_time':100+i,'monotonic_ns':i*50_000_000,
              'position':[x,64.,.5],'velocity':[v,0,0],'horizontal_speed':v,'yaw':-90.,'pitch':0.,'on_ground':True,
              'horizontal_collision':i==2,'minor_horizontal_collision':False,'vertical_collision':True,'vertical_collision_below':True,
              'sprinting':False,'sneaking':False,'fall_distance':0.,'health':20.,
              'inputs':{'forward':held},'remote_owned_inputs':['forward'] if held else []})
        measured=analyse(rows,(.7,64.,.5),result_status='succeeded')
        self.assertTrue(measured['success']);self.assertEqual(measured['game_ticks'],4);self.assertEqual(measured['horizontal_collision_ticks'],1)
        failed=dict(measured,success=False);summary=aggregate([{'metrics':measured},{'metrics':failed}]);self.assertEqual(summary['success_rate'],.5)
        csv=csv_text(rows);self.assertIn('horizontal_speed',csv);self.assertEqual(csv.count('\n'),6)

    def test_MB05_owned_snapshot_rejects_tamper_and_restores_exactly(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);world=root/DIRECTORY;world.mkdir();(world/OWNER).write_text(json.dumps({'fixture':FIXTURE}));(world/'level.dat').write_bytes(b'a')
            closed=lambda:None;manifest=capture(world,root/'baseline',closed);self.assertEqual(validate(root/'baseline')['identity'],manifest['identity'])
            (world/'level.dat').write_bytes(b'b');restore(root/'baseline',world,root/'archive',closed);self.assertEqual((world/'level.dat').read_bytes(),b'a')
            (root/'baseline'/'level.dat').write_bytes(b'x');
            with self.assertRaises(ValueError):validate(root/'baseline')

if __name__=='__main__':unittest.main()
