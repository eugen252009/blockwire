"""Explicit, bounded grounded Creative executor. No connection at import time.

The blueprint is a desired outcome, not a source of world observations. Native
geometry/placement prediction select usable poses; missing access stops the run.
Existing Survival motors and their consumption predicates are unchanged.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import threading
import time
from uuid import UUID

from pydantic import Field, field_validator
from .client import Bridge, BridgeError, Player, NativeRejected
from .creative import PROFILE, CreativeRequest, ObservedState, native_call
from .litematic import load_litematic
from .ownership import claim_control, release_control
from .schematic import compile_schematic, DIRECTIONS, PROFILES
from .skills.approaching import _reachable
from .skills.build_access import AccessMap, MAX_ROUTE, body, floor, pair, upright_body
from .skills.core import SkillContext, SkillParameters, SkillResult, SkillStop
from .skills.walking import WalkTo, walk_to

MAX_RPC = 100_000
MAX_AUDIT = 32 * 1024 * 1024
MAX_TARGETS = 1024
MAX_PREPARATIONS = 32
MAX_FRONTIERS = 64
SCAFFOLD = {'id': 'minecraft:cobblestone', 'properties': {}}
TOKEN = re.compile(r'^[a-f0-9]{64}$')


class BuildParameters(SkillParameters):
    timeout_seconds: float = Field(default=1800., ge=10., le=7200.)
    player_uuid: str
    world_id: str = Field(min_length=1, max_length=128)
    origin: list[int] = Field(min_length=3, max_length=3)
    allow_scaffolds: bool = False
    max_scaffolds: int = Field(default=128, ge=0, le=256)
    scaffold_margin: int = Field(default=3, ge=1, le=8)

    @field_validator('player_uuid')
    @classmethod
    def uuid(cls, value):
        return str(UUID(value))


def need(condition, reason):
    if not condition:
        raise SkillStop('blocked', reason)


def point(value):
    if (type(value) is not list or len(value) != 3 or
        any(type(n) not in (int, float) or not math.isfinite(n) for n in value)):
        raise ValueError('Malformed native point')
    return tuple(value)


def block_point(value):
    p = point(value)
    if any(type(n) is not int for n in p):
        raise ValueError('Native block coordinates must be integers')
    return p


def _state(row):
    value = ObservedState.model_validate(row)
    return {'id': value.id, 'properties': value.properties}


def static_state(state):
    props = dict(state['properties'])
    if state['id'] == 'minecraft:oak_stairs':
        props.pop('shape')
    if state['id'] == 'minecraft:glass_pane':
        for key in ('north', 'south', 'east', 'west'):
            props.pop(key)
    if state['id'] == 'minecraft:spruce_door':
        props['open'] = 'false'  # A requested open door is toggled separately.
    return {'id': state['id'], 'properties': props}


def matches(actual, wanted, *, final=False):
    if actual['id'] != wanted['id']:
        return False
    if final:
        return actual == wanted
    expected = static_state(wanted)
    # Compare all properties except explicitly deferred neighbor/open values.
    ignored = set(wanted['properties']) - set(expected['properties'])
    props = {key: value for key, value in actual['properties'].items() if key not in ignored}
    return props == expected['properties']


class Ledger:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, exist_ok=False)
        parent = os.open(self.directory.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try: os.fsync(parent)
        finally: os.close(parent)
        self.path = self.directory / 'journal.jsonl'
        self.stream = self.path.open('xb')
        os.chmod(self.path, 0o600)
        self.size = self.sequence = 0

    def append(self, event, **value):
        data = (json.dumps({'sequence': self.sequence, 'event': event, **value}, sort_keys=True,
                           allow_nan=False, ensure_ascii=True) + '\n').encode()
        if self.size + len(data) > MAX_AUDIT:
            raise RuntimeError('Build audit budget exhausted')
        self.stream.write(data)
        self.stream.flush()
        os.fsync(self.stream.fileno())
        self.sequence += 1
        self.size += len(data)

    def file(self, name, value):
        with (self.directory / name).open('x') as stream:
            os.chmod(self.directory / name, 0o600)
            json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        fd = os.open(self.directory, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try: os.fsync(fd)
        finally: os.close(fd)

    def close(self):
        self.stream.close()


class GuardedBackend:
    """One bound actor and transport; neither faults nor cleanup can reconnect."""
    def __init__(self, backend, context, parameters, ledger, plan):
        self.backend, self.context, self.parameters, self.ledger = backend, context, parameters, ledger
        self.actor = self.dimension = None
        self.health = self.initial = None
        self.lost = self.uncertain = self.pending_effect = False
        self.connection = None
        self.rpc = self.effects = 0
        self.data_version = plan['source']['minecraft_data_version']
        positions = [row['position'] for row in plan['targets']]
        margin = parameters.scaffold_margin
        self.lower = [min(p[i] for p in positions) - (margin if i != 1 else 1) for i in range(3)]
        self.upper = [max(p[i] for p in positions) + (margin if i != 1 else 3) for i in range(3)]

    def transport(self, op, **arguments):
        if self.lost:
            raise RuntimeError('unknown_no_retry_transport_latched')
        try:
            if isinstance(self.backend, Bridge):
                # Bridge normally allows lazy reconnection. This opt-in scope pins
                # exactly one socket, under the same lock as call/close, without
                # changing transport defaults or any TLS/authentication setting.
                with self.backend._lock:
                    if self.connection is None:
                        self.backend.connect()
                        self.connection = self.backend._socket
                        if self.connection is None:
                            raise BridgeError('Native session was not established')
                    elif self.backend._socket is not self.connection:
                        raise BridgeError('Native session changed; no reconnect')
                    return self.backend.call(op, **arguments)
            return self.backend.call(op, **arguments)
        except NativeRejected:
            # Some native errors can follow a GUI side effect. Never infer rollback.
            self.uncertain = True
            raise
        except BaseException:
            self.lost = self.uncertain = True
            close = getattr(self.backend, 'close', None)
            if callable(close):
                try: close()
                except Exception: pass
            raise

    def in_area(self, p):
        return all(self.lower[i] <= p[i] <= self.upper[i] + (1 if i != 1 else 0) for i in range(3))

    def guard_scene(self, scene):
        need(type(scene) is dict and scene.get('in_world') is True and scene.get('alive') is True, 'live_player_required')
        need(not scene.get('screen'), 'close_screen_before_build')
        need(scene.get('creative_build_profile') == PROFILE, 'creative_mod_upgrade_required')
        need(scene.get('player_uuid') == self.parameters.player_uuid, 'player_uuid_changed')
        need(scene.get('game_mode') == 'creative' and scene.get('flying') is False
             and scene.get('fall_flying') is False and scene.get('riding') is False, 'grounded_creative_required')
        need(scene.get('minecraft_data_version') == self.data_version, 'schematic_data_version_mismatch')
        actor, dimension = scene.get('actor_session'), scene.get('dimension')
        need(type(actor) is str and 1 <= len(actor) <= 128 and type(dimension) is str and dimension, 'actor_identity_required')
        position = point(scene.get('position'))
        point(scene.get('eye_position'))
        health = scene.get('health')
        need(type(health) in (int, float) and math.isfinite(health) and health > 0, 'live_health_required')
        if self.actor is None:
            self.actor, self.dimension, self.health, self.initial = actor, dimension, health, position
        need(actor == self.actor and dimension == self.dimension, 'actor_session_changed')
        need(health >= self.health, 'damage_observed')
        self.health = health
        need(self.in_area(position) and math.dist(position, self.initial) <= 64, 'build_activity_bound')
        return scene

    @staticmethod
    def audit_reply(op, reply):
        if op in {'creative', 'inventory'}:
            return reply
        if op == 'observe':
            return {k: reply.get(k) for k in ('actor_session', 'player_uuid', 'dimension', 'position', 'on_ground',
                'game_mode', 'flying', 'health', 'holding')}
        if op == 'navigation':
            return {k: reply.get(k) for k in ('actor_session', 'position', 'ready', 'reason', 'current_cell', 'on_ground')}
        return {'received': True}

    def call(self, op, **arguments):
        if op == 'stop':
            # Cleanup is allowed after cancellation/audit exhaustion, but never by
            # reopening a lost connection. A stop receipt is not release proof.
            return self.transport('stop')
        self.context.check()
        need(not self.uncertain, 'unknown_no_retry')
        need(self.rpc < MAX_RPC, 'native_rpc_budget')
        self.rpc += 1
        need(op in {'observe', 'navigation', 'inventory', 'motion_trace', 'look', 'drive', 'hotbar', 'creative'}, 'unauthorized_builder_operation')
        effect = op in {'look', 'drive', 'hotbar'} or (op == 'creative' and arguments.get('action') in {'material', 'place', 'toggle', 'remove'})
        if op in {'look', 'drive', 'hotbar', 'creative', 'motion_trace'}:
            need(self.actor is not None and arguments.get('actor_session') == self.actor, 'actor_session_required')
        if op in {'look', 'drive'}:
            arguments['grounded_creative'] = True
        if op == 'drive':
            need(type(arguments.get('ticks')) is int and 1 <= arguments['ticks'] <= 8, 'input_lease_bound')
            need(not ({'attack', 'use'} & set(arguments.get('buttons', []))), 'builder_movement_only')
        if effect:
            need(not self.pending_effect, 'unverified_effect_pending')
            self.call('observe')  # Read and guard before durable intent / native dispatch.
            self.context.check()
            self.ledger.append('intent', op=op, arguments=arguments)
            self.effects += 1
        if op == 'creative' and effect:
            self.pending_effect = True
        result = self.transport(op, **arguments)
        try:
            if type(result) is not dict:
                raise ValueError('Malformed native reply')
            if op == 'observe':
                self.guard_scene(result)
            if op == 'navigation':
                need(result.get('actor_session') == self.actor, 'actor_session_changed')
                self.call('observe')
                if result.get('ready'):
                    need(result.get('profile') == 'stepped_full_blocks_v1', 'stepped_navigation_required')
                    need(type(result.get('cells')) is list and len(result['cells']) <= 405, 'navigation_bound')
                    for cell in result['cells']:
                        block_point(cell['position'])
                    # Restrict, never broaden, native geometry: this builder does
                    # not use gap jumps or routes leaving its authorized work area.
                    allowed = {i for i, c in enumerate(result['cells']) if not c['hazards'] and self.in_area(c['position'])}
                    pairs = {frozenset((t['a'], t['b'])) for t in result.get('transitions', []) if t['kind'] in {'flat', 'diagonal', 'step'}}
                    result = dict(result)
                    result['edges'] = [e for e in result['edges'] if len(e) == 2 and all(type(n) is int and n in allowed for n in e)
                                       and frozenset(e) in pairs]
            if effect or op == 'creative':
                self.ledger.append('reply', op=op, result=self.audit_reply(op, result))
            self.context.check()
            return result
        except SkillStop:
            if effect: self.uncertain = True
            raise
        except Exception:
            self.uncertain = True
            raise

    def release_proof(self):
        if self.lost or self.actor is None:
            return False
        end = self.context.clock() + 3.
        old = None
        try:
            before = self.transport('motion_trace', limit=1, actor_session=self.actor)
            old = self._tick(before)
        except Exception:
            self.uncertain = True
        try:
            self.transport('stop')  # Attempt even when the pre-release trace is malformed.
            if old is None:
                return False
            for _ in range(40):
                if self.context.clock() >= end:
                    break
                self.context.sleeper(.05)  # Separate bounded cleanup reserve, even when cancelled.
                after = self.transport('motion_trace', limit=1, actor_session=self.actor)
                tick = self._tick(after)
                row = after['samples'][-1]
                inputs = row.get('inputs')
                if (tick > old and type(inputs) is dict and set(inputs) == {'forward', 'back', 'left', 'right', 'jump', 'sneak', 'sprint', 'attack', 'use'}
                    and all(v is False for v in inputs.values()) and row.get('remote_owned_inputs') == []):
                    return True
        except Exception:
            self.uncertain = True
        return False

    def _tick(self, trace):
        need(trace.get('profile') == 'native_player_motion_ticks_v1' and trace.get('actor_session') == self.actor, 'release_actor_changed')
        samples = trace.get('samples')
        need(type(samples) is list and len(samples) == 1 and samples[0].get('actor_session') == self.actor, 'release_tick_required')
        tick = samples[0].get('client_tick')
        need(type(tick) is int and tick >= 0, 'release_tick_required')
        return tick


def poses(nav, position, *, faces=None, desired_facing=None, eye_height=1.62, upper_part=False, half=None):
    """Candidate poses from current native reachable cells, never invented air."""
    reachable = _reachable(nav, True)
    floors = {(c['position'][0], c['position'][1]-1, c['position'][2]) for c in nav['cells'] if not c['hazards']}
    px, py, pz = position
    choices = []
    for face in (faces or DIRECTIONS):
        delta = DIRECTIONS[face]
        support = tuple(p - d for p, d in zip(position, delta))
        # Navigation proves floor geometry, not block ID or visibility. The native
        # three-block probe still has to hit and validate this exact support.
        if support not in floors:
            continue
        for cell, cost in reachable.items():
            x, y, z = cell
            stand = (x+.5, float(y), z+.5)
            if px-.42 < stand[0] < px+1.42 and pz-.42 < stand[2] < pz+1.42 and y < py+(2 if upper_part else 1.1) and y+1.9 > py:
                continue
            eye = (stand[0], stand[1]+eye_height, stand[2])
            for fraction in (.5, .2, .8):
                aim = [support[i]+.5+delta[i]*.5 for i in range(3)]
                # Lateral hit variation is important for vanilla door hinges.
                axis = 0 if delta[0] == 0 else 2
                aim[axis] = support[axis]+fraction
                if delta[1] == 0 and half in {'top', 'bottom'}:
                    aim[1] = support[1] + (.75 if half == 'top' else .25)
                if sum((eye[i]-aim[i])*delta[i] for i in range(3)) <= .08 or math.dist(eye, aim) > 2.75:
                    continue
                yaw = math.degrees(math.atan2(eye[0]-aim[0], aim[2]-eye[2]))
                facing = ('south', 'west', 'north', 'east')[int(math.floor(yaw/90+.5)) % 4]
                if desired_facing is not None and facing != desired_facing:
                    continue
                choices.append((cost+math.dist(stand, nav['position']), stand, tuple(aim), support, face))
    return sorted(choices, key=lambda row: (row[0], row[1], row[2], row[4]))[:MAX_PREPARATIONS]


class Builder:
    def __init__(self, context, parameters, plan, guard, ledger):
        self.context, self.player, self.parameters, self.plan, self.guard, self.ledger = context, context.player, parameters, plan, guard, ledger
        self.targets = {tuple(row['position']): row for row in plan['targets']}
        self.proofs = {}  # position -> native watch ticket; includes door upper halves
        self.scaffolds = {}  # only observed successful placements into literal air
        self.scaffold_parents = {}
        self.door_floors = {floor(p) for p, row in self.targets.items()
                            if row['state']['id'] == 'minecraft:spruce_door' and row['state']['properties']['half'] == 'lower'}
        self.access = None
        self.removed = set()
        self.slot = None
        self.owned_item, self.owned_count = '', 0
        self.last_tick = -1
        self.preparations = {}
        self.frontiers = set()
        self.completed = self.placed = 0

    def native(self, action, **arguments):
        self.context.check()
        value = native_call(self.player, action, actor_session=self.guard.actor, **arguments)
        need(value.get('profile') == PROFILE and value.get('actor_session') == self.guard.actor, 'creative_reply_identity')
        tick = value.get('actor_tick')
        need(type(tick) is int and tick >= self.last_tick, 'creative_reply_tick')
        self.last_tick = tick
        return value

    def scene(self):
        self.context.check()
        return self.player.observe()

    def nav(self):
        self.context.check()
        value = self.player.navigation(terrain=True)
        need(value.get('ready') is True and value.get('on_ground') is True and value.get('current_center_access') is True,
             'grounded_navigation_required')
        need(not value.get('nearby_hostiles') and not value.get('on_fire'), 'known_danger_nearby')
        upright_body(self.player.motion_trace(limit=1, actor_session=self.guard.actor), self.guard.actor, point(value.get('position')))
        if self.access is None:
            self.access = AccessMap(self.guard.actor, check=self.context.check)
        self.access.update(value)
        need(not body(self.access.home).intersection(self.targets), 'build_home_inside_target_clearance')
        return value

    def retreat_plan(self, kind, changes):
        self.nav()
        plan = self.access.retreat(self.access.current, kind, changes)
        if plan is not None:
            self.ledger.append('retreat_plan', **plan.json())
        return plan

    def settle(self):
        self.player.stop()
        for _ in range(20):
            self.context.pause(.05)
            scene = self.scene()
            if scene.get('on_ground') is True:
                nav = self.nav()
                velocity = point(nav.get('velocity'))
                if math.hypot(velocity[0], velocity[2]) < .015:
                    return scene
        raise SkillStop('blocked', 'settled_grounded_pose_not_observed')

    def move(self, stand):
        self.context.check()
        need(self.guard.in_area(stand), 'work_area_bound')
        self.ledger.append('walk_goal', position=list(stand))
        child = replace(self.context, deadline=min(self.context.deadline, self.context.clock()+30.))
        goal = (math.floor(stand[0]), round(stand[1]), math.floor(stand[2]))
        for _ in range(MAX_ROUTE+1):
            child.check()
            nav = self.nav()
            current = self.access.current
            need(self.access.route(current, self.access.home) is not None, 'known_return_route_lost')
            path = self.access.route(current, goal)
            need(path is not None, 'known_walk_route_missing')
            if len(path) == 1 and math.dist(point(nav['position']), stand) <= .08:
                return
            next_cell = path[1] if len(path) > 1 else current
            if next_cell != current:
                edge = self.access.edges.get(pair(current, next_cell))
                need(edge is not None and edge.frame == self.access.frame, 'walk_edge_not_fresh')
            waypoint = stand if next_cell == goal else (next_cell[0]+.5, float(next_cell[1]), next_cell[2]+.5)
            self.ledger.append('walk_edge', start=list(current), end=list(next_cell), observed_frame=self.access.frame)
            child.check()
            result = walk_to(child, WalkTo(x=float(waypoint[0]), y=float(waypoint[1]), z=float(waypoint[2]),
                terrain=True, arrival_radius=.08, avoid_damage=True), expected_session=self.guard.actor, pose_handoff=True)
            need(result.status == 'succeeded', 'walk_' + result.reason)
            scene = self.settle()
            need(math.dist(point(scene['position']), waypoint) <= .2, 'placement_pose_not_observed')
            if next_cell == goal: return
        raise SkillStop('blocked', 'walk_route_step_budget')

    def aim(self, aim):
        scene = self.scene()
        eye = point(scene['eye_position'])
        dx, dy, dz = [aim[i]-eye[i] for i in range(3)]
        yaw = math.degrees(math.atan2(-dx, dz))
        pitch = -math.degrees(math.atan2(dy, math.hypot(dx, dz)))
        self.context.check()
        receipt = self.player.look(yaw, pitch, duration_ms=200, rotation_profile='smoothstep', actor_session=self.guard.actor)
        rotation_id = receipt.get('rotation_id')
        need(type(rotation_id) is int and rotation_id > 0, 'rotation_identity_required')
        for _ in range(16):
            self.context.pause(.05)
            s = self.scene()
            rotation = s.get('rotation', {})
            if (rotation.get('actor_session') == self.guard.actor and rotation.get('rotation_id') == rotation_id
                and rotation.get('active') is False and rotation.get('status') == 'completed'
                and abs((s['yaw']-yaw+180)%360-180) < .15 and abs(s['pitch']-pitch) < .15):
                return
        raise SkillStop('blocked', 'aim_not_observed')

    def inventory(self):
        value = self.player.inventory()
        need(value.get('actor_session') == self.guard.actor and value.get('guarded_inventory') is True, 'inventory_actor_changed')
        need(value.get('container_open') is False and value.get('carried', {}).get('empty') is True, 'clean_closed_inventory_required')
        return value

    def material(self, item):
        value = self.inventory()
        entries = {row['inventory_index']: row for row in value['items']}
        if self.slot is None:
            self.slot = next((i for i in range(9) if i not in entries), None)
            need(self.slot is not None, 'empty_hotbar_slot_required')
        row = entries.get(self.slot, {})
        old, count = row.get('item', ''), row.get('count', 0)
        need((old, count) == (self.owned_item, self.owned_count), 'owned_hotbar_slot_changed')
        if old != item or count != 64:
            need(old in {'', *PROFILES}, 'owned_hotbar_slot_changed')
            reply = self.native('material', item=item, slot=self.slot, expected_item=old, expected_count=count)
            need(reply.get('submitted') is True, 'material_submission_not_confirmed')
            for _ in range(20):
                self.context.pause(.05)
                fresh = self.inventory()
                selected = next((r for r in fresh['items'] if r['inventory_index'] == self.slot), {})
                if selected.get('item') == item and selected.get('count') == 64:
                    break
            else: raise SkillStop('blocked', 'creative_material_not_observed')
            self.owned_item, self.owned_count = item, 64
            self.guard.pending_effect = False
        self.context.check()
        self.player.hotbar(self.slot, actor_session=self.guard.actor)
        self.context.pause(.1)
        need(self.scene().get('holding', {}).get('item') == item, 'held_material_not_observed')

    def watch(self, ticket):
        need(type(ticket) is str and TOKEN.fullmatch(ticket), 'native_watch_ticket_required')
        reply = self.native('check', ticket=ticket)
        need(reply.get('ticket') == ticket and reply.get('source') == 'explicit_client_known_watch_v1'
             and reply.get('visual_observation') is False, 'native_watch_provenance')
        rows = reply.get('states')
        need(type(rows) is list and 1 <= len(rows) <= 2, 'native_watch_bound')
        states = {}
        for row in rows:
            pos = block_point(row.get('position'))
            need(pos not in states, 'duplicate_native_watch_position')
            states[pos] = _state(row)
        return reply, states

    def verify_effect(self, ticket, expected, dispatched_tick, *, removed=False):
        previous = None
        for _ in range(30):
            self.context.pause(.1)
            reply, states = self.watch(ticket)
            need(set(states) == set(expected), 'native_watch_positions_changed')
            good = (all(s['id'] == 'minecraft:air' and s['properties'] == {} for s in states.values()) if removed
                    else all(matches(states[p], desired) for p, desired in expected.items()))
            if good and reply['actor_tick'] > dispatched_tick + (5 if removed else 0):
                if previous is not None and reply['actor_tick'] > previous:
                    return states  # Caller commits ownership/accounting before clearing pending.
                previous = reply['actor_tick']
            else: previous = None
        self.guard.uncertain = True
        raise SkillStop('failed', 'effect_not_observed_unknown_no_retry')

    def install(self, position, state, *, temporary=False):
        need(temporary or position in self.targets, 'target_not_authorized')
        if temporary:
            need(state == SCAFFOLD, 'unsupported_scaffold_material')
            need(self.parameters.allow_scaffolds and len(self.scaffolds) < self.parameters.max_scaffolds, 'scaffold_budget')
            need(position not in self.targets and self.guard.in_area(position), 'scaffold_position_not_authorized')
            need(position not in self.door_floors, 'scaffold_would_support_permanent_door')
        nav = self.nav()
        scene = self.scene()
        props = state['properties']
        faces = list(DIRECTIONS)
        if 'axis' in props:
            faces = {'x': ['east', 'west'], 'y': ['up', 'down'], 'z': ['north', 'south']}[props['axis']]
        if state['id'] == 'minecraft:spruce_door': faces = ['up']
        options = poses(nav, position, faces=faces, desired_facing=props.get('facing'),
                        eye_height=scene['eye_position'][1]-scene['position'][1], upper_part=state['id'] == 'minecraft:spruce_door', half=props.get('half'))
        if not options:
            return False
        self.material(state['id'])
        for _, stand, aim, support, face in options:
            fingerprint = (position, stand, aim, len(self.proofs), len(self.scaffolds))
            if fingerprint in self.preparations: continue
            self.preparations[fingerprint] = True
            need(len(self.preparations) <= MAX_TARGETS*MAX_PREPARATIONS, 'preparation_budget')
            self.move(stand)
            self.aim(aim)
            probe = self.native('probe')
            if probe.get('hit') is not True: continue
            hit_position = block_point(probe.get('position'))
            hit_state = _state({**probe['state'], 'position': list(hit_position)})
            if hit_position == position and matches(hit_state, state, final=True) and not temporary:
                receipt = self.native('remember', token=probe['hit_token'], position=list(position))
                self.proofs[position] = receipt['ticket']
                return True
            if (hit_position != support or probe.get('face') != face or probe.get('placement_available') is not True
                or probe.get('destination_was_air') is not True or block_point(probe.get('destination')) != position):
                continue
            candidate = _state({**probe['candidate'], 'position': list(position)})
            if not matches(candidate, state): continue
            expected = {position: state}
            if state['id'] == 'minecraft:spruce_door':
                upper = (position[0], position[1]+1, position[2])
                expected[upper] = self.targets[upper]['state']
            if temporary:
                need(position in _reachable(self.nav(), True), 'scaffold_return_floor_not_observed')
                self.ledger.append('scaffold_plan', position=list(position), standing_pose=list(stand),
                    native_support=list(support), face=face, full_floor_below_observed=True,
                    removal_order='dependent_children_then_retreat_safe', return_route='observed_history_fresh_each_walk_edge')
            if self.retreat_plan('place', expected) is None: continue
            receipt = self.native('place', token=probe['placement_token'], position=list(position))
            need(receipt.get('submitted') is True and receipt.get('destination_was_air') is True, 'placement_receipt_invalid')
            ticket = receipt.get('ticket')
            self.verify_effect(ticket, expected, receipt['actor_tick'])
            # Account for a verified world effect before any cancellable follow-up.
            if temporary:
                self.scaffolds[position] = ticket
                self.scaffold_parents[position] = {p for p in (support, floor(position)) if p in self.scaffolds and p not in self.removed}
            else:
                for pos in expected: self.proofs[pos] = ticket
                self.placed += 1
            self.guard.pending_effect = False
            self.access.invalidate('place', expected)
            need(self.scene().get('holding', {}).get('item') == state['id'] and
                 self.scene().get('holding', {}).get('count') == 64, 'creative_material_count_changed')
            self.ledger.append('placed_verified', position=list(position), state=state, temporary=temporary, ticket=ticket)
            return True
        return False

    def scaffold_candidates(self, pending, nav):
        if not self.parameters.allow_scaffolds or len(self.scaffolds) >= self.parameters.max_scaffolds:
            return []
        reachable = _reachable(nav, True)
        candidates = []
        for target in pending:
            p = tuple(target['position'])
            props = target['state']['properties']
            faces = {'x': ['east', 'west'], 'y': ['up', 'down'], 'z': ['north', 'south']}.get(props.get('axis'), list(DIRECTIONS))
            attachments = {tuple(p[i]-DIRECTIONS[f][i] for i in range(3)) for f in faces}
            for cell in reachable:
                if cell in self.targets or cell in self.scaffolds or cell in self.door_floors or not self.guard.in_area(cell): continue
                attachment = cell in attachments
                climb = cell[1]+1 <= p[1]-1 and math.hypot(cell[0]-p[0], cell[2]-p[2]) <= 3
                if attachment or climb:
                    candidates.append((not attachment, math.dist(cell, p), cell))
        return [row[2] for row in sorted(set(candidates))[:16]]

    def frontier(self, pending, nav):
        reachable = _reachable(nav, True)
        def distance(cell):
            return min(math.dist((cell[0]+.5, cell[1]+1., cell[2]+.5), row['position']) for row in pending)
        current = tuple(nav['current_cell'])
        candidates = [cell for cell in reachable if cell != current and distance(cell) < distance(current)-.15
                      and (cell, len(self.proofs), len(self.scaffolds)) not in self.frontiers]
        if not candidates: return False
        need(len(self.frontiers) < MAX_FRONTIERS*(1+len(self.proofs)+len(self.scaffolds)), 'frontier_budget')
        selected = min(candidates, key=lambda c: (distance(c), reachable[c], c))
        self.frontiers.add((selected, len(self.proofs), len(self.scaffolds)))
        self.move((selected[0]+.5, float(selected[1]), selected[2]+.5))
        return True

    def sight(self, position, *, mutation='place', changes=None):
        """Historical poses are candidates only; walk, body, ray and retreat revalidate."""
        self.nav()
        changes = [position] if changes is None else changes
        nodes, edges = self.access.projected(mutation, changes)
        options = []
        for cell in sorted(self.access.nodes):
            self.context.check()
            stand = (cell[0]+.5, float(cell[1]), cell[2]+.5)
            if mutation == 'remove' and floor(cell) in changes: continue
            if not self.guard.in_area(stand): continue
            eye = (stand[0], stand[1]+1.62, stand[2])
            aims = []
            for delta in DIRECTIONS.values():
                aim = tuple(position[i]+.5+delta[i]*.5 for i in range(3))
                if math.dist(eye, aim) <= 2.75 and sum((eye[i]-aim[i])*delta[i] for i in range(3)) > .08:
                    aims.append(aim)
            if not aims or self.access.route(cell, self.access.home, nodes=nodes, edges=edges) is None: continue
            path = self.access.route(self.access.current, cell)
            if path is not None:
                options.extend((len(path), stand, aim) for aim in aims)
        for _, stand, aim in sorted(options)[:MAX_PREPARATIONS]:
            self.move(stand); self.aim(aim)
            self.nav()
            if self.access.retreat(self.access.current, mutation, changes) is None: continue
            probe = self.native('probe')
            if probe.get('hit') is True and block_point(probe.get('position')) == position:
                return probe
        return None

    def finish_doors(self):
        for position, target in self.targets.items():
            state = target['state']
            if state['id'] != 'minecraft:spruce_door' or state['properties']['half'] != 'lower': continue
            _, states = self.watch(self.proofs[position])
            pair = {position, (position[0], position[1]+1, position[2])}
            need(set(states) == pair, 'door_pair_observation_required')
            for pos, actual in states.items():
                wanted = self.targets[pos]['state']
                need(static_state(actual) == static_state(wanted), 'door_changed_before_toggle')
            if all(states[pos] == self.targets[pos]['state'] for pos in pair): continue
            probe = self.sight(position, changes=pair)
            need(probe is not None, 'door_not_reachable')
            need(self.retreat_plan('place', pair) is not None, 'door_toggle_would_cut_return')
            receipt = self.native('toggle', position=list(position), token=probe['hit_token'], open=state['properties']['open'] == 'true')
            tick = receipt['actor_tick']
            previous = None
            for _ in range(20):
                self.context.pause(.1)
                reply, observed = self.watch(self.proofs[position])
                need(set(observed) == pair, 'door_pair_observation_required')
                if reply['actor_tick'] > tick and all(observed[p] == self.targets[p]['state'] for p in pair):
                    if previous is not None and reply['actor_tick'] > previous:
                        self.guard.pending_effect = False
                        self.access.invalidate('place', pair)
                        break
                    previous = reply['actor_tick']
                else: previous = None
            else:
                self.guard.uncertain = True
                raise SkillStop('failed', 'door_state_not_observed_unknown_no_retry')

    def scaffold_state(self, position):
        reply, states = self.watch(self.scaffolds[position])
        need(reply.get('placed_by_this_controller') is True and states == {position: SCAFFOLD}, 'owned_scaffold_changed')
        return states

    def cleanup_scaffolds(self):
        remaining = self.scaffolds.keys()-self.removed
        if not remaining: return
        self.material(SCAFFOLD['id'])
        while remaining:
            self.context.check()
            changed = False
            for position in sorted(remaining, key=lambda p: (-p[1], p[2], p[0])):
                self.context.check()
                if any(position in self.scaffold_parents.get(child, set()) for child in remaining): continue
                ticket = self.scaffolds[position]
                self.scaffold_state(position)
                probe = self.sight(position, mutation='remove')
                if probe is None: continue
                # Recheck ownership and the retreat AFTER approach/aim, before dispatch.
                states = self.scaffold_state(position)
                if self.retreat_plan('remove', [position]) is None: continue
                receipt = self.native('remove', ticket=ticket, token=probe['hit_token'], position=list(position))
                need(receipt.get('submitted') is True, 'scaffold_removal_receipt_invalid')
                self.verify_effect(ticket, {position: states[position]}, receipt['actor_tick'], removed=True)
                self.removed.add(position); remaining.remove(position)
                self.guard.pending_effect = False
                self.access.invalidate('remove', [position])
                self.ledger.append('scaffold_removed_verified', position=list(position), ticket=ticket)
                changed = True
                break
            need(changed, 'scaffold_cleanup_has_no_known_retreat_safe_order')

    def run(self):
        self.scene(); self.settle(); self.inventory()
        self.ledger.append('bound', actor_session=self.guard.actor, dimension=self.guard.dimension,
                           player_uuid=self.parameters.player_uuid, world_id_label=self.parameters.world_id)
        pending = [row for row in self.plan['targets'] if row['operation'] == 'place_block']
        while pending:
            self.context.check()
            lowest = min(row['position'][1] for row in pending)
            layer = [row for row in pending if row['position'][1] == lowest]
            scene = self.scene()
            layer.sort(key=lambda row: math.dist(row['position'], scene['position']))
            changed = False
            for row in layer[:32]:
                position = tuple(row['position'])
                if self.install(position, row['state']):
                    pending.remove(row); changed = True; self.completed += 1
                    self.context.publish({'phase': 'building', 'verified_target_groups': self.completed, 'remaining_groups': len(pending), 'known_scaffolds': len(self.scaffolds)})
                    break
            if changed: continue
            nav = self.nav()
            if self.frontier(layer, nav): continue
            for position in self.scaffold_candidates(layer, nav):
                if self.install(position, SCAFFOLD, temporary=True):
                    changed = True; break
            need(changed, 'no_known_grounded_build_access')
        self.finish_doors()
        self.cleanup_scaffolds()
        self.move(self.guard.initial)
        need(set(self.proofs) == set(self.targets), 'target_proofs_incomplete')
        for ticket in sorted(set(self.proofs.values())):
            _, states = self.watch(ticket)
            expected = {p for p, watched in self.proofs.items() if watched == ticket}
            need(set(states) == expected, 'final_target_observation_incomplete')
            need(all(p in self.targets and matches(state, self.targets[p]['state'], final=True) for p, state in states.items()), 'final_block_state_mismatch')
        for position, ticket in self.scaffolds.items():
            _, states = self.watch(ticket)
            need(states == {position: {'id': 'minecraft:air', 'properties': {}}}, 'temporary_scaffold_remains')
        final = self.scene()
        need(final.get('on_ground') is True and math.dist(point(final['position']), self.guard.initial) <= .3, 'grounded_return_not_observed')
        return SkillResult(status='succeeded', reason='targets_and_owned_scaffolds_verified',
            text='Observed requested block states, removal of owned scaffolds and grounded return; not an atomic server/save certificate.',
            details={'target_blocks': len(self.targets), 'verified_target_groups': self.completed,
                     'new_target_placements_observed': self.placed, 'scaffolds': len(self.scaffolds),
                     'interior_air_independently_verified': False, 'graphical_acceptance': 'NOT_RUN'})


def run_build(player, source, parameters, directory, *, cancel=None, publish=None, clock=time.monotonic, sleeper=time.sleep):
    if not isinstance(parameters, BuildParameters):
        raise ValueError('Typed build parameters required')
    parameters = BuildParameters.model_validate(parameters.model_dump(mode='python'))
    plan = compile_schematic(source, origin=parameters.origin)
    if len(plan['targets']) > MAX_TARGETS:
        raise ValueError('Executor target budget exceeded')
    cancellation = cancel if cancel is not None else threading.Event()
    deadline = clock() + parameters.timeout_seconds
    lease = claim_control(player, cancellation.set)
    ledger = guard = context = builder = None
    result = None
    try:
        ledger = Ledger(directory)
        ledger.file('plan.json', plan)
        ledger.file('authorization.json', parameters.model_dump(mode='json'))
        context = SkillContext(player, cancellation, deadline, publish or (lambda _: None), clock, sleeper)
        guard = GuardedBackend(player.backend, context, parameters, ledger, plan)
        context.player = Player(guard)
        builder = Builder(context, parameters, plan, guard, ledger)
        result = builder.run()
    except SkillStop as error:
        result = SkillResult(status=error.status, reason=error.reason, text=error.reason.replace('_', ' '))
    except KeyboardInterrupt:
        cancellation.set()
        result = SkillResult(status='cancelled', reason='cancel_requested', text='Interrupted; no automatic replay or recovery.')
    except Exception as error:
        result = SkillResult(status='failed', reason='unknown_no_retry' if guard is not None else 'preflight_failed',
            text='Stopped; no automatic reconnect, replay, rescue or resume.', details={'error_type': type(error).__name__})
        if guard is not None: guard.uncertain = True
    finally:
        try:
            if result is None:
                result = SkillResult(status='failed', reason='interrupted_unknown_no_retry', text='Interrupted before a terminal result.')
                if guard is not None: guard.uncertain = True
            if context is not None: context.active = False
            if guard is not None:
                required = guard.effects > 0
                released = guard.release_proof() if required else True
                result.cleanup = ('released' if released else 'not_confirmed') if required else 'not_required'
                result.details.update(native_rpc=guard.rpc, native_effects=guard.effects,
                    unknown_no_retry=guard.uncertain or guard.pending_effect or not released,
                    verified_target_groups=builder.completed if builder else 0,
                    new_target_placements_observed=builder.placed if builder else 0,
                    known_owned_scaffolds_remaining=len(builder.scaffolds)-len(builder.removed) if builder else 0,
                    scaffold_inventory_complete=not guard.uncertain and not guard.pending_effect)
                if not released and result.status == 'succeeded':
                    result.status, result.reason = 'failed', 'release_not_confirmed'
            if ledger is not None:
                try:
                    ledger.file('result.json', result.model_dump(mode='json'))
                    ledger.file('FINISHED.json', {'result_sha256': hashlib.sha256((ledger.directory/'result.json').read_bytes()).hexdigest()})
                except Exception:
                    result.status, result.reason = 'failed', 'result_persistence_failed'
                    result.details['unknown_no_retry'] = True
                finally: ledger.close()
        finally:
            release_control(player, lease)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='Explicit experimental grounded Creative build; never selects/starts a world, flies or uses slash commands.')
    parser.add_argument('schematic', type=Path)
    parser.add_argument('--origin', type=int, nargs=3, required=True)
    parser.add_argument('--player-uuid', required=True)
    parser.add_argument('--world-id', required=True, help='Operator audit label, not authenticated save identity.')
    parser.add_argument('--output', type=Path, required=True, help='NONEXISTENT private run directory; no resumption.')
    parser.add_argument('--confirm-creative-build', action='store_true', required=True)
    parser.add_argument('--allow-scaffolds', action='store_true')
    parser.add_argument('--max-scaffolds', type=int, default=128)
    parser.add_argument('--scaffold-margin', type=int, default=3)
    parser.add_argument('--duration', type=float, default=1800.)
    args = parser.parse_args(argv)
    params = BuildParameters(player_uuid=args.player_uuid, world_id=args.world_id, origin=args.origin,
        allow_scaffolds=args.allow_scaffolds, max_scaffolds=args.max_scaffolds, scaffold_margin=args.scaffold_margin,
        timeout_seconds=args.duration)
    source = load_litematic(args.schematic)
    plan = compile_schematic(source, origin=args.origin)
    if len(plan['targets']) > MAX_TARGETS or args.output.exists() or args.output.is_symlink():
        parser.error('Target budget exceeded or output already exists; no connection opened')
    cancel = threading.Event()
    previous = {sig: signal.signal(sig, lambda *_: cancel.set()) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        connection = Bridge.from_env()  # Lazy connect only after fresh ledger admission.
        try:
            result = run_build(Player(connection), source, params, args.output, cancel=cancel)
        finally:
            connection.close()
        print(json.dumps(result.model_dump(mode='json'), indent=2))
        return 0 if result.status == 'succeeded' else 1
    finally:
        for sig, handler in previous.items(): signal.signal(sig, handler)


if __name__ == '__main__':
    raise SystemExit(main())
