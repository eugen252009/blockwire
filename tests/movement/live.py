"""Authorized deterministic native movement measurements; no LLM and no simulated acceptance."""
import hashlib,json,math,os,shutil,time
from pathlib import Path
from .fixture import NAME,START,title,load,close
from .snapshots import DIRECTORY,restore,capture,validate
from .reference import scenarios,digest
from .metrics import analyse,aggregate,csv_text,yaw_delta

MODES={'normal':'walk','fast':'run','sneak':'sneak'}

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def _atomic(path,value):
    path=Path(path);temporary=path.with_suffix(path.suffix+'.partial');temporary.write_text(json.dumps(value,indent=2)+'\n');os.replace(temporary,path)

def selected(names=()):
    rows=scenarios();wanted=set(names)
    if wanted:
        unknown=wanted-{r.name for r in rows}
        if unknown:raise ValueError('Unknown scenarios: '+','.join(sorted(unknown)))
        rows=tuple(r for r in rows if r.name in wanted)
    return rows

def _yaw(position,target):return math.degrees(math.atan2(-(target[0]-position[0]),target[2]-position[2]))

def _mode_buttons(mode,jump=False):
    result=['forward']
    if mode=='fast':result.append('sprint')
    if mode=='sneak':result.append('sneak')
    if jump:result.append('jump')
    return result

def _wait_ready(player,target,actor,timeout=8.):
    stable=0;end=time.monotonic()+timeout;last=None
    while time.monotonic()<end:
        nav=player.navigation(terrain=True)
        if nav.get('actor_session')!=actor:raise RuntimeError('Actor replaced during administrative reset')
        position=nav.get('position',[]);speed=nav.get('horizontal_speed',1.)
        if nav.get('on_ground') and len(position)==3 and abs(position[0]-target[0])<.08 and abs(position[1]-target[1])<.08 and abs(position[2]-target[2])<.08 and speed<.004:
            stable=stable+1 if last is not None else 1
            if stable>=3:return nav
        else:stable=0
        last=position;time.sleep(.05)
    raise RuntimeError('Administrative start did not settle at '+repr(target))

def reset(player,scenario,actor):
    player.stop();x,y,z=scenario.start
    initial_target=scenario.path[0];initial_yaw=scenario.prelude_yaw if scenario.prelude_yaw is not None else _yaw(scenario.start,initial_target)
    player.command(f'/effect clear @s',actor_session=actor);time.sleep(.08)
    player.command(f'/effect give @s minecraft:instant_health 1 10 true',actor_session=actor);time.sleep(.08)
    player.command(f'/tp @s {x:.6f} {y:.6f} {z:.6f} {initial_yaw:.6f} 0',actor_session=actor)
    nav=_wait_ready(player,scenario.start,actor)
    # Clearing telemetry is actor-fenced and never changes world/player physics.
    trace=player.motion_trace(reset=True,actor_session=actor)
    if trace.get('profile')!='native_player_motion_ticks_v1':raise RuntimeError('Matching telemetry-capable mod required')
    time.sleep(.12)
    return nav

def prelude(player,scenario,actor):
    if not scenario.prelude_ticks:return None
    yaw=scenario.prelude_yaw if scenario.prelude_yaw is not None else _yaw(scenario.start,scenario.target)
    player.look(yaw,0,actor_session=actor);player.drive(_mode_buttons(scenario.mode),min(100,scenario.prelude_ticks+12),wait=False,actor_session=actor)
    time.sleep(scenario.prelude_ticks*.05)
    nav=player.navigation(terrain=True)
    player.motion_trace(reset=True,actor_session=actor);time.sleep(.06)
    return {'position':nav['position'],'velocity':nav.get('velocity'),'horizontal_speed':nav.get('horizontal_speed'),'yaw':yaw}

def settle(player,actor,timeout=3.):
    player.stop();end=time.monotonic()+timeout;stable=0
    while time.monotonic()<end:
        nav=player.navigation(terrain=True)
        if nav.get('actor_session')!=actor:raise RuntimeError('Actor replaced while settling')
        if nav.get('horizontal_speed',1)<.004 and nav.get('on_ground'):
            stable+=1
            if stable>=3:return nav
        else:stable=0
        time.sleep(.05)
    return player.navigation(terrain=True)

def native_baseline(player,scenario,actor):
    """Hardcoded ordinary W + native mode/jump keys and bounded regular yaw changes."""
    buttons=_mode_buttons(scenario.mode,scenario.jump);waypoints=list(scenario.path);index=0
    end=time.monotonic()+scenario.max_ticks*.05;renew=0.;best=math.inf;worsening=0;status='blocked';reason='tick_budget'
    while time.monotonic()<end:
        nav=player.navigation(terrain=True);position=nav['position']
        if nav.get('actor_session')!=actor:raise RuntimeError('Actor replaced during native baseline')
        waypoint=waypoints[index];distance=math.dist((position[0],position[2]),(waypoint[0],waypoint[2]))
        brake_window=max(.65 if index==len(waypoints)-1 else .45,scenario.arrival_radius)
        if distance<=brake_window and abs(position[1]-waypoint[1])<=1.5:
            if index<len(waypoints)-1:
                index+=1;best=math.inf;worsening=0
                if scenario.baseline_stop_waypoints:
                    player.stop();time.sleep(.12)
                    for _ in range(24):
                        current=player.observe()['yaw'];wanted=_yaw(player.observe()['position'],waypoints[index]);delta=yaw_delta(wanted,current)
                        player.look((current+max(-8.,min(8.,delta))+180)%360-180,0,actor_session=actor)
                        if abs(delta)<=8.:break
                        time.sleep(.05)
                    renew=0.
                continue
            status='succeeded';reason='native_w_brake_window';break
        if index==len(waypoints)-1:
            if distance<best-.01:best=distance;worsening=0
            else:worsening+=1
            if best<.8 and worsening>=3:status='blocked';reason='native_w_overshot_target';break
        wanted=_yaw(position,waypoint);current=player.observe()['yaw'];delta=yaw_delta(wanted,current)
        player.look((current+max(-8.,min(8.,delta))+180)%360-180,0,actor_session=actor)
        now=time.monotonic()
        if now>=renew:
            player.drive(buttons,8,wait=False,actor_session=actor);renew=now+.18
        time.sleep(.035)
    final=settle(player,actor);return {'status':status,'reason':reason,'final_navigation':final}

def blockwire_controller(player,scenario,actor,progress):
    from blockwire.skills import default_registry,run_skill
    params={'x':scenario.target[0],'y':scenario.target[1],'z':scenario.target[2],
      'terrain':scenario.terrain,'movement':MODES[scenario.mode],'arrival_radius':scenario.arrival_radius,
      'avoid_damage':True,'timeout_seconds':min(120.,scenario.max_ticks*.05+8.)}
    result=run_skill(default_registry(),player,'walk_to',params,publish=progress.append)
    final=settle(player,actor);return {'status':result.status,'reason':result.reason,'cleanup':result.cleanup,
      'details':result.details,'final_navigation':final,'parameters':params}

def one(player,scenario,variant,index,directory,actor):
    before=reset(player,scenario,actor);runup=prelude(player,scenario,actor);progress=[];started=time.monotonic()
    try:
        outcome=native_baseline(player,scenario,actor) if variant=='vanilla' else blockwire_controller(player,scenario,actor,progress)
    except BaseException as error:
        try:settle(player,actor)
        finally:outcome={'status':'error','reason':type(error).__name__+': '+str(error)[:1024]}
    trace=player.motion_trace(limit=4096,actor_session=actor);samples=trace['samples']
    if any(s.get('actor_session')!=actor for s in samples):raise RuntimeError('Mixed actor telemetry')
    acceptance=scenario.baseline_acceptance_radius if variant=='vanilla' else scenario.arrival_radius
    metrics=analyse(samples,scenario.target,result_status=outcome['status'],arrival_radius=acceptance)
    metrics['acceptance_radius']=acceptance
    row={'scenario':scenario.document(),'variant':variant,'repeat':index,'administrative_start':before,
      'measured_prelude_state':runup,'outcome':outcome,'metrics':metrics,'elapsed_seconds':time.monotonic()-started,
      'trace_profile':trace['profile'],'trace_dropped_samples':trace['dropped_samples']}
    stem=directory/f'{scenario.name}-{index:02d}';_atomic(stem.with_suffix('.json'),row)
    stem.with_suffix('.csv').write_text(csv_text(samples));return row

def cleanup_close(player):
    """Administrative cleanup only; a death remains a failed measured run."""
    scene=player.observe()
    if not scene.get('alive'):
        player.respawn(actor_session=scene['actor_session'])
        for _ in range(200):
            scene=player.observe()
            if scene.get('alive'):break
            time.sleep(.05)
        else:raise RuntimeError('Dead benchmark actor could not be cleaned up')
        if player.menu().get('screen_open'):
            try:player.menu_key(player.menu()['screen_id'],'escape')
            except Exception:pass
        time.sleep(.1)
    close(player)

def run(player,args):
    private=Path(args.private);manifest=validate(private/'baseline');root=private.parent;run_dir=root/args.run_id
    if run_dir.exists():raise ValueError('Unique movement run ID required')
    if shutil.disk_usage(private).free<256*1024*1024:raise RuntimeError('Insufficient free storage before native action')
    run_dir.mkdir(parents=True,mode=0o700);world=Path(args.saves)/DIRECTORY
    chosen=selected(args.scenario);source_paths=[Path('python/src/blockwire/skills/motion.py'),Path('python/src/blockwire/skills/walking.py'),Path('src/main/java/dev/blockwire/NavigationView.java'),Path('src/main/java/dev/blockwire/MotionTrace.java')]
    metadata={'run_id':args.run_id,'variant':args.variant,'fixture_identity':manifest['identity'],'scenario_identity':digest(),
      'minecraft_version':'26.3','source_sha256':{str(p):sha(p) for p in source_paths},'scenario_names':[s.name for s in chosen],
      'repeat_policy':'Scenario-declared fixed repetitions; failures retained','llm_calls':0,'administrative_commands_only_before_each_measurement':True}
    _atomic(run_dir/'metadata.json',metadata);restore(private/'baseline',world,run_dir/'previous-closed-world',lambda:title(player))
    load_events=[];scene=load(player,audit=lambda e:load_events.append(e));_atomic(run_dir/'load-events.json',load_events)
    actor=scene['actor_session'];rows=[]
    try:
        # Capability check before the first movement effect.
        player.motion_trace(limit=1,reset=True,actor_session=actor)
        for scenario in chosen:
            count=args.repeats if args.repeats is not None else scenario.repeats
            for index in range(1,count+1):
                row=one(player,scenario,args.variant,index,run_dir,actor);rows.append(row)
                print(json.dumps({'scenario':scenario.name,'repeat':index,'variant':args.variant,'success':row['metrics']['success'],
                  'ticks':row['metrics']['game_ticks'],'error':row['metrics']['target_horizontal_error'],'reason':row['outcome']['reason']}),flush=True)
                if row['metrics']['end_position'][1] < 58. or (row.get('outcome',{}).get('final_navigation',{}).get('alive') is False):
                    raise RuntimeError('Critical fall/death stops the suite after retaining the run')
    finally:
        player.stop();cleanup_close(player)
    by_scenario={}
    for scenario in chosen:by_scenario[scenario.name]=aggregate([r for r in rows if r['scenario']['name']==scenario.name])
    summary={'metadata':metadata,'runs':len(rows),'successes':sum(r['metrics']['success'] for r in rows),
      'success_rate':sum(r['metrics']['success'] for r in rows)/len(rows) if rows else 0,'scenarios':by_scenario}
    _atomic(run_dir/'summary.json',summary);capture(world,run_dir/'ended-world',lambda:title(player));return summary
