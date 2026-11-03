"""Feedback-driven native input motor. Native Minecraft still owns physics and collision."""
from __future__ import annotations

import math
from .core import SkillResult
from .walking import route


LEASE_TICKS = 8             # 400 ms fail-safe, not a gameplay completion guarantee.
UPDATE_SECONDS = .05        # Observe/revalidate before renewing; never blindly refresh input.
STEERING_DEGREES = 8.  # Legacy non-navigation users retain the bounded step helper below.
ROTATION_DURATION_MS = 200
ROTATION_PROFILE = "smoothstep"
ROTATION_TOLERANCE = .25
MOVING_SPEED = .01


def _blocked(reason,**details):
    return SkillResult(status="blocked", reason=reason, text="Motion stopped: " + reason.replace("_", " "),details=details)


def _yaw_delta(target, current):
    return (target-current+180) % 360-180



def rotate_view_timed(context, view, wanted, session, *, duration_ms=ROTATION_DURATION_MS,
                      profile=ROTATION_PROFILE):
    """Schedule one idempotent native rotation; completion remains an observed postcondition."""
    dyaw,dpitch=_yaw_delta(wanted[0],view[0]),max(-90.,min(90.,wanted[1]))-view[1]
    if max(abs(dyaw),abs(dpitch))<=ROTATION_TOLERANCE:return False
    context.check()
    context.player.look((wanted[0]+180)%360-180,max(-90.,min(90.,wanted[1])),actor_session=session,
                        duration_ms=duration_ms,rotation_profile=profile)
    context.pause(UPDATE_SECONDS)
    return True


def travel_inputs(motion_yaw, current_yaw, distance):
    """Quantize a desired world vector into ordinary W/A/S/D while the view turns."""
    delta = _yaw_delta(motion_yaw, current_yaw)
    magnitude = abs(delta)
    side = "left" if delta < 0 else "right"
    if magnitude <= 22.5:
        buttons = ("forward",)
    elif magnitude <= 67.5:
        buttons = ("forward", side)
    elif magnitude <= 112.5:
        buttons = (side,)
    elif magnitude <= 157.5:
        buttons = ("back", side)
    else:
        buttons = ("back",)
    return (motion_yaw+180) % 360-180, buttons


def _straight_ahead(path, position):
    """A loaded, collision-connected collinear chain; never shortcut a corner/unknown edge."""
    if len(path) < 3:
        return None
    dx, dz = path[1][0]-path[0][0], path[1][2]-path[0][2]
    if max(abs(dx),abs(dz)) != 1 or not (dx or dz) or path[1][1] != path[0][1]:
        return None
    lateral = abs((position[0]-path[0][0]-.5)*dz-(position[2]-path[0][2]-.5)*dx)/math.hypot(dx,dz)
    if lateral > .18:
        return None
    end = 1
    for i in range(2, min(len(path), 5)):
        if (path[i][0]-path[i-1][0], path[i][2]-path[i-1][2]) != (dx, dz) or path[i][1] != path[0][1]:
            break
        end = i
    if end < 2:
        return None
    return (path[end][0]+.5, path[end][1], path[end][2]+.5), (dx, dz)


def _broad_steering_support(state,source,direction):
    """Prove lateral standing cells before combining a large turn with movement."""
    if direction is None:return False
    dx=1 if direction[0]>0 else -1 if direction[0]<0 else 0
    dz=1 if direction[1]>0 else -1 if direction[1]<0 else 0
    if not (dx or dz):return False
    lateral=(-dz,dx);y=source[1]
    cells={tuple(row["position"]) for row in state.get("cells",[]) if not row.get("hazards")}
    forward=(source[0]+dx,y,source[2]+dz)
    return all((base[0]+sign*lateral[0],y,base[2]+sign*lateral[1]) in cells
               for base in (source,forward) for sign in (-1,1))


def _supported_sneak_edge_pose(state, target, avoid_damage):
    """Allow one tiny native sneak pulse while the target body still overlaps the current support."""
    if state.get('on_ground', True) is not True:
        return False
    position = state['position'];cell = tuple(state['current_cell'])
    if abs(position[1] - target[1]) > .2 or math.hypot(position[0] - target[0], position[2] - target[2]) > .45:
        return False
    support = next((row for row in state.get('cells', ()) if tuple(row.get('position', ())) == cell), None)
    if support is None or (avoid_damage and support.get('hazards')):
        return False
    if abs(target[0] - cell[0] - .5) > .8 or abs(target[2] - cell[2] - .5) > .8:
        return False
    half = .3
    overlap_x = max(0., min(target[0] + half, cell[0] + 1.) - max(target[0] - half, cell[0]))
    overlap_z = max(0., min(target[2] + half, cell[2] + 1.) - max(target[2] - half, cell[2]))
    return min(overlap_x, overlap_z) >= .0001 and max(overlap_x, overlap_z) >= .25


def _observed_sneak_pose(state):
    """Native stance proof, not an input receipt or a placement postcondition."""
    position,eye=state.get('position',()),state.get('eye_position',())
    return (state.get('on_ground') is True and state.get('sneaking') is True
            and len(position)==3 and len(eye)==3 and 0.<eye[1]-position[1]<=1.27+1e-5)


def _edge_kind(state, source, destination):
    """Read one native edge annotation; old fixtures retain conservative inference."""
    positions=[tuple(c["position"]) for c in state["cells"]]
    try: pair={positions.index(tuple(source)),positions.index(tuple(destination))}
    except ValueError: return None
    for transition in state.get("transitions",()):
        if {transition.get("a"),transition.get("b")}==pair:return transition.get("kind")
    dx,dz=abs(destination[0]-source[0]),abs(destination[2]-source[2])
    if abs(destination[1]-source[1])==1 and dx+dz==1:return "step"
    if destination[1]==source[1] and max(dx,dz)==1:return "diagonal" if dx and dz else "flat"
    return None


class FlatMotion:
    """Shared actor-fenced motor: roll on known straight segments, precision pulses elsewhere."""
    def __init__(self):
        self.pending = self.departed = None
        self._waypoint = None
        self._best_distance = math.inf
        self._no_progress = 0
        self.turning = False
        self.holding = False  # Ownership intent, NOT an observation of native key state/outcome.
        self.mode = "stopped"
        self.lease_ticks = 0
        self._buttons = ()
        self._direction = None
        self._session = None
        self._gap_runup = None
        self._sample_position = None
        self._sample_time = None
        self._peak_step = 0.
        self.sneak_stance = False  # Owned only by this motor's enclosing skill.
        self._pose_waits = 0

    def halt(self, context, *, preserve_sneak=False):
        context.check()
        if preserve_sneak and self._session is not None:
            context.player.drive(['sneak'], LEASE_TICKS, wait=False, actor_session=self._session)
            self.sneak_stance = True
        else:
            context.player.stop()
            self.sneak_stance = False
        self.holding = False
        self._buttons, self._direction = (), None
        self.mode, self.lease_ticks = "stopped", 0

    def _fail(self, context, reason, **details):
        if self.holding or self.sneak_stance:
            self.halt(context)
        self._gap_runup = None
        return _blocked(reason,**details)


    def step(self, context, state, destination, view, avoid_damage):
        """Execute ONE observed mesh edge, not a jump simulator or a new planner."""
        source = tuple(state["current_cell"])
        if abs(destination[1]-source[1]) != 1 or abs(destination[0]-source[0])+abs(destination[2]-source[2]) != 1:
            return self._fail(context, "unsupported_step")
        indices = {tuple(c["position"]): i for i,c in enumerate(state["cells"])}
        pair = {indices.get(source), indices.get(destination)}
        if None in pair or not any(set(e)==pair for e in state["edges"]):
            return self._fail(context, "step_edge_not_observed")
        session, health = state["actor_session"], state["health"]
        yaw = math.degrees(math.atan2(source[0]-destination[0], destination[2]-source[2]))
        if rotate_view_timed(context, view, (yaw, 0.), session):
            self.turning = True
            return None  # Revalidate geometry after every stopped turn.
        context.check()
        fresh = context.player.navigation(terrain=True)
        if fresh.get("actor_session") != session:
            return self._fail(context, "actor_session_changed")
        if not fresh.get("ready") or fresh["current_cell"] != list(source):
            return self._fail(context, "step_source_changed")
        fresh_indices = {tuple(c["position"]):i for i,c in enumerate(fresh["cells"])}
        pair = {fresh_indices.get(source), fresh_indices.get(destination)}
        if None in pair or not any(set(e)==pair for e in fresh["edges"]):
            return self._fail(context, "step_edge_changed")
        if avoid_damage and (fresh["health"]<health or fresh.get("on_fire") or fresh.get("nearby_hostiles") or
                             any(c["hazards"] for c in fresh["cells"] if tuple(c["position"]) in {source,destination})):
            return self._fail(context, "known_danger_nearby")
        end, started = context.clock()+2., False
        while context.clock() < end:
            context.check()
            s = context.player.navigation(terrain=True)
            if s.get("actor_session") != session:
                return self._fail(context, "actor_session_changed")
            if not s.get("alive") or (avoid_damage and (s["health"]<health or s.get("on_fire") or s.get("nearby_hostiles"))):
                return self._fail(context, "damage_or_death_observed")
            if not s.get("ready") and s.get("reason") != "not_grounded":
                return self._fail(context, s.get("reason", "step_not_ready"))
            p = s["position"]
            if abs(p[1]-source[1])>1.5 or math.hypot(p[0]-source[0]-.5,p[2]-source[2]-.5)>1.6:
                return self._fail(context, "step_left_verified_envelope")
            distance = math.hypot(p[0]-destination[0]-.5,p[2]-destination[2]-.5)
            if started and s.get("ready") and tuple(s.get("current_cell", [])) == tuple(destination) and abs(p[1]-destination[1])<.1:
                self.halt(context)
                context.pause(.15)
                return None  # Caller verifies fresh native position, not this receipt.
            progress = ((p[0]-source[0]-.5)*(destination[0]-source[0]) +
                        (p[2]-source[2]-.5)*(destination[2]-source[2]))
            # Release before the center: native airborne momentum is NOT instantaneous braking.
            # Once grounded in the destination cell, ordinary feedback centers precisely.
            buttons = ["forward"] if progress < (.85 if destination[1]<source[1] else .6) and distance>.16 else []
            if not started and destination[1]>source[1]: buttons.append("jump")
            context.check()
            context.player.drive(buttons, 1, wait=False, actor_session=session)
            self.holding = True
            self.mode = "step"
            started = True
            context.pause(.075)
        return self._fail(context, "step_not_completed")

    def gap(self, context, state, destination, view, movement, avoid_damage, *, takeoff=None):
        """Execute one observed gap edge, optionally beginning at its proven run-up cell."""
        source=tuple(state["current_cell"]);edge_source=tuple(takeoff) if takeoff is not None else source
        runup=takeoff is not None
        if movement=="sneak":return self._fail(context,"gap_jump_unsupported_while_sneaking")
        if _edge_kind(state,edge_source,destination)!="gap_jump":return self._fail(context,"gap_edge_not_observed")
        session,health=state["actor_session"],state["health"]
        yaw=math.degrees(math.atan2(source[0]-destination[0],destination[2]-source[2]))
        if abs(_yaw_delta(yaw,view[0]))>ROTATION_TOLERANCE or abs(view[1])>ROTATION_TOLERANCE:
            if self.holding:self.halt(context)
            if rotate_view_timed(context,view,(yaw,0.),session):
                self.turning=True;return None
        context.check();fresh=context.player.navigation(terrain=True)
        if fresh.get("actor_session")!=session:return self._fail(context,"actor_session_changed")
        if (not fresh.get("ready") or tuple(fresh.get("current_cell",())) not in ({source,edge_source} if runup else {source}) or
                _edge_kind(fresh,edge_source,destination)!="gap_jump"):
            return self._fail(context,"gap_edge_changed")
        sx,sz=source[0]+.5,source[2]+.5;dx,dz=destination[0]-source[0],destination[2]-source[2]
        length=math.hypot(dx,dz);ux,uz=dx/length,dz/length
        end=context.clock()+3.;airborne=False
        while context.clock()<end:
            context.check();s=context.player.navigation(terrain=True)
            if s.get("actor_session")!=session:return self._fail(context,"actor_session_changed")
            if not s.get("alive") or (avoid_damage and (s.get("health",health)<health or s.get("on_fire") or s.get("nearby_hostiles"))):
                return self._fail(context,"damage_or_death_observed")
            reason=s.get("reason");airborne=airborne or reason=="not_grounded"
            if not s.get("ready") and reason not in {None,"not_grounded"}:return self._fail(context,reason or "gap_not_ready")
            p=s["position"];progress=(p[0]-sx)*ux+(p[2]-sz)*uz
            lateral=abs((p[0]-sx)*uz-(p[2]-sz)*ux)
            if p[1]<source[1]-.75 or p[1]>source[1]+2. or lateral>.8 or progress < -1. or progress > length+1.5:
                return self._fail(context,"gap_left_verified_envelope")
            if s.get("ready"):
                cell=tuple(s.get("current_cell",()))
                observed_cell=next((c for c in s.get("cells",[]) if tuple(c.get("position",()))==cell),None)
                hazard_free=observed_cell is not None and (not avoid_damage or not observed_cell.get("hazards"))
                near_landing=(cell[1]==destination[1] and
                              max(abs(cell[0]-destination[0]),abs(cell[2]-destination[2]))<=1)
                safe_landing=(cell==tuple(destination) or
                              (near_landing and progress>=length-1. and s.get("current_center_access") and hazard_free))
                if airborne and safe_landing:
                    if self.holding:self.halt(context)
                    self._gap_runup=None
                    context.pause(.12);return None
                if not (runup and cell==edge_source) and airborne:return self._fail(context,"gap_jump_missed_landing")
            # A diagonal/long jump starts one cell earlier and carries jump across the proven
            # takeoff cell, then releases it while descending so landing cannot trigger a third hop.
            descending=float(s.get("velocity",[0.,0.,0.])[1])<0.
            release_runup_jump=runup and descending and progress>=length-1.3
            buttons=["forward"]+(["jump"] if (runup and not release_runup_jump) or not airborne else [])
            if movement=="run":buttons.append("sprint")
            context.check();context.player.drive(buttons,LEASE_TICKS,wait=False,actor_session=session)
            self.holding=True;self._buttons=tuple(buttons);self.mode="gap_jump";self.lease_ticks=LEASE_TICKS
            context.pause(.05)
        return self._fail(context,"gap_jump_not_completed")

    def pulse(self, context, state, target, movement, retreat_from=(), *, avoid_damage=True, max_ticks=1,
              view=None, continuous=False, precision_sneak=True, arrival_radius=.3, preserve_edge_sneak=True,
              pose_handoff=False):
        self.turning=False;context.check()
        if type(preserve_edge_sneak) is not bool or type(pose_handoff) is not bool:
            raise ValueError('Explicit stance policy required')
        if state.get("profile") not in {"flat_full_blocks_v1","stepped_full_blocks_v1"} or not state.get("ready"):
            return self._fail(context,"navigation_not_ready")
        if self._session is None:self._session=state["actor_session"]
        if state["actor_session"]!=self._session:return self._fail(context,"actor_session_changed")
        position,now=state["position"],context.clock()
        if self._sample_time is not None and now-self._sample_time>.001:
            observed=math.hypot(position[0]-self._sample_position[0],position[2]-self._sample_position[2])*.05/(now-self._sample_time)
            previous_peak=self._peak_step;self._peak_step=max(self._peak_step,observed)
            if self.holding and observed>max(.5,previous_peak*2.5):
                self.halt(context);self.mode="braking";return None
        self._sample_position,self._sample_time=position[:],now
        if not state["current_center_access"]:return self._fail(context,"current_cell_center_obstructed")
        cell=tuple(state["current_cell"]);center=(cell[0]+.5,cell[2]+.5)
        center_distance=math.hypot(position[0]-center[0],position[2]-center[1]);active_target=target
        if self._gap_runup is not None:
            takeoff,destination=self._gap_runup;dx,dz=destination[0]-takeoff[0],destination[2]-takeoff[2]
            behind=(takeoff[0]-(1 if dx>0 else -1 if dx<0 else 0),takeoff[1],
                    takeoff[2]-(1 if dz>0 else -1 if dz<0 else 0))
            if cell==behind and center_distance<=.3:
                return self.gap(context,state,destination,view,movement,avoid_damage,takeoff=takeoff)
            active_target=(behind[0]+.5,float(behind[1]),behind[2]+.5)
        path=route(state,active_target,avoid_damage)
        edge_pose = path is None and movement == 'sneak' and _supported_sneak_edge_pose(state, active_target, avoid_damage)
        edge_stance = (edge_pose and preserve_edge_sneak) or (pose_handoff and movement=='sneak')
        if path is None:
            if not edge_pose:return self._fail(context,"no_known_safe_route",position=position,target=list(active_target),
                                                current_cell=list(cell),observed_cells=len(state.get('cells',())))
            path=[cell]
        next_cell=path[1] if len(path)>1 else None
        kind=_edge_kind(state,cell,next_cell) if next_cell else None
        if next_cell and kind is None:return self._fail(context,"unsupported_route_edge")
        if (len(path)>2 and _edge_kind(state,path[1],path[2])=="gap_jump" and
                math.hypot(path[2][0]-path[1][0],path[2][2]-path[1][2])>2.1):
            dx,dz=path[2][0]-path[1][0],path[2][2]-path[1][2]
            behind=(path[1][0]-(1 if dx>0 else -1 if dx<0 else 0),path[1][1],
                    path[1][2]-(1 if dz>0 else -1 if dz<0 else 0))
            if cell==behind and center_distance<=.3:
                self.pending=self.departed=None
                return self.gap(context,state,path[2],view,movement,avoid_damage,takeoff=path[1])
        if next_cell and kind=="gap_jump" and center_distance<=.3:
            if math.hypot(next_cell[0]-cell[0],next_cell[2]-cell[2])>2.1:
                if self.holding:self.halt(context)
                self._gap_runup=(cell,next_cell);self.pending=self.departed=None;return None
            self.pending=self.departed=None
            return self.gap(context,state,next_cell,view,movement,avoid_damage)
        if next_cell and kind=="step" and center_distance<=.16:
            if self.holding:self.halt(context)
            self.pending=self.departed=None
            return self.step(context,state,next_cell,view,avoid_damage)

        target_cell=(math.floor(active_target[0]),round(active_target[1]),math.floor(active_target[2]))
        final_waypoint=edge_pose or cell==target_cell
        centering=bool(state.get("source_recovered_from_partial_support")) or (kind in {"step","gap_jump"} and center_distance>.16)
        if final_waypoint:waypoint=(active_target[0],active_target[2])
        elif centering:waypoint=center
        elif next_cell:
            self.departed,self.pending=cell,next_cell;waypoint=(next_cell[0]+.5,next_cell[2]+.5)
        else:waypoint=(active_target[0],active_target[2])

        # Precision Sneak needs its actual native stance on full support too:
        # otherwise every key-up can restart a standing-speed tick and oscillate
        # around a small target. Observe preparation; never treat drive as proof.
        if pose_handoff and movement=='sneak' and not _observed_sneak_pose(state):
            self.halt(context,preserve_sneak=True)
            self._pose_waits+=1
            if self._pose_waits>=8:return self._fail(context,'pose_stance_not_observed')
            self.mode='pose_preparation';self.turning=True
            context.pause(UPDATE_SECONDS)
            return None  # Reobserve actor, geometry, position and stance before direction.
        self._pose_waits=0
        if edge_stance and not self.holding:
            context.check();context.player.drive(['sneak'],LEASE_TICKS,wait=False,actor_session=self._session)
            self.sneak_stance=True
        direction=None;ahead=_straight_ahead(path,position) if continuous and view is not None and not centering else None
        if ahead:
            point,direction=ahead;waypoint=(point[0],point[2])
        elif next_cell and kind in {"flat","diagonal"}:
            direction=(next_cell[0]-cell[0],next_cell[2]-cell[2])
        if any(math.hypot(waypoint[0]-t["position"][0],waypoint[1]-t["position"][2]) <
               math.hypot(position[0]-t["position"][0],position[2]-t["position"][2])-.01 for t in retreat_from):
            return self._fail(context,"escape_would_approach_threat")
        dx,dz=waypoint[0]-position[0],waypoint[1]-position[2];distance=math.hypot(dx,dz)
        radius=arrival_radius if final_waypoint else .12
        native_speed=max(0.,float(state.get("horizontal_speed",0.)))
        braking_distance=radius+max(.03,native_speed*2.2)
        if native_speed>MOVING_SPEED and distance<=braking_distance:
            if self.holding:self.halt(context,preserve_sneak=edge_stance)
            self.mode="braking";context.pause(UPDATE_SECONDS);return None

        rolling=bool(not edge_pose and continuous and view is not None and distance>radius+.08 and
                     (final_waypoint or centering or kind in {"flat","diagonal"} or ahead))
        motion_yaw=math.degrees(math.atan2(-dx,dz));camera_yaw=motion_yaw
        heading_error=abs(_yaw_delta(camera_yaw,view[0])) if view is not None else 0.
        can_steer_while_moving=bool(rolling and not centering and
                                     _broad_steering_support(state,cell,direction))
        steering_yaw=view[0] if view is not None else camera_yaw
        if view is not None:
            if (heading_error>ROTATION_TOLERANCE or abs(view[1])>ROTATION_TOLERANCE) and not can_steer_while_moving:
                if self.holding:self.halt(context,preserve_sneak=edge_stance)
                self.turning=rotate_view_timed(context,view,(camera_yaw,0.),self._session);self.mode="turning";return None
            if heading_error>ROTATION_TOLERANCE or abs(view[1])>ROTATION_TOLERANCE:
                self.turning=rotate_view_timed(context,view,(camera_yaw,0.),self._session)
                if self.turning:
                    context.check()
                    fresh=(context.player.navigation(terrain=True) if state.get("profile")=="stepped_full_blocks_v1" else context.player.navigation())
                    if fresh.get("actor_session")!=self._session:return self._fail(context,"actor_session_changed")
                    if not fresh.get("ready") or not fresh.get("current_center_access"):
                        # A timed turn spans real native updates. Partial-support recovery can
                        # transiently change readiness while an old lease is expiring; stop and
                        # replan from a fresh sample rather than converting uncertainty to motion.
                        if self.holding:self.halt(context)
                        self.mode="turning"
                        for _ in range(3):
                            context.check();context.pause(UPDATE_SECONDS)
                        return None
                    if fresh.get("current_cell")!=state.get("current_cell"):
                        if self.holding:self.halt(context)
                        return None
                    context.check();actual_view=context.player.observe();context.check()
                    if actual_view.get("actor_session",self._session)!=self._session:
                        return self._fail(context,"actor_session_changed")
                    if not actual_view.get("in_world") or not actual_view.get("alive"):
                        return self._fail(context,"not_in_world_or_dead")
                    steering_yaw=float(actual_view["yaw"])
        else:
            context.check();context.player.look(camera_yaw,0,actor_session=self._session)
        _,directions=travel_inputs(motion_yaw,steering_yaw,distance);buttons=list(directions)
        if movement=="sneak" or (precision_sneak and distance<.35):buttons.append("sneak")
        elif movement=="run":buttons.append("sprint")
        if self.holding and not rolling:self.halt(context,preserve_sneak=edge_stance)

        if waypoint!=self._waypoint:
            self._waypoint,self._best_distance,self._no_progress=waypoint,distance,0
        elif distance<self._best_distance-.005 or native_speed>MOVING_SPEED:
            self._best_distance,self._no_progress=min(self._best_distance,distance),0
        else:self._no_progress+=1
        if self._no_progress>=8:return self._fail(context,"stuck")
        room=max(0.,distance-radius-native_speed*2.2)
        # Lease expiry is a conservative stall bound, not a native speed model.
        lease_bound=.065 if "sneak" in buttons else .28 if "sprint" in buttons else .22
        per_tick_bound=max(lease_bound,native_speed,self._peak_step)
        lease=max(1,min(LEASE_TICKS,math.floor(room/per_tick_bound))) if room>0 else 1
        ticks=lease if rolling else 1 if distance<.4 else min(max_ticks,2)
        context.check()
        if edge_stance:
            leases={button:ticks for button in buttons};leases['sneak']=LEASE_TICKS
            context.player.drive(buttons,LEASE_TICKS,wait=False,actor_session=self._session,button_ticks=leases)
            self.sneak_stance=True
        else:
            context.player.drive(buttons,ticks,wait=False,actor_session=self._session)
        self.holding=True;self._buttons,self._direction=tuple(buttons),direction if rolling else None
        self.mode,self.lease_ticks=("rolling" if rolling else "precision"),ticks
        if rolling:
            context.pause(UPDATE_SECONDS)
        else:
            context.pause(ticks*.05+.06);self.halt(context,preserve_sneak=edge_stance);self.mode="edge_precision" if edge_pose else "precision"
        return None
