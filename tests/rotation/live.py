"""Authorized deterministic native camera measurements; no LLM and no combat."""
import hashlib,json,math,os,shutil,threading,time
from pathlib import Path
from movement.fixture import title,load,close
from movement.snapshots import DIRECTORY,restore,capture,validate
from .reference import scenarios,digest
from .metrics import analyse,aggregate,csv_text,yaw_delta

START=(-70.5,64.,-50.5)

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def _atomic(path,value):
    path=Path(path);temporary=path.with_suffix(path.suffix+'.partial');temporary.write_text(json.dumps(value,indent=2)+'\n');os.replace(temporary,path)
def selected(names=()):
    rows=scenarios();wanted=set(names)
    if wanted:
        unknown=wanted-{row.name for row in rows}
        if unknown:raise ValueError('Unknown rotation scenarios: '+','.join(sorted(unknown)))
        rows=tuple(row for row in rows if row.name in wanted)
    return rows

def _view(player,actor):
    scene=player.observe()
    if scene.get('actor_session')!=actor:raise RuntimeError('Actor replaced during rotation benchmark')
    if not scene.get('in_world') or not scene.get('alive'):raise RuntimeError('Rotation actor unavailable')
    return scene

def _wait_ready(player,actor,timeout=5.):
    end=time.monotonic()+timeout;stable=0
    while time.monotonic()<end:
        nav=player.navigation(terrain=True)
        if nav.get('actor_session')!=actor:raise RuntimeError('Actor replaced during reset')
        position=nav.get('position',[])
        if nav.get('on_ground') and len(position)==3 and max(abs(position[i]-START[i]) for i in range(3))<.08 and nav.get('horizontal_speed',1.)<.004:
            stable+=1
            if stable>=3:return nav
        else:stable=0
        time.sleep(.05)
    raise RuntimeError('Administrative rotation start did not settle')

def _renew(player,buttons,actor):
    if buttons:player.drive(list(buttons),8,wait=False,actor_session=actor)

def reset(player,scenario,actor):
    player.stop();x,y,z=START
    player.command(f'/tp @s {x:.6f} {y:.6f} {z:.6f} {scenario.start_yaw:.6f} {scenario.start_pitch:.6f}',actor_session=actor)
    _wait_ready(player,actor)
    if scenario.movement:
        _renew(player,scenario.movement,actor);end=time.monotonic()+1.
        while time.monotonic()<end:
            nav=player.navigation(terrain=True)
            if nav.get('actor_session')!=actor:raise RuntimeError('Actor replaced before moving rotation')
            if nav.get('horizontal_speed',0.)>=.01:break
            time.sleep(.03)
        else:raise RuntimeError('Moving rotation prelude did not move')
    trace=player.motion_trace(reset=True,actor_session=actor)
    if trace.get('profile')!='native_player_motion_ticks_v1':raise RuntimeError('Matching motion telemetry required')
    if scenario.movement:_renew(player,scenario.movement,actor)
    time.sleep(.11)
    before=player.motion_trace(limit=8,actor_session=actor)
    if not before['samples']:raise RuntimeError('No native tick marker before rotation')
    scene=_view(player,actor)
    return {'measurement_start_ns':before['samples'][-1]['monotonic_ns'],'view':[scene['yaw'],scene['pitch']],
            'position':scene['position'],'rotation':scene.get('rotation')}

def _legacy_step(player,scene,target,actor):
    dyaw=yaw_delta(target[0],scene['yaw']);dpitch=target[1]-scene['pitch'];extent=max(abs(dyaw),abs(dpitch))
    fraction=min(1.,8./extent) if extent else 1.
    player.look((scene['yaw']+dyaw*fraction+180)%360-180,scene['pitch']+dpitch*fraction,actor_session=actor)

def _native_target(player,target,duration_ms,profile,actor):
    return player.look(target[0],target[1],actor_session=actor,duration_ms=duration_ms,rotation_profile=profile)

def execute(player,scenario,variant,actor,marker):
    if variant not in {'legacy','linear','smoothstep'}:raise ValueError('Unknown rotation variant')
    profile='legacy' if variant=='legacy' else variant
    measurement_start=marker['measurement_start_ns'];measurement_view=marker['view'];started=time.monotonic()
    events=list(scenario.sequence) if scenario.sequence else [(0,scenario.target_yaw,scenario.target_pitch)]
    if scenario.supersede_after_ms is not None:events.append((scenario.supersede_after_ms,scenario.supersede_yaw,scenario.supersede_pitch))
    events.sort();event_index=0;target=(events[0][1],events[0][2]);final_target_start_ns=measurement_start
    final_target_start_view=measurement_view[:];receipts=[];cancelled_ns=None;terminal='active';renew_at=0.
    last_event_ms=max(event[0] for event in events);deadline=started+(last_event_ms+scenario.duration_ms+1800)/1000
    while time.monotonic()<deadline:
        now=time.monotonic();elapsed_ms=(now-started)*1000
        while event_index<len(events) and elapsed_ms>=events[event_index][0]:
            _,yaw,pitch=events[event_index];scene=_view(player,actor);target=(yaw,pitch)
            if variant!='legacy':
                receipt=_native_target(player,target,scenario.duration_ms,profile,actor);receipts.append(receipt)
                final_target_start_ns=int(receipt.get('started_ns',player.motion_trace(limit=1,actor_session=actor)['samples'][-1]['monotonic_ns']))
            else:
                latest=player.motion_trace(limit=1,actor_session=actor)['samples'];final_target_start_ns=latest[-1]['monotonic_ns'] if latest else measurement_start
            final_target_start_view=[scene['yaw'],scene['pitch']];event_index+=1
        if scenario.cancel_after_ms is not None and elapsed_ms>=scenario.cancel_after_ms:
            player.stop();time.sleep(.28)
            latest=player.motion_trace(limit=16,actor_session=actor)['samples']
            rotation_id=receipts[-1].get('rotation_id') if receipts else None
            cancelled=next((sample for sample in latest if sample.get('rotation_status')=='cancelled' and
                            (rotation_id is None or sample.get('rotation_id')==rotation_id)),None)
            cancelled_ns=cancelled['monotonic_ns'] if cancelled else None
            terminal='cancelled';break
        scene=_view(player,actor)
        if variant=='legacy':_legacy_step(player,scene,target,actor)
        rotation=scene.get('rotation',{})
        error=math.hypot(yaw_delta(target[0],scene['yaw']),target[1]-scene['pitch'])
        all_events=event_index==len(events)
        inactive=variant=='legacy' or not rotation.get('active',False)
        if all_events and error<=.5 and inactive:
            terminal=rotation.get('status','completed') if variant!='legacy' else 'completed';time.sleep(.12);break
        if scenario.movement and now>=renew_at:
            _renew(player,scenario.movement,actor);renew_at=now+.16
        time.sleep(.05 if variant=='legacy' else .018)
    else:terminal='timed_out'
    if scenario.movement and terminal!='cancelled':player.stop()
    elif not scenario.movement and terminal not in {'cancelled'}:
        # Stop is also the lifecycle fence for any timed request that failed to finish.
        if terminal!='completed':player.stop()
    time.sleep(.16)
    scene=_view(player,actor);rotation=scene.get('rotation',{})
    if terminal=='active':terminal=rotation.get('status','completed')
    return {'variant':variant,'profile':profile,'terminal_status':terminal,'receipts':receipts,
            'measurement_start_ns':measurement_start,'measurement_start_view':measurement_view,
            'final_target_started_ns':final_target_start_ns,'final_target_start_view':final_target_start_view,
            'effective_target':list(target),'cancelled_ns':cancelled_ns,
            'final_scene':{'yaw':scene['yaw'],'pitch':scene['pitch'],'position':scene['position'],'rotation':rotation}}

def one(player,scenario,variant,index,directory,actor):
    marker=reset(player,scenario,actor);started=time.monotonic()
    try:outcome=execute(player,scenario,variant,actor,marker)
    except BaseException as error:
        try:player.stop()
        finally:
            outcome={'variant':variant,'profile':'legacy' if variant=='legacy' else variant,'terminal_status':'error',
              'measurement_start_ns':marker['measurement_start_ns'],'measurement_start_view':marker['view'],
              'final_target_started_ns':marker['measurement_start_ns'],'final_target_start_view':marker['view'],
              'effective_target':[scenario.target_yaw,scenario.target_pitch],
              'error':type(error).__name__+': '+str(error)[:1024]}
    trace=player.motion_trace(limit=4096,actor_session=actor);samples=trace['samples']
    if any(sample.get('actor_session')!=actor for sample in samples):raise RuntimeError('Mixed actor telemetry')
    metrics=analyse(samples,scenario,outcome)
    row={'scenario':scenario.document(),'variant':variant,'repeat':index,'administrative_start':marker,
         'outcome':outcome,'metrics':metrics,'elapsed_seconds':time.monotonic()-started,
         'trace_profile':trace['profile'],'trace_dropped_samples':trace['dropped_samples']}
    stem=directory/f'{scenario.name}-{index:02d}';_atomic(stem.with_suffix('.json'),row);stem.with_suffix('.csv').write_text(csv_text(samples));return row

def cleanup_close(player):
    player.stop();close(player)

def run(player,args):
    movement_private=Path(args.movement_private);manifest=validate(movement_private/'baseline')
    root=Path(args.output_root);run_dir=root/args.run_id
    if run_dir.exists():raise ValueError('Unique rotation run ID required')
    if shutil.disk_usage(root.parent if root.parent.exists() else Path('.')).free<256*1024*1024:raise RuntimeError('Insufficient free storage')
    run_dir.mkdir(parents=True,mode=0o700);world=Path(args.saves)/DIRECTORY;chosen=selected(args.scenario)
    source_paths=[Path('python/src/blockwire/skills/motion.py'),Path('python/src/blockwire/client.py'),Path('src/main/java/dev/blockwire/Blockwire.java'),
                  Path('src/main/java/dev/blockwire/Protocol.java'),Path('src/main/java/dev/blockwire/RotationController.java'),
                  Path('src/main/java/dev/blockwire/MotionTrace.java'),Path('tests/rotation/reference.py'),Path('tests/rotation/live.py'),Path('tests/rotation/metrics.py')]
    metadata={'run_id':args.run_id,'variant':args.variant,'fixture_identity':manifest['identity'],'scenario_identity':digest(),
      'minecraft_version':'26.3','source_sha256':{str(path):sha(path) for path in source_paths},
      'scenario_names':[scenario.name for scenario in chosen],'repeat_policy':'Fixed declared repetitions; failures retained',
      'llm_calls':0,'administrative_commands_only_before_measurement':True,'combat':False}
    _atomic(run_dir/'metadata.json',metadata)
    restore(movement_private/'baseline',world,run_dir/'previous-closed-world',lambda:title(player))
    events=[];scene=load(player,audit=events.append);_atomic(run_dir/'load-events.json',events);actor=scene['actor_session'];rows=[]
    try:
        player.motion_trace(limit=1,reset=True,actor_session=actor)
        for scenario in chosen:
            count=args.repeats if args.repeats is not None else scenario.repeats
            for index in range(1,count+1):
                row=one(player,scenario,args.variant,index,run_dir,actor);rows.append(row)
                print(json.dumps({'scenario':scenario.name,'repeat':index,'variant':args.variant,'success':row['metrics']['success'],
                  'actual_duration_ms':row['metrics'].get('actual_duration_ms'),'max_step':row['metrics'].get('max_angular_step_degrees'),
                  'yaw_error':row['metrics'].get('final_yaw_error'),'status':row['outcome'].get('terminal_status')}),flush=True)
    finally:cleanup_close(player)
    summary={'metadata':metadata,'runs':len(rows),'successes':sum(row['metrics']['success'] for row in rows),
      'success_rate':sum(row['metrics']['success'] for row in rows)/len(rows) if rows else 0.,
      'duration_applicable_runs':sum(bool(row['metrics'].get('duration_applicable')) for row in rows),
      'duration_within_tolerance':sum(row['metrics'].get('duration_within_tolerance') is True for row in rows),
      'instant_snaps':sum(row['metrics']['instant_snap_observed'] for row in rows),
      'scenarios':{scenario.name:aggregate([row for row in rows if row['scenario']['name']==scenario.name]) for scenario in chosen}}
    _atomic(run_dir/'summary.json',summary);capture(world,run_dir/'ended-world',lambda:title(player));return summary
