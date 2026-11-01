"""Pure analysis of recorded native tick samples; no gameplay assumptions or effects."""
import csv,io,math,statistics

MOVING=.01
SETTLED=.004

def yaw_delta(a,b):return (a-b+180)%360-180

def input_tuple(sample):
    inputs=sample.get('inputs',{})
    return tuple(k for k in ('forward','back','left','right','jump','sneak','sprint') if inputs.get(k))

def analyse(samples,target,*,result_status=None,arrival_radius=.3):
    if not samples:return {'sample_count':0,'success':False,'reason':'no_native_samples'}
    positions=[s['position'] for s in samples]
    steps=[math.dist(a,b) for a,b in zip(positions,positions[1:])]
    horizontal=[math.hypot(b[0]-a[0],b[2]-a[2]) for a,b in zip(positions,positions[1:])]
    speeds=[s.get('horizontal_speed',math.hypot(*[s.get('velocity',[0,0,0])[i] for i in (0,2)])) for s in samples]
    moving=[v>=MOVING for v in speeds]
    stop_runs=0;inside=False
    for i,value in enumerate(moving):
        internal=any(moving[:i]) and any(moving[i+1:])
        if not value and internal and not inside:stop_runs+=1;inside=True
        if value:inside=False
    directions=[]
    for a,b in zip(positions,positions[1:]):
        dx,dz=b[0]-a[0],b[2]-a[2]
        if math.hypot(dx,dz)>=.005:directions.append(math.degrees(math.atan2(-dx,dz)))
    direction_changes=sum(abs(yaw_delta(b,a))>=20 for a,b in zip(directions,directions[1:]))
    inputs=[input_tuple(s) for s in samples]
    input_changes=sum(a!=b for a,b in zip(inputs,inputs[1:]))
    jumps=sum('jump' not in a and 'jump' in b for a,b in zip(inputs,inputs[1:]))+(1 if inputs and 'jump' in inputs[0] else 0)
    end=positions[-1];error=math.dist((end[0],end[2]),(target[0],target[2]));vertical_error=abs(end[1]-target[1])
    intervals=[(b['monotonic_ns']-a['monotonic_ns'])/1e6 for a,b in zip(samples,samples[1:]) if b['monotonic_ns']>a['monotonic_ns']]
    game_ticks=samples[-1]['game_time']-samples[0]['game_time'] if len(samples)>1 else 0
    settled=all(v<SETTLED for v in speeds[-3:]) if len(speeds)>=3 else speeds[-1]<SETTLED
    health_loss=max(0.,samples[0].get('health',0)-samples[-1].get('health',0))
    success=(result_status in (None,'succeeded') and error<=arrival_radius and vertical_error<=.2 and health_loss==0)
    return {'sample_count':len(samples),'client_ticks':samples[-1]['client_tick']-samples[0]['client_tick'] if len(samples)>1 else 0,
      'game_ticks':game_ticks,'wall_tick_ms_median':statistics.median(intervals) if intervals else None,
      'wall_tick_ms_min':min(intervals) if intervals else None,'wall_tick_ms_max':max(intervals) if intervals else None,
      'path_length':sum(steps),'horizontal_path_length':sum(horizontal),'net_horizontal_distance':math.hypot(end[0]-positions[0][0],end[2]-positions[0][2]),
      'vertical_range':max(p[1] for p in positions)-min(p[1] for p in positions),'max_horizontal_speed':max(speeds),
      'median_horizontal_speed':statistics.median(speeds),'full_stop_runs':stop_runs,'direction_changes_20deg':direction_changes,
      'input_changes':input_changes,'jump_attempts':jumps,'horizontal_collision_ticks':sum(bool(s.get('horizontal_collision')) for s in samples),
      'vertical_collision_ticks':sum(bool(s.get('vertical_collision')) for s in samples),'sprint_ticks':sum(bool(s.get('sprinting')) for s in samples),
      'sneak_ticks':sum(bool(s.get('sneaking')) for s in samples),'health_loss':health_loss,'end_position':end,
      'target_horizontal_error':error,'target_vertical_error':vertical_error,'settled_at_end':settled,'result_status':result_status,'success':success}

def aggregate(rows):
    if not rows:return {'runs':0,'success_rate':0}
    numeric=('game_ticks','path_length','target_horizontal_error','full_stop_runs','input_changes','horizontal_collision_ticks','health_loss','max_horizontal_speed')
    out={'runs':len(rows),'successes':sum(r['metrics']['success'] for r in rows)};out['success_rate']=out['successes']/len(rows)
    for key in numeric:
        values=[r['metrics'][key] for r in rows if r['metrics'].get(key) is not None]
        if values:out[key]={'median':statistics.median(values),'min':min(values),'max':max(values),'spread':max(values)-min(values)}
    return out

def csv_text(samples):
    fields=['client_tick','actor_tick','game_time','monotonic_ns','x','y','z','vx','vy','vz','horizontal_speed','yaw','pitch','on_ground',
      'horizontal_collision','minor_horizontal_collision','vertical_collision','vertical_collision_below','sprinting','sneaking','fall_distance','health','inputs','remote_owned_inputs']
    output=io.StringIO();writer=csv.DictWriter(output,fieldnames=fields);writer.writeheader()
    for s in samples:
        p=s['position'];v=s['velocity'];writer.writerow({'client_tick':s['client_tick'],'actor_tick':s['actor_tick'],'game_time':s['game_time'],
          'monotonic_ns':s['monotonic_ns'],'x':p[0],'y':p[1],'z':p[2],'vx':v[0],'vy':v[1],'vz':v[2],
          'horizontal_speed':s['horizontal_speed'],'yaw':s['yaw'],'pitch':s['pitch'],'on_ground':s['on_ground'],
          'horizontal_collision':s['horizontal_collision'],'minor_horizontal_collision':s['minor_horizontal_collision'],
          'vertical_collision':s['vertical_collision'],'vertical_collision_below':s['vertical_collision_below'],
          'sprinting':s['sprinting'],'sneaking':s['sneaking'],'fall_distance':s['fall_distance'],'health':s['health'],
          'inputs':'+'.join(input_tuple(s)),'remote_owned_inputs':'+'.join(s.get('remote_owned_inputs',[]))})
    return output.getvalue()
