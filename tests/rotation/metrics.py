"""Pure analysis for recorded native time-based camera traces."""
import csv,io,math,statistics


def yaw_delta(target,current):return (target-current+180)%360-180

def angle_error(yaw,pitch,target_yaw,target_pitch):
    return math.hypot(yaw_delta(target_yaw,yaw),target_pitch-pitch)

def _curve(profile,t):
    t=max(0.,min(1.,t))
    return t if profile in {'legacy','linear'} else t*t*(3.-2.*t)

def _inputs(sample):
    values=sample.get('inputs',{})
    return tuple(key for key in ('forward','back','left','right','sprint','sneak','jump') if values.get(key))

def analyse(samples,scenario,outcome):
    if not samples:return {'sample_count':0,'success':False,'reason':'no_native_samples'}
    start_ns=outcome['measurement_start_ns'];target_ns=outcome.get('final_target_started_ns',start_ns)
    measured=[sample for sample in samples if sample['monotonic_ns']>=start_ns]
    if not measured:measured=samples[-1:]
    target_yaw,target_pitch=outcome['effective_target']
    reached=next((sample for sample in measured if sample['monotonic_ns']>=target_ns and
                  angle_error(sample['yaw'],sample['pitch'],target_yaw,target_pitch)<=.5),None)
    end_ns=(reached or measured[-1])['monotonic_ns']
    active=[sample for sample in measured if sample['monotonic_ns']<=end_ns]
    yaw_steps=[yaw_delta(b['yaw'],a['yaw']) for a,b in zip(active,active[1:])]
    pitch_steps=[b['pitch']-a['pitch'] for a,b in zip(active,active[1:])]
    angular_steps=[math.hypot(y,p) for y,p in zip(yaw_steps,pitch_steps)]
    signs=[1 if value>.05 else -1 if value<-.05 else 0 for value in yaw_steps]
    signs=[value for value in signs if value]
    reversals=sum(a!=b for a,b in zip(signs,signs[1:]))
    intervals=[(b['monotonic_ns']-a['monotonic_ns'])/1e6 for a,b in zip(active,active[1:]) if b['monotonic_ns']>a['monotonic_ns']]
    final=measured[-1];final_yaw_error=abs(yaw_delta(target_yaw,final['yaw']));final_pitch_error=abs(target_pitch-final['pitch'])
    start_view=outcome['final_target_start_view'];dyaw=yaw_delta(target_yaw,start_view[0]);dpitch=target_pitch-start_view[1]
    extent=math.hypot(dyaw,dpitch)
    actual_duration=0. if extent<=.5 and reached else (reached['monotonic_ns']-target_ns)/1e6 if reached else None
    duration_error=None if actual_duration is None or extent<=.5 else actual_duration-scenario.duration_ms
    trajectory=[];overshoot=[];extent_squared=dyaw*dyaw+dpitch*dpitch
    for sample in active:
        if sample['monotonic_ns']<target_ns:continue
        elapsed=(sample['monotonic_ns']-target_ns)/1e6
        progress=_curve(outcome['profile'],elapsed/scenario.duration_ms)
        expected_yaw=start_view[0]+dyaw*progress;expected_pitch=start_view[1]+dpitch*progress
        trajectory.append(angle_error(sample['yaw'],sample['pitch'],expected_yaw,expected_pitch))
        if extent_squared:
            actual_yaw=yaw_delta(sample['yaw'],start_view[0]);actual_pitch=sample['pitch']-start_view[1]
            along=(actual_yaw*dyaw+actual_pitch*dpitch)/math.sqrt(extent_squared)
            overshoot.append(max(0.,along-math.sqrt(extent_squared)))
    positions=[sample['position'] for sample in active]
    path=sum(math.dist(a,b) for a,b in zip(positions,positions[1:]))
    inputs=[_inputs(sample) for sample in active]
    input_changes=sum(a!=b for a,b in zip(inputs,inputs[1:]))
    speeds=[sample.get('horizontal_speed',0.) for sample in active]
    moving=[speed>=.01 for speed in speeds]
    stop_runs=0;inside=False
    for index,value in enumerate(moving):
        internal=any(moving[:index]) and any(moving[index+1:])
        if not value and internal and not inside:stop_runs+=1;inside=True
        if value:inside=False
    cancel_ns=outcome.get('cancelled_ns')
    after_cancel=[sample for sample in measured if cancel_ns is not None and sample['monotonic_ns']>=cancel_ns]
    post_cancel_steps=[math.hypot(yaw_delta(b['yaw'],a['yaw']),b['pitch']-a['pitch']) for a,b in zip(after_cancel,after_cancel[1:])]
    cancellation_stable=bool(cancel_ns is not None and len(after_cancel)>=3 and max(post_cancel_steps or [0.])<=.1)
    duration_tolerance=max(75.,scenario.duration_ms*.35)
    duration_applicable=scenario.cancel_after_ms is None and extent>.5
    duration_ok=(actual_duration is not None and abs(duration_error)<=duration_tolerance) if duration_applicable else None
    target_ok=final_yaw_error<=.5 and final_pitch_error<=.5
    if scenario.cancel_after_ms is not None:
        success=outcome.get('terminal_status')=='cancelled' and cancellation_stable
    else:
        success=target_ok and reached is not None and outcome.get('terminal_status') not in {'error','cancelled','actor_session_changed'}
    return {'sample_count':len(active),'tick_interval_ms_median':statistics.median(intervals) if intervals else None,
      'tick_interval_ms_min':min(intervals) if intervals else None,'tick_interval_ms_max':max(intervals) if intervals else None,
      'start_yaw':outcome['measurement_start_view'][0],'start_pitch':outcome['measurement_start_view'][1],
      'final_target_start_yaw':start_view[0],'final_target_start_pitch':start_view[1],
      'target_yaw':target_yaw,'target_pitch':target_pitch,'final_yaw':final['yaw'],'final_pitch':final['pitch'],
      'final_yaw_error':final_yaw_error,'final_pitch_error':final_pitch_error,'requested_duration_ms':scenario.duration_ms,
      'actual_duration_ms':actual_duration,'duration_error_ms':duration_error,'duration_applicable':duration_applicable,
      'duration_within_tolerance':duration_ok,
      'angular_extent_degrees':extent,'max_angular_step_degrees':max(angular_steps or [0.]),
      'median_angular_step_degrees':statistics.median(angular_steps or [0.]),'max_overshoot_degrees':max(overshoot or [0.]),
      'angular_direction_changes':reversals,
      'trajectory_rmse_degrees':math.sqrt(sum(value*value for value in trajectory)/len(trajectory)) if trajectory else 0.,
      'instant_snap_observed':bool(extent>5 and max(angular_steps or [0.])>=extent*.8),
      'full_stop_runs':stop_runs,'input_changes':input_changes,'path_length':path,
      'net_displacement':math.dist(positions[0],positions[-1]) if positions else 0.,
      'cancellation_stable':cancellation_stable,'post_cancel_max_angular_step':max(post_cancel_steps or [0.]),
      'trace_rotation_statuses':sorted({sample.get('rotation_status') for sample in active if sample.get('rotation_status') is not None}),
      'success':success}

def aggregate(rows):
    if not rows:return {'runs':0,'successes':0,'success_rate':0.}
    metrics=[row['metrics'] for row in rows]
    out={'runs':len(rows),'successes':sum(row['metrics']['success'] for row in rows)};out['success_rate']=out['successes']/len(rows)
    for key in ('actual_duration_ms','duration_error_ms','final_yaw_error','final_pitch_error','max_angular_step_degrees',
                'max_overshoot_degrees','angular_direction_changes','trajectory_rmse_degrees','full_stop_runs','input_changes','path_length','net_displacement'):
        values=[metric[key] for metric in metrics if metric.get(key) is not None]
        if values:out[key]={'median':statistics.median(values),'min':min(values),'max':max(values),'spread':max(values)-min(values)}
    out['duration_applicable_runs']=sum(bool(metric.get('duration_applicable')) for metric in metrics)
    out['duration_within_tolerance']=sum(metric.get('duration_within_tolerance') is True for metric in metrics)
    out['instant_snaps']=sum(bool(metric['instant_snap_observed']) for metric in metrics)
    return out

def csv_text(samples):
    fields=['client_tick','actor_tick','game_time','monotonic_ns','x','y','z','vx','vy','vz','horizontal_speed','yaw','pitch',
            'on_ground','sprinting','sneaking','inputs','remote_owned_inputs','rotation_id','rotation_status','rotation_target_yaw',
            'rotation_target_pitch','rotation_requested_duration_ms','rotation_profile']
    output=io.StringIO();writer=csv.DictWriter(output,fieldnames=fields);writer.writeheader()
    for sample in samples:
        position=sample['position'];velocity=sample['velocity'];writer.writerow({
          'client_tick':sample['client_tick'],'actor_tick':sample['actor_tick'],'game_time':sample['game_time'],
          'monotonic_ns':sample['monotonic_ns'],'x':position[0],'y':position[1],'z':position[2],
          'vx':velocity[0],'vy':velocity[1],'vz':velocity[2],'horizontal_speed':sample['horizontal_speed'],
          'yaw':sample['yaw'],'pitch':sample['pitch'],'on_ground':sample['on_ground'],'sprinting':sample['sprinting'],
          'sneaking':sample['sneaking'],'inputs':'+'.join(_inputs(sample)),
          'remote_owned_inputs':'+'.join(sample.get('remote_owned_inputs',[])),
          'rotation_id':sample.get('rotation_id'),'rotation_status':sample.get('rotation_status'),
          'rotation_target_yaw':sample.get('rotation_target_yaw'),'rotation_target_pitch':sample.get('rotation_target_pitch'),
          'rotation_requested_duration_ms':sample.get('rotation_requested_duration_ms'),'rotation_profile':sample.get('rotation_profile')})
    return output.getvalue()
