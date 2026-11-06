"""Opt-in LLM decision runtime over existing strict skills, not a campaign planner."""
from __future__ import annotations

import copy
try:
    import fcntl
except ImportError:  # Keep legacy MCP/imports usable where the optional POSIX journal cannot run.
    fcntl = None
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import sqlite3
import threading
import time
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator
from .client import BridgeError, CallableBackend, Player
from .errors import classify,FaultKind
from .ownership import claim_control, release_control
from .recipes import RECIPES, item_counts
from .mechanics import describe_mechanics
from .skills import default_registry
from .skills.core import _execute,ExecutionOptions

SAFE_SKILLS = frozenset({'walk_to', 'gather_wood', 'estimate_distance', 'craft_item', 'equip_item',
                          'interact_with_block', 'place_block', 'place_at', 'gather_block', 'consume_item', 'search_blocks', 'dig_step'})
BUILTINS = frozenset({'observe_environment', 'inspect_inventory', 'list_recipes'})
FATAL = frozenset({'actor_session_changed', 'transport_error', 'handler_error', 'player_dead', 'not_in_world'})


class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)
    kind: Literal['act', 'wait', 'finish']
    skill: str | None = Field(default=None, max_length=64)
    parameters: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(default='', max_length=512)
    note: str = Field(default='', max_length=512)
    wait_seconds: float = Field(default=1., ge=.1, le=5.)

    @model_validator(mode='after')
    def envelope(self):
        if (self.kind == 'act') != bool(self.skill):
            raise ValueError('Only act decisions must name a skill')
        if self.kind != 'act' and self.parameters:
            raise ValueError('Non-action parameters are forbidden')
        if len(json.dumps(self.parameters, allow_nan=False)) > 8192:
            raise ValueError('Action parameters too large')
        return self


class AgentLimits(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)
    duration_seconds: float = Field(default=120., ge=.1, le=1800.)
    max_decisions: int = Field(default=20, ge=1, le=200)
    action_timeout_seconds: float = Field(default=30., ge=.1, le=120.)
    decision_timeout_seconds: float = Field(default=20., ge=.1, le=180.)
    max_failures: int = Field(default=6, ge=1, le=20)
    max_same_failure: int = Field(default=2, ge=1, le=5)


class Decider(Protocol):
    def decide(self, context: dict) -> dict: ...


class SessionStore:
    """Private, exclusive per-agent SQLite state. Pending effects are never replayed."""
    def __init__(self, path, identity):
        if fcntl is None:raise RuntimeError('Persistent agent/BCL execution requires POSIX file locking')
        self.path = Path(path)
        self.identity = dict(identity)
        if set(identity) != {'agent_id', 'world_id', 'player_id'} or any(not isinstance(v, str) or not 1 <= len(v) <= 128 for v in identity.values()):
            raise ValueError('Explicit bounded agent/world/player identity required')
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.is_symlink(): raise ValueError('State symlink forbidden')
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        os.chmod(self.path, 0o600)
        self.lock = None

    def acquire(self):
        self.lock = open(str(self.path)+'.lock', 'a+')
        os.chmod(str(self.path)+'.lock', 0o600)
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except Exception:
            self.lock.close(); self.lock = None
            raise RuntimeError('Agent session already active') from None
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL)')
            row = db.execute('SELECT body FROM state WHERE id=1').fetchone()
        state = json.loads(row[0]) if row else {'identity': self.identity, 'history': [], 'notes': [], 'events': [], 'pending': None}
        if state['identity'] != self.identity:
            self.release()
            raise ValueError('Persistent identity mismatch; use another state file')
        return state

    def save(self, state):
        if self.lock is None: raise RuntimeError('State is not owned')
        body = json.dumps(state, allow_nan=False)
        if len(body.encode()) > 256*1024: raise ValueError('Persistent context bound exceeded')
        with sqlite3.connect(self.path) as db:
            db.execute('INSERT OR REPLACE INTO state(id,body) VALUES(1,?)', (body,))

    def release(self):
        if self.lock is not None:
            fcntl.flock(self.lock, fcntl.LOCK_UN);self.lock.close();self.lock = None


def compact(scene, inventory, menu):
    """No human text, NBT, credentials or inferred hidden terrain in LLM context."""
    selected = {key: scene.get(key) for key in ('actor_session', 'player_uuid', 'in_world', 'dimension', 'position',
                'eye_position', 'yaw', 'pitch', 'health', 'hunger', 'alive', 'on_ground', 'holding',
                'target', 'sight_target', 'visible_interactables', 'visible_blocks', 'visibility')}
    selected['holding'] = {k: v for k, v in (scene.get('holding') or {}).items()
                           if k in {'empty', 'item', 'count', 'damage', 'max_damage', 'enchantments'}}
    selected['target'] = {k: v for k, v in (scene.get('target') or {}).items()
                          if k in {'kind', 'id', 'entity_id', 'type', 'position', 'face', 'distance'}}
    selected['sight_target'] = {k: v for k, v in (scene.get('sight_target') or {}).items()
                                if k in {'id', 'position', 'aim_position', 'face', 'distance'}}
    selected['visible_interactables'] = [{k: v for k, v in row.items()
                                          if k in {'id', 'position', 'aim_position', 'face', 'distance', 'kind'}}
                                         for row in scene.get('visible_interactables', [])][:16]
    selected['entities_partial'] = True
    selected['entities'] = [{k: row[k] for k in ('id', 'entity_id', 'type', 'position', 'distance', 'visible') if k in row}
                            for row in scene.get('potentially_visible_entities', [])][:16]
    selected['inventory'] = item_counts(inventory)
    selected['carried'] = {k: v for k, v in (inventory.get('carried') or {}).items()
                           if k in {'empty', 'item', 'count'}}
    selected['menu_type'] = inventory.get('menu_type') or menu.get('type')
    selected['selected_hotbar'] = inventory.get('selected_hotbar')
    selected['container_open'] = bool(inventory.get('container_open'))
    selected['screen_type'] = menu.get('type')
    selected['inventory_slots'] = [{k: r[k] for k in ('inventory_index', 'item', 'count') if k in r}
                                   for r in inventory.get('items', [])][:46]
    return selected


def decision_state_changed(current, previous):
    # Native residual motion below arrival tolerance is not a new strategic situation.
    if any(current.get(k)!=previous.get(k) for k in ('health','hunger','inventory','holding','menu_type','screen_type','container_open')):
        return True
    a,b=current.get('position'),previous.get('position')
    return a != b if a is None or b is None else math.dist(a,b)>.1


class AgentRuntime:
    """Observe -> external LLM decision -> existing skill -> fresh verification -> replan.

    No strategy branches, recipe progression, automatic respawn, reconnect or
    implicit actor rebind. Bounded repeats are a safety policy, not a planner.
    """
    def __init__(self, player, decider: Decider, store: SessionStore, goal: str, *, registry=None,
                 allowed_skills=None, allow_rebind=False, completion_check=None, expected_actor_session=None, failure_handler=None,
                 reuse_verified_observation=False, execution_options=None, **limits):
        if not isinstance(goal, str) or not 1 <= len(goal) <= 2048: raise ValueError('Bounded operator goal required')
        if expected_actor_session is not None and (not isinstance(expected_actor_session,str) or not 1<=len(expected_actor_session)<=128):
            raise ValueError('Explicit bounded actor session required')
        if type(reuse_verified_observation) is not bool:
            raise ValueError('Explicit verified-observation reuse policy required')
        self.reuse_verified_observation = reuse_verified_observation
        if execution_options is not None and not isinstance(execution_options,ExecutionOptions):
            raise ValueError('Typed trusted-host execution options required')
        self.execution_options = execution_options
        self.expected_actor_session=expected_actor_session
        self.player, self.decider, self.store, self.goal = player, decider, store, goal
        self.registry = registry or default_registry()
        self.allowed = frozenset(SAFE_SKILLS if allowed_skills is None else allowed_skills)
        if not self.allowed <= {d['name'] for d in self.registry.describe()}:
            # Omit future safe names from the default, but reject explicit unknown names.
            if allowed_skills is not None: raise ValueError('Unknown selected skill')
            self.allowed &= {d['name'] for d in self.registry.describe()}
        self.limits = AgentLimits.model_validate(limits)
        if type(allow_rebind) is not bool: raise ValueError('allow_rebind must be an explicit boolean')
        self.allow_rebind = allow_rebind
        if completion_check is not None and not callable(completion_check): raise ValueError('Trusted completion checker required')
        self.completion_check = completion_check
        if failure_handler is not None and not callable(failure_handler):raise ValueError('Trusted failure handler required')
        self.failure_handler=failure_handler
        self.cancel_event = threading.Event()
        self._status_lock = threading.Lock()
        self._status = {'status': 'idle', 'phase': 'idle'}
        self._started = False
        self.state = None
        self.session = None
        self.deadline = None
        self.transport_lost = False

    def status(self):
        with self._status_lock: return copy.deepcopy(self._status)

    def cancel(self): self.cancel_event.set()

    def _publish(self, **value):
        with self._status_lock: self._status.update(value)

    def _check(self):
        if self.cancel_event.is_set(): raise RuntimeError('cancel_requested')
        if time.monotonic() >= self.deadline: raise RuntimeError('deadline_exceeded')

    def _observe(self):
        self._check()
        scene = self.player.observe()
        self._check()
        if not scene.get('in_world'):raise RuntimeError('not_in_world')
        if not scene.get('alive'):raise RuntimeError('player_dead')
        if not isinstance(scene.get('actor_session'), str): raise RuntimeError('actor_session_required')
        if scene.get('player_uuid') != self.store.identity['player_id']: raise RuntimeError('player_identity_mismatch')
        if self.expected_actor_session is not None and scene.get('actor_session')!=self.expected_actor_session:
            raise RuntimeError('actor_session_changed')
        if self.session is not None and scene.get('actor_session') != self.session: raise RuntimeError('actor_session_changed')
        inventory = self.player.inventory()
        self._check()
        menu = self.player.menu()
        self._check()
        # Bracket the multi-RPC observation: never execute against a replacement actor.
        again = self.player.observe()
        if again.get('actor_session') != scene.get('actor_session'): raise RuntimeError('actor_session_changed')
        if not again.get('alive'):raise RuntimeError('player_dead')
        if menu.get('type') == 'PauseScreen': raise RuntimeError('game_paused_resume_explicitly')
        grid = range(1, 10 if inventory.get('menu_type') == 'CraftingMenu' else 5)
        if ((inventory.get('carried') and not inventory['carried'].get('empty')) or
            (inventory.get('menu_type') in {'InventoryMenu', 'CraftingMenu'} and
             any(r.get('slot') in grid and not r.get('empty') for r in inventory.get('slots', [])))):
            raise RuntimeError('partial_inventory_state_requires_recovery')
        observation = compact(again, inventory, menu)
        if again.get('visibility',{}).get('profile')=='sampled_surfaces_v1':
            self._check()
            nav=self.player.navigation(terrain=True)
            if nav.get('actor_session')!=again.get('actor_session'):raise RuntimeError('actor_session_changed')
            observation['navigation']={k:nav.get(k) for k in ('profile','ready','reason','current_cell','current_center_access','cells','edges','radius','max_cells')}
            self._check()
        if self.session == again.get('actor_session'):
            evidence = self.state.setdefault('inventory_evidence', {'actor_session':self.session,'high_water':{}})
            if evidence['actor_session'] != self.session:
                evidence = self.state['inventory_evidence'] = {'actor_session':self.session,'high_water':{}}
            for item,count in observation['inventory'].items():
                evidence['high_water'][item] = max(count,evidence['high_water'].get(item,0))
            if len(evidence['high_water'])>256: raise RuntimeError('inventory_evidence_bound_exceeded')
            observation['inventory_high_water'] = dict(evidence['high_water'])
        return observation, inventory

    def _decision(self, payload):
        self._publish(phase='deciding')
        result = queue.Queue(maxsize=1)
        # A model only gets copied data, never Player or the bridge. An unresponsive
        # trusted provider can leave ONE daemon worker; no new actions/retries follow.
        def work():
            try: result.put((True, self.decider.decide(copy.deepcopy(payload))))
            except Exception as exc: result.put((False, type(exc).__name__))
        threading.Thread(target=work, daemon=True, name='blockwire-model-decision').start()
        until = min(self.deadline, time.monotonic()+self.limits.decision_timeout_seconds)
        monitor_at = time.monotonic()+.5
        while time.monotonic() < until:
            self._check()
            try:
                ok, value = result.get(timeout=.05)
                if not ok: raise RuntimeError('model_provider_error:'+value)
                return Decision.model_validate(value)
            except queue.Empty:
                if time.monotonic() >= monitor_at:
                    scene = self.player.observe()
                    if scene.get('actor_session') != self.session: raise RuntimeError('actor_session_changed')
                    if not scene.get('alive'): raise RuntimeError('player_died_while_deciding')
                    if scene.get('health', 0) < payload['observation'].get('health', 0):
                        raise RuntimeError('health_lost_while_deciding')
                    monitor_at = time.monotonic()+.5
        raise RuntimeError('model_decision_timeout')

    def _bound_player(self):
        def dispatch(request):
            op = request['op']
            if self.transport_lost: raise BridgeError('transport_error_no_reconnect')
            if op != 'stop': self._check()
            if op not in {'observe', 'inventory', 'navigation', 'combat', 'menu', 'look', 'drive', 'action',
                          'hotbar', 'open_inventory', 'close_screen', 'click_slot', 'stop', 'motion_trace'}:
                raise BridgeError('agent_operation_not_allowed')
            if op == 'motion_trace' and (request.get('reset',False) or type(request.get('limit'))is not int or not 1<=request['limit']<=8
                    or request.get('actor_session')!=self.session):
                raise BridgeError('agent_motion_trace_guard')
            if op == 'drive' and (type(request.get('ticks')) is not int or not 1 <= request['ticks'] <= 8):
                raise RuntimeError('agent_input_lease_limit')
            if op in {'look', 'drive', 'action', 'hotbar', 'open_inventory', 'close_screen', 'click_slot'}:
                if request.get('actor_session') != self.session: raise BridgeError('actor_session_changed')
            try:
                value = self.player.backend.call(op, **{k: v for k, v in request.items() if k != 'op'})
            except BridgeError as exc:
                if classify(exc) in {FaultKind.TRANSPORT,FaultKind.INVARIANT}:
                    self.transport_lost = True
                raise
            if op in {'observe', 'navigation', 'inventory', 'motion_trace'} and value.get('actor_session') != self.session:
                raise BridgeError('actor_session_changed')
            return value
        return Player(CallableBackend(dispatch))

    def run(self):
        if self._started: raise RuntimeError('Runtime activations cannot be reused')
        self._started = True
        self.deadline = time.monotonic()+self.limits.duration_seconds
        lease, bound = None, False
        failures, repeats = 0, {}
        result = {'status': 'stopped', 'reason': 'decision_budget_exhausted', 'objective_verified': False}
        try:
            self.state = self.store.acquire()
            lease = claim_control(self.player, self.cancel)
            self._publish(status='running', phase='observing')
            observation, _ = self._observe()
            self.session = observation['actor_session']
            previous = self.state.get('last_actor_session')
            if previous and previous != self.session and not self.allow_rebind:
                raise RuntimeError('explicit_actor_rebind_required')
            bound = True
            if self.state.get('pending'):
                self.state['events'].append({'kind': 'interrupted_action_not_replayed', 'action': self.state['pending']})
            self.state.update(goal=self.goal, pending=None, last_actor_session=self.session, observation=observation)
            repeats = self.state.setdefault('failed_actions', {})
            facade = self._bound_player()
            verified_observation = None
            for step in range(self.limits.max_decisions):
                self._check()
                self._publish(step=step, phase='observing')
                # Deterministic execution may reuse its own last post-action
                # snapshot for dispatch only. Every action still acquires fresh
                # actor/resource observations immediately before its effects.
                observation = verified_observation if verified_observation is not None else self._observe()[0]
                verified_observation = None
                old = self.state.get('observation', {})
                for field in ('health', 'hunger', 'dimension', 'inventory'):
                    if old.get(field) != observation.get(field):
                        self.state['events'].append({'kind': field+'_changed', 'before': old.get(field), 'after': observation.get(field)})
                self.state['observation'] = observation
                landmarks = self.state.setdefault('landmarks', {})
                for row in observation.get('visible_interactables') or []:
                    key = json.dumps([row.get('id'), row.get('position')])
                    landmarks.pop(key, None)
                    landmarks[key] = {'id': row.get('id'), 'position': row.get('position'),
                                      'observed_actor': self.session, 'status': 'historical_requires_revalidation'}
                while len(landmarks) > 32: landmarks.pop(next(iter(landmarks)))
                self.state['events'] = self.state['events'][-16:]
                self.store.save(self.state)
                payload = {'identity': self.store.identity, 'goal': self.goal, 'observation': observation,
                           'execution_limits': self.limits.model_dump(),
                           'completion_contract':self.completion_check.describe() if self.completion_check is not None and callable(getattr(self.completion_check,'describe',None)) else None,
                           'remaining_seconds': max(0., self.deadline-time.monotonic()),
                           'known_positions': list(self.state.get('landmarks', {}).values()),
                           'history': self.state['history'][-8:], 'notes': self.state['notes'][-8:],
                           'events': self.state['events'][-8:], 'completed_actions': self.state.get('completed_actions', {}),
                           'recipes': [r.describe() for r in RECIPES.values()], 'mechanics': describe_mechanics(),
                           'skills': [d for d in self.registry.describe() if d['name'] in self.allowed],
                           'read_only_actions': sorted(BUILTINS), 'decision_schema': Decision.model_json_schema()}
                try:
                    decision = self._decision(payload)
                except ValueError:
                    failures += 1
                    self.state['history'].append({'status': 'blocked', 'reason': 'invalid_model_decision'})
                    self.state['history'] = self.state['history'][-8:]
                    if failures >= self.limits.max_failures: raise RuntimeError('failure_budget_exhausted')
                    continue
                self._check()
                if decision.note: self.state['notes'] = (self.state['notes']+[decision.note])[-8:]
                if decision.kind == 'finish':
                    if self.completion_check is None:
                        result.update(reason='planner_finished_unverified')
                        break
                    fresh, _ = self._observe()
                    verified = self.completion_check(copy.deepcopy(fresh))
                    if type(verified) is not bool: raise RuntimeError('completion_checker_must_return_bool')
                    if verified:
                        result.update(status='succeeded', reason='objective_postcondition_observed', objective_verified=True)
                        break
                    failures += 1
                    self.state['history'] = (self.state['history']+[{'status': 'blocked', 'reason': 'objective_postcondition_not_observed'}])[-8:]
                    self.store.save(self.state)
                    if failures >= self.limits.max_failures: raise RuntimeError('failure_budget_exhausted')
                    continue
                if decision.kind == 'wait':
                    until = min(self.deadline, time.monotonic()+decision.wait_seconds)
                    while time.monotonic() < until:
                        self._check();self.cancel_event.wait(.05)
                    continue
                current, _ = self._observe()  # Never act on stale model-time resources/health.
                if decision_state_changed(current, observation):
                    self.state['events'] = (self.state['events']+[{'kind': 'observation_changed_during_decision'}])[-16:]
                    continue
                relevant = {k: current.get(k) for k in ('inventory', 'position', 'holding', 'dimension', 'visible_blocks', 'menu_type')}
                fingerprint = hashlib.sha256(json.dumps([decision.skill, decision.parameters, relevant], sort_keys=True, allow_nan=False).encode()).hexdigest()
                if repeats.get(fingerprint, 0) >= self.limits.max_same_failure:
                    raise RuntimeError('identical_failed_action_budget_exhausted')
                if decision.skill in BUILTINS and not decision.parameters:
                    outcome = {'status': 'succeeded', 'reason': 'fresh_observation_provided'}
                elif decision.skill not in self.allowed:
                    outcome = {'status': 'blocked', 'reason': 'action_not_allowed'}
                else:
                    parameters = {**decision.parameters}
                    parameters.setdefault('timeout_seconds', self.limits.action_timeout_seconds)
                    try: definition, validated = self.registry.prepare(decision.skill, parameters)
                    except (ValueError, TypeError):
                        outcome = {'status': 'blocked', 'reason': 'invalid_action_parameters'}
                    else:
                        self._check()
                        if self.deadline-time.monotonic() < .1: raise RuntimeError('deadline_exceeded')
                        validated = validated.model_copy(update={'timeout_seconds': min(validated.timeout_seconds,
                            self.limits.action_timeout_seconds, self.deadline-time.monotonic())})
                        parameters = validated.model_dump(mode='json')
                        self.state['pending'] = {'skill': decision.skill, 'parameters': parameters}
                        self.store.save(self.state)  # Durable BEFORE effects; never auto-replayed.
                        self._publish(phase='acting', active=self.state['pending'])
                        execution_policy={} if self.execution_options is None else {'execution_options':self.execution_options}
                        performed = _execute(definition, validated, facade, self.cancel_event,
                                             lambda progress: self._publish(progress=progress), time.monotonic, time.sleep,**execution_policy)
                        outcome = performed.model_dump(mode='json')
                        if definition.controls_player and performed.cleanup != 'released': raise RuntimeError('cleanup_not_confirmed')
                self._publish(phase='verifying')
                fresh, _ = self._observe()
                for field in ('health', 'hunger', 'dimension', 'inventory'):
                    if observation.get(field) != fresh.get(field):
                        self.state['events'].append({'kind': field+'_changed', 'before': observation.get(field), 'after': fresh.get(field)})
                self.state['events'] = self.state['events'][-16:]
                self.state['observation'] = fresh
                # Keep concise results; authoritative current resources come from the fresh snapshot.
                entry = {'action': decision.skill, 'parameters': decision.parameters,
                         'status': outcome['status'], 'reason': outcome['reason'],
                         'details': outcome.get('details', {})}
                if len(json.dumps(entry['details'])) > 8192:
                    entry['details'] = {'omitted': 'details_exceed_context_budget'}
                self.state['history'] = (self.state['history']+[entry])[-8:]
                self.state['pending'] = None
                if outcome['status'] == 'succeeded':
                    completed = self.state.setdefault('completed_actions', {})
                    completed[decision.skill] = completed.get(decision.skill, 0)+1
                if outcome['status'] != 'succeeded':
                    failures += 1;repeats[fingerprint] = repeats.get(fingerprint, 0)+1
                    if len(repeats) > 64: repeats.pop(next(iter(repeats)))
                self.store.save(self.state)
                if self.reuse_verified_observation and outcome['status'] == 'succeeded':
                    verified_observation = fresh
                if outcome['reason'] in FATAL: raise RuntimeError(outcome['reason'])
                if outcome['status']!='succeeded' and self.failure_handler is not None:
                    handled=self.failure_handler(entry)
                    if type(handled) is not bool:raise RuntimeError('failure_handler_must_return_bool')
                    if not handled:raise RuntimeError('batch_operation_failed')
                if failures >= self.limits.max_failures: raise RuntimeError('failure_budget_exhausted')
            self._check()
        except KeyboardInterrupt:
            self.cancel_event.set()
            result.update(status='cancelled', reason='keyboard_interrupt')
        except Exception as exc:
            if isinstance(exc, BridgeError) and classify(exc) in {FaultKind.TRANSPORT,FaultKind.INVARIANT}: self.transport_lost = True
            reason = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
            result.update(status='cancelled' if self.cancel_event.is_set() else 'blocked', reason=reason)
        finally:
            if lease is not None:
                try:
                    if not bound: result['cleanup'] = 'not_needed_before_actor_binding'
                    else:
                        if self.transport_lost: raise RuntimeError('transport_error_no_reconnect')
                        self.player.stop();result['cleanup'] = 'released'
                except Exception: result.update(status='failed', reason='cleanup_not_confirmed', cleanup='not_confirmed')
                release_control(self.player, lease)
            try:
                if self.state is not None:
                    self.state['last_result'] = result
                    self.store.save(self.state)
            except Exception:
                result.update(status='failed', reason='state_store_error')
            finally:
                self.store.release()
            self._publish(**result, phase='terminal', active=None)
        return {**result, 'history': self.state.get('history', []) if self.state else []}
