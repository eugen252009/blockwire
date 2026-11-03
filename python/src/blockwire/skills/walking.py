"""Receding-horizon flat walking using explicit client-known native collision edges."""
from __future__ import annotations

from typing import Literal
import heapq
import math
from pydantic import Field, model_validator
from .core import SkillContext, SkillDefinition, SkillParameters, SkillResult


class WalkTo(SkillParameters):
    x: float = Field(ge=-29_999_984, le=29_999_984, description="World X, not a relative offset.")
    y: float = Field(ge=-2048, le=2048, description="Feet Y. Different levels require terrain=True and observed one-block step edges.")
    z: float = Field(ge=-29_999_984, le=29_999_984, description="World Z, not a relative offset.")
    terrain: bool = Field(default=False, description='Opt in to bounded full-block one-block climbs/descents; no slabs, fluids or gaps.')
    arrival_radius: float = Field(default=.3,ge=.08,le=.3,description='Observed horizontal arrival radius. Native placement adapters may request tighter centering; ordinary walking retains 0.3 blocks.')
    sneak: bool = False
    movement: Literal['walk','run','sneak'] = 'walk'
    avoid_damage: bool = Field(default=True, description="Conservative known-hazard avoidance, NOT immunity. Sneaking is controlled separately.")
    recorded_yaw: float | None = Field(default=None,ge=-180,le=180,description='Optional local-human view yaw paired with recorded_buttons for one bounded checkpoint pulse.')
    recorded_pitch: float | None = Field(default=None,ge=-90,le=90,description='Optional local-human view pitch paired with recorded_buttons.')
    recorded_direction: Literal['forward','back','left','right','forward_left','forward_right','back_left','back_right','hold'] | None = Field(default=None,description='Optional exact local-human movement direction combination for this grounded checkpoint; hold preserves crouch without directional input.')

    @model_validator(mode='after')
    def recorded_control_contract(self):
        supplied=(self.recorded_yaw is not None,self.recorded_pitch is not None,self.recorded_direction is not None)
        if any(supplied) and not all(supplied):raise ValueError('recorded yaw, pitch and direction must be supplied together')
        return self


def route(mesh: dict, target: tuple[float, float, float], avoid_damage: bool):
    """Shortest cardinal path to target cell or a strictly closer visible frontier."""
    cells = mesh["cells"]
    positions = [tuple(cell["position"]) for cell in cells]
    allowed = {i for i, cell in enumerate(cells) if not (avoid_damage and cell["hazards"])}
    source = tuple(mesh["current_cell"])
    if source not in positions or positions.index(source) not in allowed:
        return None
    start = positions.index(source)
    stepped = mesh.get("profile") == "stepped_full_blocks_v1"
    destination = (math.floor(target[0]), round(target[1]) if stepped else source[1], math.floor(target[2]))
    adjacency = {i: [] for i in allowed}
    for a, b in mesh["edges"]:
        if a in allowed and b in allowed:
            adjacency[a].append(b)
            adjacency[b].append(a)
    previous = {start: None}
    costs = {start: 0.}
    serial = 0
    queue = [(0., serial, start)]
    while queue:
        cost, _, current = heapq.heappop(queue)
        if cost > costs[current]:
            continue
        a = positions[current]
        for neighbor in adjacency[current]:
            b = positions[neighbor]
            edge_cost = math.sqrt((a[0]-b[0])**2+(a[1]-b[1])**2+(a[2]-b[2])**2)
            candidate = cost+edge_cost
            if candidate < costs.get(neighbor, math.inf)-1e-9:
                costs[neighbor] = candidate
                previous[neighbor] = current
                serial += 1  # Preserve native edge discovery order for equal-cost paths.
                heapq.heappush(queue, (candidate, serial, neighbor))
    def distance(index):
        p = positions[index]
        return math.sqrt((p[0]+.5-target[0])**2+(p[2]+.5-target[2])**2+((p[1]-target[1])**2 if stepped else 0))
    if destination in positions:
        end = positions.index(destination)
        if end not in previous:
            return None
    else:
        end = min(previous, key=distance)
        if end == start or distance(end) >= distance(start):
            return None
    path = [end]
    while previous[path[-1]] is not None:
        path.append(previous[path[-1]])
    return [positions[index] for index in reversed(path)]


def walk_to(context: SkillContext, goal: WalkTo, *, expected_session=None) -> SkillResult:
    from .crafting import ensure_gameplay
    if not (goal.sneak or goal.movement=='sneak'):context.release_retained_sneak()
    ensure_gameplay(context)
    target = (goal.x, goal.y, goal.z)
    session, health, initial = None, None, None
    previous_position = None
    arrival_sample = None
    stationary = 0
    steps = 0
    recorded_steps=0;recorded_best=None
    from .motion import FlatMotion  # Local import: the motor also consumes route().
    motion = FlatMotion()
    effective_sneak = goal.sneak or goal.movement=='sneak'

    def blocked(reason, state):
        return SkillResult(status="blocked", reason=reason, text="Walk stopped: " + reason.replace("_", " "),
                           details={"target": target, "last_observation": state, "steps": steps})

    while True:
        context.check()
        state = context.player.navigation(terrain=True) if goal.terrain else context.player.navigation()
        context.check()
        if state.get("profile") != ("stepped_full_blocks_v1" if goal.terrain else "flat_full_blocks_v1"):
            return blocked("unsupported_navigation_profile", state)
        if not state.get("ready"):
            return blocked(state.get("reason", "navigation_not_ready"), state)
        if expected_session is not None and state.get("actor_session") != expected_session:
            return blocked("actor_session_changed", state)
        if session is None:
            session, health, initial = state["actor_session"], state["health"], state["position"]
            if math.dist((initial[0], initial[2]), (goal.x, goal.z)) > 64:
                return blocked("target_out_of_range_64_blocks", state)
        if session != state["actor_session"]:
            return blocked("actor_session_changed", state)
        if not goal.terrain and abs(state["position"][1] - goal.y) > .2:
            return blocked("vertical_route_unsupported", state)
        if goal.avoid_damage:
            if state["health"] < health:
                return blocked("damage_observed", state)
            current_hazards = next((c["hazards"] for c in state["cells"]
                                    if c["position"] == state["current_cell"]), [])
            if state.get("on_fire") or state.get("nearby_hostiles") or current_hazards:
                return blocked("known_danger_nearby", state)
        position = state["position"]
        distance = math.hypot(position[0] - goal.x, position[2] - goal.z)
        if distance <= goal.arrival_radius and abs(position[1]-goal.y) <= .2:
            if motion.holding:
                motion.halt(context,preserve_sneak=motion.sneak_stance)
                context.pause(.2)
                continue  # Observe arrival again after releasing native forward input.
            if motion.sneak_stance:
                context.check();context.player.drive(['sneak'],8,wait=False,actor_session=session)
            # A released input lease is not zero native velocity. Every radius, including
            # ordinary 0.3-block walking, requires observed settling before success.
            if float(state.get("horizontal_speed",0.)) > .004:
                context.pause(.1)
                continue
            if arrival_sample is None or math.dist(position,arrival_sample) > .005:
                arrival_sample = position[:]
                context.pause(.2)
                continue
            return SkillResult(status="succeeded", reason="arrived", text="Reached the requested walking radius.",
                details={"position": position, "target": target, "distance": distance, "steps": steps,
                         "effective_sneak": effective_sneak, "avoid_damage_is_best_effort": True})
        arrival_sample = None
        if previous_position is not None and math.dist(position, previous_position) < .015:
            stationary += 1
        else:
            stationary = 0
            previous_position = position[:]  # Accumulate small feedback advances.
        if stationary >= 12:
            return blocked("stuck", state)
        context.check()
        scene = context.player.observe()
        context.check()
        if not scene.get("in_world") or not scene.get("alive"):
            return blocked("scene_not_ready", state)
        if goal.recorded_direction is not None:
            if state.get('on_ground') is not True:return blocked('recorded_checkpoint_not_grounded',state)
            if distance>.6:return blocked('recorded_checkpoint_too_far',state)
            if recorded_best is None:recorded_best=distance
            elif distance>recorded_best+.08:return blocked('recorded_checkpoint_diverged',state)
            else:recorded_best=min(recorded_best,distance)
            if recorded_steps>=3:return blocked('recorded_checkpoint_not_reached',state)
            wanted_yaw,wanted_pitch=goal.recorded_yaw,goal.recorded_pitch
            if abs((wanted_yaw-scene['yaw']+180)%360-180)>.25 or abs(wanted_pitch-scene['pitch'])>.25:
                context.player.look(wanted_yaw,wanted_pitch,actor_session=session,duration_ms=200,rotation_profile='smoothstep')
                for _ in range(6):
                    context.check();context.pause(.05);fresh=context.player.observe();context.check()
                    if fresh.get('actor_session',session)!=session:return blocked('actor_session_changed',state)
                    if not fresh.get('in_world') or not fresh.get('alive'):return blocked('scene_not_ready',state)
                    if abs((wanted_yaw-fresh['yaw']+180)%360-180)<=.25 and abs(wanted_pitch-fresh['pitch'])<=.25:break
                else:return blocked('recorded_view_not_reached',state)
            buttons=goal.recorded_direction.split('_')
            if effective_sneak:buttons.append('sneak')
            elif goal.movement=='run':buttons.append('sprint')
            context.check();context.player.drive(buttons,1,wait=False,actor_session=session)
            context.pause(.08);context.check();context.player.stop();context.pause(.05)
            recorded_steps+=1;steps+=1;previous_position=None;stationary=0
            continue
        context.publish({"position": position, "target": target, "distance": distance, "steps": steps,
                         "effective_sneak": effective_sneak, "control_mode": motion.mode,
                         "owned_input_lease": motion.holding})
        result = motion.pulse(context, state, target, "sneak" if effective_sneak else goal.movement,
                              avoid_damage=goal.avoid_damage, max_ticks=3,
                              view=(scene["yaw"], scene["pitch"]), continuous=True, precision_sneak=False,
                              arrival_radius=goal.arrival_radius)
        if result is not None:
            return result
        if motion.turning:
            previous_position = None
            stationary = 0
            continue
        steps += 1


def _validate_recorded_move(row):
    if len(row)!=6 or any(type(value) not in (int,float) or not math.isfinite(value) for value in row):
        raise ValueError('recorded path samples must contain six finite numbers')
    x,y,z,yaw,pitch,code=row
    if not -29_999_984<=x<=29_999_984 or not -2048<=y<=2048 or not -29_999_984<=z<=29_999_984:
        raise ValueError('recorded path point outside world bounds')
    if not -180<=yaw<=180 or not -90<=pitch<=90 or type(code) is not int or not 0<=code<=8:
        raise ValueError('recorded path view or direction code is invalid')


class RecordedPath(SkillParameters):
    samples:list[list[int|float]]=Field(min_length=2,max_length=32,description='Ordered [x,y,z,yaw,pitch,direction_code] samples from one sealed grounded crouch segment.')
    arrival_radius:float=Field(default=.3,ge=.08,le=.3)
    avoid_damage:bool=True

    @model_validator(mode='after')
    def sample_contract(self):
        for index,row in enumerate(self.samples):
            _validate_recorded_move(row)
            if index and math.dist(self.samples[index-1][:3],row[:3])>.6:
                raise ValueError('recorded path samples must remain locally contiguous')
        return self


class RecordedDrop(SkillParameters):
    edge:list[int|float]=Field(min_length=3,max_length=3,description='Sealed grounded step-off point.')
    landing:list[int|float]=Field(min_length=3,max_length=3,description='First sealed grounded landing point after the native fall.')
    yaw:float=Field(ge=-180,le=180)
    pitch:float=Field(ge=-90,le=90)
    direction:Literal['forward','back','left','right']
    avoid_damage:bool=True

    @model_validator(mode='after')
    def drop_contract(self):
        for point in (self.edge,self.landing):
            if any(type(value) not in (int,float) or not math.isfinite(value) for value in point):
                raise ValueError('recorded drop points must contain finite numbers')
            if not -29_999_984<=point[0]<=29_999_984 or not -2048<=point[1]<=2048 or not -29_999_984<=point[2]<=29_999_984:
                raise ValueError('recorded drop point outside world bounds')
        height=float(self.edge[1])-float(self.landing[1])
        if not 2.<=height<=4. or math.hypot(float(self.edge[0])-float(self.landing[0]),float(self.edge[2])-float(self.landing[2]))>.75:
            raise ValueError('recorded drop must be one bounded local native descent')
        return self


class RecordedSequence(SkillParameters):
    events:list[list[int|float|str]]=Field(min_length=3,max_length=40,description='Ordered sealed events: [0,x,y,z,yaw,pitch,direction_code] movement or [1,block,sx,sy,sz,face_code,qx,qy,qz,rx,ry,rz] crouched placement.')
    arrival_radius:float=Field(default=.3,ge=.08,le=.3)
    avoid_damage:bool=True

    @model_validator(mode='after')
    def event_contract(self):
        moves=[];placements=0;previous=None
        for row in self.events:
            if not row or type(row[0]) is not int:raise ValueError('recorded sequence event type is invalid')
            if row[0]==0:
                if len(row)!=7:raise ValueError('recorded sequence movement event is invalid')
                _validate_recorded_move(row[1:]);point=row[1:4]
                if previous is not None and math.dist(previous,point)>.6:
                    raise ValueError('recorded sequence movement events must remain locally contiguous')
                previous=point;moves.append(row)
            elif row[0]==1:
                if len(row)!=12 or type(row[1]) is not str or not row[1].startswith('minecraft:'):
                    raise ValueError('recorded sequence placement event is invalid')
                if any(type(value) is not int for value in row[2:5]) or type(row[5]) is not int or not 0<=row[5]<=5:
                    raise ValueError('recorded sequence support or face is invalid')
                if any(type(value) not in (int,float) or not math.isfinite(value) for value in row[6:]):
                    raise ValueError('recorded sequence pose or aim is invalid')
                if previous is None or math.dist(previous,row[6:9])>.6:
                    raise ValueError('recorded sequence placement is not contiguous with movement evidence')
                placements+=1
            else:raise ValueError('recorded sequence event type is invalid')
        if len(moves)<2 or placements<1 or placements>8 or self.events[0][0]!=0 or self.events[-1][0]!=0:
            raise ValueError('recorded sequence requires bounded movement around placements')
        return self


def _replay_recorded_events(context,events,arrival_radius,avoid_damage):
    from .crafting import ensure_gameplay
    ensure_gameplay(context)
    directions={0:['forward'],1:['back'],2:['left'],3:['right'],4:['forward','left'],
                5:['forward','right'],6:['back','left'],7:['back','right'],8:[]}
    faces={0:'up',1:'down',2:'north',3:'south',4:'east',5:'west'}
    session=None;health=None;last=None;sample_index=0;placements=0
    def fail(reason,**details):
        return SkillResult(status='blocked',reason=reason,text='Recorded path stopped: '+reason.replace('_',' '),details=details)
    try:
        for event_index,event in enumerate(events):
            if event[0]==1:
                from .item_actions import PlaceBlock,place_block
                settled=None
                for _ in range(6):
                    context.check();sample=context.player.navigation();context.check()
                    if sample.get('actor_session')!=session:return fail('actor_session_changed',event=event_index)
                    if sample.get('on_ground') is not True:return fail('recorded_path_lost_ground',event=event_index,position=sample.get('position'))
                    if avoid_damage and (sample.get('health',health)<health or sample.get('on_fire') or sample.get('nearby_hostiles')):
                        return fail('damage_or_known_danger_observed',event=event_index)
                    if float(sample.get('horizontal_speed',0.))<=.004:
                        if settled is not None and math.dist(sample['position'],settled)<=.005:break
                        settled=sample['position'][:]
                    else:settled=None
                    context.check();context.player.drive(['sneak'],8,wait=False,actor_session=session);context.pause(.1)
                else:return fail('recorded_path_not_settled',event=event_index)
                _,block,sx,sy,sz,face,qx,qy,qz,rx,ry,rz=event
                context.check();context.player.drive(['sneak'],8,wait=False,actor_session=session)
                result=place_block(context,PlaceBlock(block=block,support=[sx,sy,sz],face=faces[face],auto_position=True,
                    recorded_pose=[qx,qy,qz],recorded_aim=[rx,ry,rz],recorded_sneak=True,clear_plants=False),
                    expected_session=session,preserve_recorded_sneak=True)
                if result.status!='succeeded' or result.reason!='block_placed':return result
                placements+=1;context.check();context.player.drive(['sneak'],8,wait=False,actor_session=session);context.pause(.05)
                continue
            row=event[1:];target=tuple(float(value) for value in row[:3]);yaw,pitch=float(row[3]),float(row[4]);code=int(row[5]);best=None
            # A directionless sample cannot correct its own position. Require the
            # immediately preceding recorded directional tick to leave that sealed
            # hold checkpoint inside the unchanged arrival envelope. This prevents
            # dense samples from consuming the radius cumulatively and then failing
            # one tick later without inventing another input or widening tolerance.
            hold_target=None
            if code!=8 and event_index+1<len(events):
                following=events[event_index+1]
                if following[0]==0 and int(following[6])==8:
                    hold_target=tuple(float(value) for value in following[1:4])
            for attempt in range(4):
                context.check();state=context.player.navigation();context.check()
                if state.get('profile')!='flat_full_blocks_v1' or not state.get('ready'):
                    return fail(state.get('reason','navigation_not_ready'),sample=sample_index,event=event_index,
                                position=state.get('position'),horizontal_speed=state.get('horizontal_speed'),on_ground=state.get('on_ground'))
                if session is None:session=state.get('actor_session');health=state.get('health')
                if state.get('actor_session')!=session:return fail('actor_session_changed',sample=sample_index)
                if state.get('on_ground') is not True:return fail('recorded_path_not_grounded',sample=sample_index,position=state.get('position'))
                if avoid_damage and (state.get('health',health)<health or state.get('on_fire') or state.get('nearby_hostiles')):
                    return fail('damage_or_known_danger_observed',sample=sample_index)
                position=state['position'];distance=math.hypot(position[0]-target[0],position[2]-target[2]);last=(target,sample_index)
                hold_distance=None if hold_target is None else math.hypot(position[0]-hold_target[0],position[2]-hold_target[2])
                completion_distance=max(distance,hold_distance) if hold_distance is not None else distance
                if completion_distance<=arrival_radius:
                    context.check();context.player.drive(['sneak'],8,wait=False,actor_session=session)
                    context.pause(.2 if code==8 else .06)
                    break
                if completion_distance>.65:return fail('recorded_path_sample_too_far',sample=sample_index,distance=distance,
                    completion_distance=completion_distance,position=position,target=target,hold_target=hold_target)
                if best is None:best=completion_distance
                elif completion_distance>best+.08:return fail('recorded_path_diverged',sample=sample_index,distance=distance,
                    completion_distance=completion_distance,best=best,position=position,target=target,hold_target=hold_target)
                else:best=min(best,completion_distance)
                if attempt==3:
                    for _ in range(4):
                        context.check();context.pause(.05);coast=context.player.navigation();context.check()
                        if coast.get('profile')!='flat_full_blocks_v1' or not coast.get('ready'):
                            return fail(coast.get('reason','navigation_not_ready'),sample=sample_index,event=event_index,
                                        position=coast.get('position'),horizontal_speed=coast.get('horizontal_speed'),on_ground=coast.get('on_ground'))
                        if coast.get('actor_session')!=session:return fail('actor_session_changed',sample=sample_index)
                        if coast.get('on_ground') is not True:return fail('recorded_path_not_grounded',sample=sample_index,position=coast.get('position'))
                        if avoid_damage and (coast.get('health',health)<health or coast.get('on_fire') or coast.get('nearby_hostiles')):
                            return fail('damage_or_known_danger_observed',sample=sample_index)
                        position=coast['position'];distance=math.hypot(position[0]-target[0],position[2]-target[2])
                        hold_distance=None if hold_target is None else math.hypot(position[0]-hold_target[0],position[2]-hold_target[2])
                        completion_distance=max(distance,hold_distance) if hold_distance is not None else distance
                        if completion_distance<=arrival_radius:break
                        if best is not None and completion_distance>best+.08:
                            return fail('recorded_path_diverged',sample=sample_index,distance=distance,
                                        completion_distance=completion_distance,best=best,position=position,target=target,hold_target=hold_target)
                        best=completion_distance if best is None else min(best,completion_distance)
                    else:return fail('recorded_path_sample_not_reached',sample=sample_index,distance=distance,
                                     completion_distance=completion_distance,position=position,target=target,hold_target=hold_target)
                    break
                context.check();scene=context.player.observe();context.check()
                if scene.get('actor_session',session)!=session or not scene.get('in_world') or not scene.get('alive'):
                    return fail('actor_session_changed',sample=sample_index)
                context.player.drive(['sneak'],8,wait=False,actor_session=session)
                if abs((yaw-scene['yaw']+180)%360-180)>.25 or abs(pitch-scene['pitch'])>.25:
                    context.check();context.player.look(yaw,pitch,actor_session=session,duration_ms=200,rotation_profile='smoothstep')
                    for _ in range(6):
                        context.check();context.pause(.05);fresh=context.player.observe();context.check()
                        if fresh.get('actor_session',session)!=session:return fail('actor_session_changed',sample=sample_index)
                        if abs((yaw-fresh['yaw']+180)%360-180)<=.25 and abs(pitch-fresh['pitch'])<=.25:break
                    else:return fail('recorded_view_not_reached',sample=sample_index)
                buttons=directions[code]+['sneak'];leases={button:1 for button in directions[code]};leases['sneak']=8
                context.check();context.player.drive(buttons,8,wait=False,actor_session=session,button_ticks=leases);context.pause(.06)
            else:return fail('recorded_path_sample_not_reached',sample=sample_index)
            sample_index+=1
        settled=None
        for _ in range(6):
            context.check();sample=context.player.navigation();context.check()
            if sample.get('actor_session')!=session:return fail('actor_session_changed')
            if sample.get('on_ground') is not True:return fail('recorded_path_lost_ground',position=sample.get('position'))
            if float(sample.get('horizontal_speed',0.))<=.004:
                if settled is not None and math.dist(sample['position'],settled)<=.005:break
                settled=sample['position'][:]
            else:settled=None
            context.check();context.player.drive(['sneak'],8,wait=False,actor_session=session);context.pause(.1)
        else:return fail('recorded_path_not_settled')
        context.check();context.player.stop();context.pause(.12);context.check();final=context.player.navigation();context.check()
        if final.get('actor_session')!=session:return fail('actor_session_changed')
        if final.get('on_ground') is not True:return fail('recorded_path_lost_ground',position=final.get('position'))
        target,index=last;distance=math.hypot(final['position'][0]-target[0],final['position'][2]-target[2])
        if distance>arrival_radius:return fail('recorded_path_final_postcondition_failed',sample=index,distance=distance)
        return SkillResult(status='succeeded',reason='recorded_path_reached',text='Reached the sealed grounded crouch segment.',
                           details={'position':final['position'],'target':target,'samples':sample_index,'placements':placements,'distance':distance})
    finally:
        try:context.player.stop()
        except Exception:pass


def replay_recorded_drop(context:SkillContext,goal:RecordedDrop)->SkillResult:
    from .crafting import ensure_gameplay
    ensure_gameplay(context);session=None;health=None;airborne=False
    edge=tuple(float(value) for value in goal.edge);landing=tuple(float(value) for value in goal.landing)
    def fail(reason,**details):return SkillResult(status='blocked',reason=reason,text='Recorded drop stopped: '+reason.replace('_',' '),details=details)
    try:
        for pulse in range(3):
            context.check();state=context.player.navigation();context.check()
            if session is None:session=state.get('actor_session');health=state.get('health')
            if state.get('actor_session')!=session:return fail('actor_session_changed')
            if goal.avoid_damage and (state.get('health',health)<health or state.get('on_fire') or state.get('nearby_hostiles')):
                return fail('damage_or_known_danger_observed',position=state.get('position'))
            if state.get('on_ground') is not True:
                airborne=True;break
            position=state.get('position',[math.inf]*3)
            if abs(position[1]-edge[1])>.1 or math.hypot(position[0]-edge[0],position[2]-edge[2])>.4:
                return fail('recorded_drop_edge_not_reached',position=position,edge=edge)
            context.check();scene=context.player.observe();context.check()
            if scene.get('actor_session',session)!=session:return fail('actor_session_changed')
            if abs((goal.yaw-scene['yaw']+180)%360-180)>.25 or abs(goal.pitch-scene['pitch'])>.25:
                context.player.look(goal.yaw,goal.pitch,actor_session=session,duration_ms=200,rotation_profile='smoothstep')
                for _ in range(6):
                    context.check();context.pause(.05);scene=context.player.observe();context.check()
                    if scene.get('actor_session',session)!=session:return fail('actor_session_changed')
                    if abs((goal.yaw-scene['yaw']+180)%360-180)<=.25 and abs(goal.pitch-scene['pitch'])<=.25:break
                else:return fail('recorded_view_not_reached')
            context.check();context.player.drive([goal.direction],1,wait=False,actor_session=session);context.pause(.06)
        if not airborne:
            context.check();state=context.player.navigation();context.check();airborne=state.get('on_ground') is False
        if not airborne:return fail('recorded_drop_airborne_not_observed')
        context.player.stop()
        for _ in range(30):
            context.check();context.pause(.05);state=context.player.navigation();context.check()
            if state.get('actor_session')!=session:return fail('actor_session_changed')
            position=state.get('position',[math.inf]*3)
            if goal.avoid_damage and (state.get('health',health)<health or state.get('on_fire') or state.get('nearby_hostiles')):
                return fail('damage_or_known_danger_observed',position=position)
            if position[1]<landing[1]-.5 or math.hypot(position[0]-landing[0],position[2]-landing[2])>.75:
                return fail('recorded_drop_diverged',position=position,landing=landing)
            if state.get('on_ground') is True:
                context.player.stop();context.pause(.1);context.check();final=context.player.navigation();context.check()
                distance=math.dist(final.get('position',[math.inf]*3),landing)
                if final.get('actor_session')!=session:return fail('actor_session_changed')
                if final.get('on_ground') is not True or distance>.5:return fail('recorded_drop_landing_not_observed',position=final.get('position'),landing=landing,distance=distance)
                return SkillResult(status='succeeded',reason='recorded_drop_landed',text='Observed the sealed native step-off and grounded landing.',
                                   details={'position':final['position'],'target':landing,'pulses':pulse+1,'distance':distance})
        return fail('recorded_drop_landing_not_observed',position=state.get('position'),landing=landing)
    finally:
        try:context.player.stop()
        except Exception:pass


def replay_recorded_path(context:SkillContext,goal:RecordedPath)->SkillResult:
    return _replay_recorded_events(context,[[0,*row] for row in goal.samples],goal.arrival_radius,goal.avoid_damage)


def replay_recorded_sequence(context:SkillContext,goal:RecordedSequence)->SkillResult:
    return _replay_recorded_events(context,goal.events,goal.arrival_radius,goal.avoid_damage)


RECORDED_DROP=SkillDefinition('replay_recorded_drop','Replay one sealed bounded native step-off and require the recorded grounded landing. At most three exact actor-fenced one-tick directional pulses; gravity, collision and fall outcome remain native.',RecordedDrop,replay_recorded_drop)
RECORDED_PATH=SkillDefinition('replay_recorded_path','Replay one sealed grounded crouch segment using exact local-human view/direction samples. Native collision remains authoritative; every loop checks actor, ground, damage and target postconditions.',RecordedPath,replay_recorded_path)
RECORDED_SEQUENCE=SkillDefinition('replay_recorded_sequence','Replay one sealed continuous crouch sequence containing exact local-human movement and placement evidence. Controls stay leased only across the explicit sequence; every placement still requires exact support, one use, one item and the observed destination.',RecordedSequence,replay_recorded_sequence)


WALK_TO = SkillDefinition(
    "walk_to",
    "Reach a world position on known loaded flat full-block ground. Detours around native collision "
    "obstacles. Flat by default; terrain=True permits bounded one-block full-cube jumps/descents, not slabs/gaps/fluids. No chunk generation. Sneak only when requested. avoid_damage avoids known "
    "hazards/nearby hostiles and stops on health loss; never guarantees no damage. At most 64 blocks per goal.",
    WalkTo, walk_to,
)
