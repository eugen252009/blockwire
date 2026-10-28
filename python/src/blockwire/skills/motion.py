"""Feedback-driven native input motor. Native Minecraft still owns physics and collision."""
from __future__ import annotations

import math
from .core import SkillResult
from .walking import route


LEASE_TICKS = 8             # 400 ms fail-safe, not a gameplay completion guarantee.
UPDATE_SECONDS = .05        # Observe/revalidate before renewing; never blindly refresh input.
STEERING_DEGREES = 4.


def _blocked(reason):
    return SkillResult(status="blocked", reason=reason, text="Motion stopped: " + reason.replace("_", " "))


def _yaw_delta(target, current):
    return (target-current+180) % 360-180


def turn_view_step(context, view, wanted, session):
    """Shortest-arc camera step, at most eight degrees/axis. Large turns must be stopped."""
    dyaw, dpitch = _yaw_delta(wanted[0], view[0]), wanted[1]-view[1]
    extent = max(abs(dyaw), abs(dpitch))
    fraction = min(1., 8./extent) if extent else 1.
    context.check()
    context.player.look((view[0]+dyaw*fraction+180) % 360-180,
                        view[1]+dpitch*fraction, actor_session=session)
    if extent > 8.:
        context.pause(.05)
        return True
    return False


def travel_inputs(motion_yaw, current_yaw, distance):
    """Primarily W; A/D only for one-tick, near-waypoint lateral corrections."""
    if distance < .35:
        for offset, key in [(90, "right"), (-90, "left")]:
            camera_yaw = (motion_yaw-offset+180) % 360-180
            if abs(_yaw_delta(camera_yaw, current_yaw)) <= 8.:
                return camera_yaw, (key,)
    return (motion_yaw+180) % 360-180, ("forward",)


def _straight_ahead(path, position):
    """A loaded, collision-connected collinear chain; never shortcut a corner/unknown edge."""
    if len(path) < 3:
        return None
    dx, dz = path[1][0]-path[0][0], path[1][2]-path[0][2]
    if abs(dx)+abs(dz) != 1 or path[1][1] != path[0][1]:
        return None
    lateral = abs(position[2]-path[0][2]-.5) if dx else abs(position[0]-path[0][0]-.5)
    if lateral > .06:
        return None
    end = 1
    for i in range(2, min(len(path), 5)):
        if (path[i][0]-path[i-1][0], path[i][2]-path[i-1][2]) != (dx, dz) or path[i][1] != path[0][1]:
            break
        end = i
    if end < 2:
        return None
    return (path[end][0]+.5, path[end][1], path[end][2]+.5), (dx, dz)


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
        self._sample_position = None
        self._sample_time = None
        self._peak_step = 0.

    def halt(self, context):
        context.check()
        context.player.stop()
        self.holding = False
        self._buttons, self._direction = (), None
        self.mode, self.lease_ticks = "stopped", 0

    def _fail(self, context, reason):
        if self.holding:
            self.halt(context)
        return _blocked(reason)

    def pulse(self, context, state, target, movement, retreat_from=(), *, avoid_damage=True, max_ticks=1,
              view=None, continuous=False):
        self.turning = False
        context.check()
        if state.get("profile") != "flat_full_blocks_v1" or not state.get("ready"):
            return self._fail(context, "navigation_not_ready")
        if self._session is None:
            self._session = state["actor_session"]
        if state["actor_session"] != self._session:
            return self._fail(context, "actor_session_changed")
        position, now = state["position"], context.clock()
        if self._sample_time is not None and now-self._sample_time > .001:
            step = math.hypot(position[0]-self._sample_position[0], position[2]-self._sample_position[2])*.05/(now-self._sample_time)
            self._peak_step = max(self._peak_step, step)
        self._sample_position, self._sample_time = position[:], now
        path = route(state, target, avoid_damage)
        if path is None:
            return self._fail(context, "no_known_safe_route")
        if not state["current_center_access"]:
            return self._fail(context, "current_cell_center_obstructed")
        cell = tuple(state["current_cell"])
        if self.pending is not None:
            continuing = cell == self.departed and len(path) > 1 and path[1] == self.pending
            centering = cell == self.pending and math.hypot(
                position[0]-self.pending[0]-.5, position[2]-self.pending[2]-.5) > .12
            if not (continuing or centering):
                self.pending = self.departed = None
        center = (cell[0]+.5, cell[2]+.5)
        if cell == (math.floor(target[0]), cell[1], math.floor(target[2])):
            waypoint = (target[0], target[2])
        elif self.pending is not None:
            waypoint = (self.pending[0]+.5, self.pending[2]+.5)
        elif math.hypot(position[0]-center[0], position[2]-center[1]) > .12:
            waypoint = center
        elif len(path) > 1:
            self.departed, self.pending = cell, path[1]
            waypoint = (self.pending[0]+.5, self.pending[2]+.5)
        else:
            waypoint = (target[0], target[2])

        rolling, direction, lease = False, None, 0
        ahead = _straight_ahead(path, position) if continuous and view is not None else None
        if ahead:
            point, direction = ahead
            room = math.hypot(point[0]-position[0], point[2]-position[2])
            nominal = .065 if movement == "sneak" else .28 if movement == "run" else .22
            # Conservative budget heuristic, NOT a replacement physics/speed guarantee.
            bound = max(nominal*2.5, self._peak_step*1.5)
            lease = min(LEASE_TICKS, max(0, math.floor((room-.6)/bound)))
            if lease >= 4:
                rolling, waypoint = True, (point[0], point[2])
                self.departed, self.pending = cell, path[1]  # Brake toward the next center, not backwards.
        if any(math.hypot(waypoint[0]-t["position"][0], waypoint[1]-t["position"][2]) <
               math.hypot(position[0]-t["position"][0], position[2]-t["position"][2])-.01 for t in retreat_from):
            return self._fail(context, "escape_would_approach_threat")
        dx, dz = waypoint[0]-position[0], waypoint[1]-position[2]
        distance = math.hypot(dx, dz)
        motion_yaw = math.degrees(math.atan2(-dx, dz))
        camera_yaw, directions = travel_inputs(motion_yaw, view[0], distance) if view is not None else (motion_yaw, ("forward",))
        buttons = list(directions)
        if movement == "sneak" or distance < .35:
            buttons.append("sneak")
        elif movement == "run":
            buttons.append("sprint")
        keep_held = (rolling and self.holding and tuple(buttons) == self._buttons and direction == self._direction
                     and view is not None and abs(_yaw_delta(camera_yaw, view[0])) <= STEERING_DEGREES
                     and abs(view[1]) <= STEERING_DEGREES)
        if not keep_held:
            self.halt(context)  # Sharp turn, mode change, uncertain/short route or first alignment.
        if view is not None:
            self.turning = turn_view_step(context, view, (camera_yaw, 0.), self._session)
            if self.turning:
                self.mode = "turning"
                return None  # Fresh observations/readiness checks before the next movement stage.
        else:
            context.check()
            context.player.look(motion_yaw, 0, actor_session=self._session)
        if waypoint != self._waypoint:
            self._waypoint, self._best_distance, self._no_progress = waypoint, distance, 0
        elif distance < self._best_distance-.01:
            self._best_distance, self._no_progress = distance, 0
        else:
            self._no_progress += 1
        if self._no_progress >= 8:
            return self._fail(context, "stuck")
        speed = .065 if "sneak" in buttons else .28 if "sprint" in buttons else .22
        ticks = lease if rolling else 1 if distance < .35 else min(max_ticks, max(1, math.floor(distance/speed)))
        context.check()
        context.player.drive(buttons, ticks, wait=False, actor_session=self._session)
        self.holding = True
        self._buttons, self._direction = tuple(buttons), direction if rolling else None
        self.mode, self.lease_ticks = "rolling" if rolling else "precision", ticks
        if rolling:
            context.pause(UPDATE_SECONDS)  # Observe while W remains held, then decide whether renewal is safe.
        else:
            context.pause(ticks*.05+.08)
            self.halt(context)
            self.mode = "precision"
        return None
