"""Deterministic rotation benchmark contracts; NOT graphical Minecraft acceptance."""
import json,math,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tests'))
from rotation.reference import scenarios,document,digest
from rotation.metrics import analyse,aggregate,csv_text,yaw_delta


def sample(t,yaw,pitch=0.,x=0.,held=False,status='active'):
    return {'client_tick':t//10,'actor_tick':t//10,'game_time':100+t//10,'monotonic_ns':t*1_000_000,
      'position':[x,64.,.5],'velocity':[.1 if held else 0.,0.,0.],'horizontal_speed':.1 if held else 0.,
      'yaw':yaw,'pitch':pitch,'on_ground':True,'sprinting':False,'sneaking':False,
      'inputs':{'forward':held},'remote_owned_inputs':['forward'] if held else [],'rotation_status':status}


class RotationBenchmarkContracts(unittest.TestCase):
    def test_RB01_reference_covers_required_times_axes_motion_wrap_cancel_and_retarget(self):
        rows=scenarios();names={row.name for row in rows}
        self.assertEqual(len(rows),50);self.assertEqual(len(names),50)
        self.assertEqual({100,200,400},{row.duration_ms for row in rows})
        self.assertTrue(any(row.movement for row in rows));self.assertTrue(any(row.target_pitch for row in rows))
        self.assertTrue(any('wrap' in row.name for row in rows));self.assertTrue(any(row.cancel_after_ms for row in rows))
        self.assertTrue(any(row.supersede_after_ms for row in rows));self.assertTrue(any(row.sequence for row in rows))
        self.assertEqual(document()['minecraft_version'],'26.3');self.assertEqual(digest(),digest())
        self.assertFalse(any('llm' in json.dumps(row.document()).lower() for row in rows))

    def test_RB02_shortest_yaw_math_and_irregular_tick_metrics(self):
        self.assertEqual(yaw_delta(-179.,179.),2.);self.assertEqual(yaw_delta(179.,-179.),-2.)
        scenario=next(row for row in scenarios() if row.name=='yaw_90_200ms')
        times=[0,31,79,143,207,260];values=[0,5.8,30.8,72.2,90,90]
        samples=[sample(t,yaw) for t,yaw in zip(times,values)]
        outcome={'measurement_start_ns':0,'final_target_started_ns':0,'effective_target':[90.,0.],
          'final_target_start_view':[0.,0.],'measurement_start_view':[0.,0.],'profile':'smoothstep','terminal_status':'completed'}
        measured=analyse(samples,scenario,outcome)
        self.assertTrue(measured['success']);self.assertTrue(measured['duration_within_tolerance'])
        self.assertAlmostEqual(measured['actual_duration_ms'],207.);self.assertFalse(measured['instant_snap_observed'])
        self.assertEqual(measured['max_overshoot_degrees'],0.)
        self.assertEqual(measured['tick_interval_ms_min'],31.);self.assertEqual(measured['tick_interval_ms_max'],64.)
        same=next(row for row in scenarios() if row.name=='identical_yaw_pitch_200ms')
        noop=analyse([sample(0,37.,-12.),sample(50,37.,-12.)],same,
          {'measurement_start_ns':0,'final_target_started_ns':0,'effective_target':[37.,-12.],
           'final_target_start_view':[37.,-12.],'measurement_start_view':[37.,-12.],
           'profile':'linear','terminal_status':'completed'})
        self.assertEqual(noop['actual_duration_ms'],0.);self.assertFalse(noop['duration_applicable'])

    def test_RB03_moving_trace_records_displacement_inputs_and_no_full_stop(self):
        scenario=next(row for row in scenarios() if row.name=='moving_walk_yaw90_200ms')
        samples=[sample(t,yaw,x=t/1000,held=True) for t,yaw in ((0,0),(50,14),(100,45),(150,76),(200,90))]
        outcome={'measurement_start_ns':0,'final_target_started_ns':0,'effective_target':[90.,0.],
          'final_target_start_view':[0.,0.],'measurement_start_view':[0.,0.],'profile':'smoothstep','terminal_status':'completed'}
        measured=analyse(samples,scenario,outcome)
        self.assertTrue(measured['success']);self.assertGreater(measured['net_displacement'],.19)
        self.assertEqual(measured['full_stop_runs'],0);self.assertEqual(measured['input_changes'],0)

    def test_RB04_cancellation_requires_observed_stability(self):
        scenario=next(row for row in scenarios() if row.name=='cancel_yaw180_after80ms')
        samples=[sample(t,yaw,status='cancelled' if t>=100 else 'active') for t,yaw in ((0,0),(50,-8),(100,-20),(150,-20),(200,-20))]
        outcome={'measurement_start_ns':0,'final_target_started_ns':0,'effective_target':[-180.,0.],
          'final_target_start_view':[0.,0.],'measurement_start_view':[0.,0.],'profile':'smoothstep',
          'terminal_status':'cancelled','cancelled_ns':100_000_000}
        measured=analyse(samples,scenario,outcome)
        self.assertTrue(measured['success']);self.assertTrue(measured['cancellation_stable'])
        self.assertFalse(measured['duration_applicable']);self.assertIsNone(measured['duration_within_tolerance'])
        unstable=[dict(row) for row in samples];unstable[-1]['yaw']=-25.
        self.assertFalse(analyse(unstable,scenario,outcome)['success'])

    def test_RB05_aggregate_keeps_failures_and_csv_has_rotation_metadata(self):
        base={'success':True,'duration_applicable':True,'duration_within_tolerance':True,'instant_snap_observed':False,
          'actual_duration_ms':200.,'duration_error_ms':0.,'final_yaw_error':0.,'final_pitch_error':0.,
          'max_angular_step_degrees':20.,'max_overshoot_degrees':0.,'angular_direction_changes':0,'trajectory_rmse_degrees':1.,
          'full_stop_runs':0,'input_changes':0,'path_length':0.,'net_displacement':0.}
        failed=dict(base,success=False,duration_within_tolerance=False)
        summary=aggregate([{'metrics':base},{'metrics':failed}]);self.assertEqual(summary['success_rate'],.5)
        self.assertEqual((summary['duration_applicable_runs'],summary['duration_within_tolerance']),(2,1))
        text=csv_text([sample(0,0)]);self.assertIn('rotation_requested_duration_ms',text);self.assertIn('remote_owned_inputs',text)


if __name__=='__main__':unittest.main()
