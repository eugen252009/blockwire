"""Trusted, transport-independent skill contract. No remote code loading or eval."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from importlib.metadata import entry_points
import os
import re
import threading
import time
from typing import Any, Callable, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from ..client import BridgeError, Player, _environment
from ..errors import NativeOperationError
from ..ownership import BUSY, claim_control, control_busy, release_control

Status = Literal["succeeded", "blocked", "cancelled", "timed_out", "failed"]


class SkillParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    timeout_seconds: float = Field(default=30, ge=0.1, le=120, description="Cooperative wall-clock deadline.")


class SkillResult(BaseModel):
    status: Status
    reason: str
    text: str
    details: dict[str, Any] = Field(default_factory=dict)
    cleanup: Literal["released", "not_required", "not_confirmed"] = "not_required"


class SkillStop(Exception):
    def __init__(self, status: Status, reason: str):
        self.status, self.reason = status, reason


@dataclass(frozen=True)
class ExecutionOptions:
    """Trusted-host diagnostic policy, never a BCL command or skill parameter.

    Reuse is confined to one SkillContext. It grants no ownership or lease
    transfer and cannot extend an action beyond ordinary final cleanup.
    """
    camera_reuse: bool = False
    sneak_reuse: bool = False
    placement_reuse: bool = False

    def __post_init__(self):
        if any(type(value) is not bool for value in (self.camera_reuse,self.sneak_reuse,self.placement_reuse)):
            raise ValueError('Execution reuse options require explicit booleans')


@dataclass
class SkillContext:
    player: Player
    cancellation: threading.Event
    deadline: float
    publish: Callable[[dict[str, Any]], None]
    clock: Callable[[], float] = time.monotonic
    sleeper: Callable[[float], None] = time.sleep
    execution_options: ExecutionOptions = field(default_factory=ExecutionOptions)
    placement_session: Any = field(default=None, repr=False)
    retained_sneak_session: str | None = field(default=None, repr=False)
    active: bool = field(default=True, repr=False)

    def check(self) -> None:
        if not self.active:
            raise SkillStop('blocked','execution_context_closed')
        if self.cancellation.is_set():
            raise SkillStop("cancelled", "cancel_requested")
        if self.clock() >= self.deadline:
            raise SkillStop("timed_out", "deadline_exceeded")

    def retain_sneak(self, session: str) -> None:
        """Record authorized stance intent, not a new owner or an active-key proof."""
        self.check()
        if not self.execution_options.sneak_reuse:return
        if not isinstance(session,str) or not session:
            raise SkillStop('blocked','actor_session_required')
        if self.retained_sneak_session not in (None,session):
            raise SkillStop('blocked','actor_session_changed')
        self.retained_sneak_session=session

    def renew_retained_sneak(self, scene: dict) -> None:
        """Renew only after a fresh guarded observation in this same live context."""
        self.check()
        if self.retained_sneak_session is None:return
        if scene.get('actor_session')!=self.retained_sneak_session:
            raise SkillStop('blocked','actor_session_changed')
        if not scene.get('in_world') or not scene.get('alive'):
            raise SkillStop('blocked','live_player_required')
        self.player.drive(['sneak'],8,wait=False,actor_session=self.retained_sneak_session)

    def release_retained_sneak(self) -> None:
        self.check()
        if self.retained_sneak_session is not None:
            self.player.stop()
            self.retained_sneak_session=None

    def pause(self, seconds: float) -> None:
        # Small waits keep cooperative cancellation responsive without another game action.
        remaining = seconds
        while remaining > 0:
            self.check()
            duration = min(remaining, .05)
            self.sleeper(duration)
            remaining -= duration
        self.check()


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    description: str
    parameters: type[SkillParameters]
    handler: Callable[[SkillContext, Any], SkillResult]
    controls_player: bool = True


class SkillRegistry:
    def __init__(self):
        self._definitions: dict[str, SkillDefinition] = {}

    def register(self, definition: SkillDefinition) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", definition.name):
            raise ValueError("Invalid skill name")
        if definition.name in self._definitions:
            raise ValueError("Duplicate skill name")
        if not issubclass(definition.parameters, SkillParameters):
            raise TypeError("Skill parameters must inherit SkillParameters")
        self._definitions[definition.name] = definition

    def prepare(self, name: str, parameters: dict[str, Any]):
        if name not in self._definitions:
            raise ValueError("Unknown skill")
        definition = self._definitions[name]
        return definition, definition.parameters.model_validate(parameters)

    def describe(self) -> list[dict[str, Any]]:
        return [{"name": d.name, "description": d.description, "controls_player": d.controls_player,
                 "parameters": d.parameters.model_json_schema()} for d in self._definitions.values()]


def load_selected_plugins(registry: SkillRegistry, selection: str | None = None) -> None:
    """Execute ONLY explicitly selected installed entry-point providers. Trusted host code."""
    selection = _environment("BLOCKWIRE_SKILLS", "") if selection is None else selection
    names = [name.strip() for name in selection.split(",") if name.strip()]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate selected skill provider")
    installed = list(entry_points(group="blockwire.skills")) + list(entry_points(group="block_bridge.skills"))
    for name in names:
        matches = [entry for entry in installed if entry.name == name]
        if len(matches) != 1:
            raise ValueError(f"Skill provider is absent or ambiguous: {name}")
        matches[0].load()(registry)


def _execute(definition, parameters, player, cancellation, publish, clock, sleeper, *, execution_options=None) -> SkillResult:
    if execution_options is not None and not isinstance(execution_options,ExecutionOptions):
        raise ValueError('Typed trusted-host execution options required')
    context = SkillContext(player, cancellation, clock() + parameters.timeout_seconds, publish, clock, sleeper,
                           execution_options or ExecutionOptions())
    result = None
    try:
        context.check()
        result = definition.handler(context, parameters)
        if not isinstance(result, SkillResult):
            raise TypeError("Skill handler must return SkillResult")
        context.check()
    except SkillStop as stop:
        result = SkillResult(status=stop.status, reason=stop.reason, text=stop.reason.replace("_", " "))
    except BridgeError as error:
        reason = str(error)
        if isinstance(error,NativeOperationError) or reason in {"actor_session_changed", "player_dead", "not_in_world", "close_screen_first", "target_entity_changed"}:
            result = SkillResult(status="blocked", reason=reason, text="Native control precondition changed: "+reason)
        else:
            result = SkillResult(status="failed", reason="transport_error", text="Transport failed; observe before retrying.")
    except Exception as error:
        result = SkillResult(status="failed", reason="handler_error",
                             text="Skill failed; no action is automatically retried.",
                             details={"error_type": type(error).__name__})
    finally:
        # Cached adapters and stance intent never escape the owning skill. Native
        # cleanup remains unconditional and uses the existing player/owner lease.
        context.active=False
        context.retained_sneak_session=None
        context.placement_session=None
        if definition.controls_player:
            try:
                player.stop()
                if result is not None:
                    result.cleanup = "released"
            except Exception:
                if result is not None:
                    result.cleanup = "not_confirmed"
                    if result.status == "succeeded":
                        result.status, result.reason = "failed", "stop_not_confirmed"
                        result.text = "Goal reached, but input release was not confirmed."
    return result


def run_skill(registry: SkillRegistry, player: Player, name: str, parameters: dict[str, Any], *,
              cancel_event: threading.Event | None = None, publish: Callable | None = None,
              clock=time.monotonic, sleeper=time.sleep, execution_options=None) -> SkillResult:
    if execution_options is not None and not isinstance(execution_options,ExecutionOptions):
        raise ValueError('Typed trusted-host execution options required')
    # Validation precedes cleanup or any game action.
    definition, validated = registry.prepare(name, parameters)
    cancellation = cancel_event or threading.Event()
    lease = claim_control(player, cancellation.set) if definition.controls_player else None
    try:
        return _execute(definition, validated, player, cancellation,
                        publish or (lambda _: None), clock, sleeper,execution_options=execution_options)
    finally:
        if lease is not None:
            release_control(player, lease)


class SkillManager:
    """One cooperative worker per actor; bounded history, prompt status/cancel access."""
    def __init__(self, registry: SkillRegistry, player: Player):
        self.registry, self.player = registry, player
        self._lock = threading.RLock()
        self._jobs: OrderedDict[str, dict] = OrderedDict()
        self._active: str | None = None

    def start(self, name: str, parameters: dict[str, Any]) -> dict:
        definition, validated = self.registry.prepare(name, parameters)
        with self._lock:
            self.ensure_idle()
            event = threading.Event()
            lease = claim_control(self.player, event.set) if definition.controls_player else None
            job_id = str(uuid4())
            self._jobs[job_id] = {"id": job_id, "skill": name, "status": "running", "progress": {}, "event": event}
            self._active = job_id
            while len(self._jobs) > 20:
                self._jobs.popitem(last=False)
            def publish(progress):
                with self._lock:
                    self._jobs[job_id]["progress"] = dict(progress)
            def work():
                try:
                    result = _execute(definition, validated, self.player, event, publish, time.monotonic, time.sleep)
                except BaseException:
                    result = SkillResult(status="failed", reason="worker_terminated", text="Skill worker terminated.")
                with self._lock:
                    job = self._jobs[job_id]
                    job["status"], job["result"] = result.status, result.model_dump(mode="json")
                    self._active = None
                    if lease is not None:
                        release_control(self.player, lease)
            try:
                threading.Thread(target=work, name="blockwire-skill", daemon=True).start()
            except BaseException:
                self._active = None
                del self._jobs[job_id]
                if lease is not None:
                    release_control(self.player, lease)
                raise
            return self.status(job_id)

    def ensure_idle(self) -> None:
        with self._lock:
            if self._active is not None or control_busy(self.player):
                raise RuntimeError(BUSY)

    def status(self, job_id: str) -> dict:
        with self._lock:
            if job_id not in self._jobs:
                raise ValueError("Unknown or expired job ID")
            return {key: value for key, value in self._jobs[job_id].items() if key != "event"}

    def cancel(self, job_id: str | None = None) -> dict:
        with self._lock:
            selected = job_id or self._active
            if selected is None:
                return {"status": "idle"}
            if selected not in self._jobs:
                raise ValueError("Unknown or expired job ID")
            self._jobs[selected]["event"].set()
            return {"id": selected, "cancellation_requested": self._jobs[selected]["status"] == "running"}
