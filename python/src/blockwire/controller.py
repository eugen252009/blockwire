"""Explicit, bounded standalone controllers. Trusted host Python, never an in-game interpreter."""
from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass, field
import inspect
import math
import threading
import time
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .client import Bridge, BridgeError, CallableBackend, Player
from .ownership import claim_control, release_control
from .skills import default_registry
from .skills.core import SkillResult, _execute

EVENTS = frozenset({"ready", "health_changed", "death", "actor_changed", "disconnected", "skill_finished", "stopped"})
TERMINAL_EVENTS = frozenset({"death", "actor_changed", "disconnected", "stopped"})
ALL_RESOURCES = frozenset({"movement", "yaw", "pitch", "hand", "hotbar", "screen"})
# Deliberately small: ordinary non-placeable foods without intentional negative effects.
FOOD = frozenset("minecraft:" + item for item in (
    "bread", "apple", "cooked_beef", "cooked_porkchop", "cooked_chicken", "cooked_mutton",
    "cooked_rabbit", "cooked_cod", "cooked_salmon", "baked_potato"))
LEASE_TICKS = 8


async def _drain(task):
    """Join an owned thread/RPC even if its caller is cancelled repeatedly."""
    while not task.done():
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
    return task.result()


class ControllerParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    duration_seconds: float = Field(default=60, ge=.1, le=600)
    hz: float = Field(default=10, ge=2, le=20)
    callback_timeout_seconds: float = Field(default=2, ge=.05, le=10)


class EatParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    hotbar_slot: int = Field(ge=0, le=8)
    timeout_seconds: float = Field(default=8, ge=.1, le=30)


class ResourceBusy(RuntimeError):
    """Another task owns a required resource; no input has been changed."""


class ControllerStopped(RuntimeError):
    pass


@dataclass(frozen=True)
class ControllerState:
    ready: bool
    actor_session: str | None
    position: tuple | None
    health: float | None
    hunger: int | None
    hostiles: tuple
    sampled_at: float


@dataclass(frozen=True)
class Event:
    name: str
    data: dict


@dataclass(frozen=True)
class ControllerResult:
    status: str
    reason: str
    cleanup: str
    errors: tuple[str, ...] = ()


@dataclass(eq=False)
class _Control:
    name: str
    resources: frozenset
    task: asyncio.Task
    deadline: float
    cancellation: threading.Event = field(default_factory=threading.Event)
    buttons: tuple = ()
    expires: float = 0
    ticks: int = 1
    sky: bool = False
    blocked_reason: str | None = None


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


class Controller:
    """One actor owner, standard asyncio tasks, one serialized native input writer.

    Use run(script), whose optional setup(bot) and required loop(bot) are local
    callables. loop invocations never overlap. Use TaskGroup for parallel goals.
    State/events are partial client observations, not safety or server guarantees.
    """
    def __init__(self, player: Player, **parameters):
        self.parameters = ControllerParameters.model_validate(parameters)
        self._player = player
        self._registry = default_registry()  # No provider auto-loading.
        self._callbacks: dict[str, list] = {}
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=32)
        self._terminal: dict[str, Event] = {}
        self._gate = asyncio.Lock()
        self._stop = asyncio.Event()
        self._controls: set[_Control] = set()
        self._background: list[asyncio.Task] = []
        self._nav: dict = {}
        self._scene: dict = {}
        self._sampled_at = 0.
        self._session = None
        self._held: frozenset = frozenset()
        self._yaw = self._pitch = 0.
        self._deadline = 0.
        self._reason = None
        self._errors: list[str] = []
        self._closing = self._started = self._setup_done = self._transport_lost = False

    @property
    def state(self) -> ControllerState:
        nav = self._nav
        return ControllerState(bool(nav.get("ready") and not self._stop.is_set() and not self._closing), nav.get("actor_session"),
            tuple(nav["position"]) if "position" in nav else None, nav.get("health"), self._scene.get("hunger"),
            _freeze(nav.get("nearby_hostiles", [])), self._sampled_at)

    def on(self, name: str, callback) -> None:
        if name not in EVENTS or not callable(callback):
            raise ValueError("Unknown event or non-callable callback")
        if sum(map(len, self._callbacks.values())) >= 32:
            raise ValueError("At most 32 event subscriptions")
        self._callbacks.setdefault(name, []).append(callback)

    def stop(self) -> None:
        """Request runner shutdown. Await run() for confirmed cleanup; this is not a safe shelter."""
        self._signal("requested")

    def _signal(self, reason):
        if self._reason is None:
            self._reason = reason
        self._stop.set()

    def _emit(self, name, **data):
        event = Event(name, copy.deepcopy(data))
        if name in TERMINAL_EVENTS:
            self._terminal[name] = event  # At most four terminal notifications.
        elif not self._closing:
            try:
                self._queue.put_nowait(event)
            except asyncio.QueueFull:
                self._signal("event_queue_overflow")

    def _check(self, control=None, *, fresh=False):
        if self._closing or self._stop.is_set():
            raise ControllerStopped(self._reason or "controller_stopped")
        if time.monotonic() >= self._deadline:
            self._signal("deadline_exceeded")
            raise ControllerStopped("deadline_exceeded")
        if control is not None and (control.cancellation.is_set() or time.monotonic() >= control.deadline):
            raise ControllerStopped("action_cancelled_or_timed_out")
        if fresh and time.monotonic() - self._sampled_at > .5:
            self._signal("stale_navigation")
            raise ControllerStopped("stale_navigation")

    async def _wire(self, op, **arguments):
        # Caller holds _gate. Cancellation must drain an in-flight RPC before
        # cleanup/ownership reuse: to_thread cancellation cannot kill its thread.
        work = asyncio.create_task(asyncio.to_thread(self._player.backend.call, op, **arguments))
        try:
            return await asyncio.shield(work)
        except asyncio.CancelledError:
            try:
                await _drain(work)
            except Exception as error:
                self._wire_error(error)
            raise
        except Exception as error:
            self._wire_error(error)
            raise

    def _wire_error(self, error):
        reason = str(error)
        if isinstance(error, BridgeError) and reason in {
                "actor_session_changed", "player_dead", "not_in_world", "close_screen_first", "target_entity_changed"}:
            if reason == "actor_session_changed":
                self._emit("actor_changed", previous=self._session, current=None)
            elif reason == "player_dead":
                self._emit("death", health=None)
            elif reason == "not_in_world":
                self._emit("disconnected", reason=reason)
            self._signal(reason)
        else:
            # No reconnect, retry, or further RPC on an uncertain connection.
            self._transport_lost = True
            self._emit("disconnected", reason="transport_error")
            self._signal("transport_error")

    async def _read(self, op):
        async with self._gate:
            self._check()
            value = await self._wire(op)
            if op == "navigation":
                self._accept_navigation(value)
            elif op == "observe":
                if value.get("actor_session") != self._session:
                    self._emit("actor_changed", previous=self._session, current=value.get("actor_session"))
                    self._signal("actor_session_changed")
                    raise ControllerStopped("actor_session_changed")
                self._scene = copy.deepcopy(value)
            return value

    def _accept_navigation(self, value):
        previous = self._nav
        self._nav = copy.deepcopy(value)
        self._sampled_at = time.monotonic()
        if value.get("profile") != "flat_full_blocks_v1" or not isinstance(value.get("actor_session"), str):
            self._signal("unsupported_navigation_profile")
        elif self._session is not None and value["actor_session"] != self._session:
            self._emit("actor_changed", previous=self._session, current=value["actor_session"])
            self._signal("actor_session_changed")
        else:
            self._session = value["actor_session"]
            if previous.get("health") is not None and previous["health"] != value.get("health"):
                self._emit("health_changed", previous=previous["health"], current=value.get("health"))
        if value.get("alive") is False:
            self._emit("death", health=value.get("health"))
        if value.get("reason") == "not_in_world":
            self._emit("disconnected", reason="not_in_world")
        if not value.get("ready"):
            self._signal(value.get("reason", "navigation_not_ready"))
        self._check()

    def _acquire(self, name, resources, timeout):
        self._check(fresh=True)
        resources = frozenset(resources)
        if any(resources & control.resources for control in self._controls):
            raise ResourceBusy("Conflicting controller resources; await or cancel the other action first")
        control = _Control(name, resources, asyncio.current_task(), min(self._deadline, time.monotonic() + timeout))
        self._controls.add(control)
        return control

    async def _view_locked(self):
        pitch = -90. if any(c.sky for c in self._controls) else self._pitch
        return await self._wire("look", yaw=self._yaw, pitch=pitch, actor_session=self._session)

    async def _flush_locked(self, renew=None):
        self._check(fresh=True)
        now = time.monotonic()
        active = [c for c in self._controls if c.buttons and c.expires > now and not c.cancellation.is_set()]
        buttons = frozenset(button for control in active for button in control.buttons)
        if buttons or self._held:
            # Only an explicit new pulse restarts movement. Other writers retain
            # its native deadline/tick budget; eating can never stretch it.
            per_button = {button: (min(LEASE_TICKS, max(1, math.floor((c.expires-now)/.05)))
                          if c.sky else c.ticks) for c in active if c is renew or c.sky for button in c.buttons}
            ticks = LEASE_TICKS if buttons else 1
            await self._wire("drive", buttons=sorted(buttons), ticks=ticks,
                             button_ticks=per_button, actor_session=self._session)
            self._held = buttons
        return {"text": "Owned inputs updated; not a gameplay outcome."}

    async def _buttons(self, control, buttons, seconds):
        async with self._gate:
            self._check(control, fresh=True)
            control.buttons, control.expires = tuple(buttons), min(control.deadline, time.monotonic() + seconds)
            return await self._flush_locked(renew=control)

    async def _release(self, control, result):
        try:
            async with self._gate:
                self._controls.discard(control)
                if self._closing or self._stop.is_set():
                    raise ControllerStopped("runner_cleanup_pending")
                await self._flush_locked()
                if control.sky:
                    await self._view_locked()
            if result is not None:
                result.cleanup = "released"
        except Exception:
            if result is not None:
                result.cleanup = "not_confirmed"
                if result.status == "succeeded":
                    result.status, result.reason = "failed", "stop_not_confirmed"
        finally:
            self._controls.discard(control)
            if result is not None:
                self._emit("skill_finished", skill=control.name, result=result.model_dump(mode="json"))

    async def _skill_call(self, control, op, arguments):
        if op == "stop":
            # A legacy skill's finally must never issue a global native stop.
            async with self._gate:
                control.buttons, control.expires = (), 0
                if not self._closing and not self._stop.is_set():
                    return await self._flush_locked()
                return {"text": "Owned contribution cleared; runner cleanup pending."}
        self._check(control)
        if op in {"navigation", "observe", "inventory"}:
            return await self._read(op)
        if op not in {"look", "drive", "action", "hotbar"}:
            raise BridgeError("unsupported_controller_operation")
        if op != "hotbar" and arguments.get("actor_session") != self._session:
            raise BridgeError("actor_session_required")
        async with self._gate:
            self._check(control, fresh=True)
            if op == "look":
                self._yaw, self._pitch = arguments["yaw"], arguments["pitch"]
                return await self._view_locked()
            if op == "drive":
                control.buttons = tuple(arguments["buttons"])
                control.ticks = min(LEASE_TICKS, arguments["ticks"])
                control.expires = min(control.deadline, time.monotonic() + control.ticks*.05)
                return await self._flush_locked(renew=control)
            return await self._wire(op, **{**arguments, "actor_session": self._session})

    async def _skill(self, name, parameters, resources):
        definition, goal = self._registry.prepare(name, parameters)
        control = self._acquire(name, resources, goal.timeout_seconds)
        loop = asyncio.get_running_loop()
        def dispatch(request):
            op, arguments = request["op"], {k: v for k, v in request.items() if k != "op"}
            if op != "stop" and control.cancellation.is_set():
                raise BridgeError("controller_action_cancelled")
            return asyncio.run_coroutine_threadsafe(self._skill_call(control, op, arguments), loop).result()
        facade = Player(CallableBackend(dispatch))
        worker = asyncio.create_task(asyncio.to_thread(_execute, definition, goal, facade, control.cancellation,
            lambda _: None, time.monotonic, time.sleep))
        result = None
        try:
            result = await asyncio.shield(worker)
        except asyncio.CancelledError:
            control.cancellation.set()
            result = await _drain(worker)
            raise
        finally:
            control.cancellation.set()
            await self._release(control, result)
        return result.model_dump(mode="json")

    async def walk_to(self, x: float, y: float, z: float, *, sneak=False, avoid_damage=True, timeout_seconds=30):
        """Reuse the synchronous flat-ground walker; movement/yaw can coexist with eating."""
        return await self._skill("walk_to", dict(x=x, y=y, z=z, sneak=sneak,
            avoid_damage=avoid_damage, timeout_seconds=timeout_seconds), {"movement", "yaw"})

    async def skill(self, name: str, **parameters):
        """Other built-in goals run exclusively, not as competing legacy input writers."""
        return await self._skill(name, parameters, ALL_RESOURCES)

    async def observe(self):
        return await self._read("observe")

    async def inventory(self):
        return await self._read("inventory")

    async def _hotbar(self, control, slot):
        async with self._gate:
            self._check(control, fresh=True)
            return await self._wire("hotbar", slot=slot, actor_session=self._session)

    async def eat(self, *, hotbar_slot: int, timeout_seconds: float = 8):
        """Ordinary allowlisted food, empty offhand and clear upward crosshair only.

        Success requires observed hunger gain AND a reduced food stack. This may
        consume more than one item under latency. Restore the original slot on
        normal completion only, never force it after cancellation/session loss.
        """
        goal = EatParameters(hotbar_slot=hotbar_slot, timeout_seconds=timeout_seconds)
        control = self._acquire("eat", {"hand", "hotbar", "pitch"}, goal.timeout_seconds)
        result = None
        original = None
        def outcome(status, reason):
            return SkillResult(status=status, reason=reason, text=reason.replace("_", " "))
        def food(inventory):
            return next((i for i in inventory["items"] if i["inventory_index"] == goal.hotbar_slot), {})
        try:
            if not self._nav.get("hotbar_actor_session"):
                result = outcome("blocked", "guarded_hotbar_required")
            else:
                scene, inventory = await self.observe(), await self.inventory()
                before = food(inventory)
                initial_hunger = scene.get("hunger", 20)
                if scene.get("hunger", 20) >= 20:
                    result = outcome("succeeded", "already_full")
                elif before.get("item") not in FOOD or before.get("count", 0) < 1:
                    result = outcome("blocked", "select_supported_food")
                elif any(i["inventory_index"] == 40 and not i.get("empty", False) for i in inventory["items"]):
                    result = outcome("blocked", "empty_offhand_required")
                else:
                    original = inventory["selected_hotbar"]
                    await self._hotbar(control, goal.hotbar_slot)
                    async with self._gate:
                        self._check(control, fresh=True)
                        self._yaw = scene["yaw"] if not any("yaw" in c.resources for c in self._controls) else self._yaw
                        control.sky = True
                        await self._view_locked()
                    await asyncio.sleep(.08)  # Native crosshair refreshes on the next rendered frame.
                    while True:
                        if time.monotonic() >= control.deadline:
                            result = outcome("timed_out", "deadline_exceeded")
                            break
                        self._check(control)
                        await self._read("navigation")
                        scene, inventory = await self.observe(), await self.inventory()
                        current = food(inventory)
                        # Compare against the actual pre-use observation, not a receipt.
                        if inventory["selected_hotbar"] != goal.hotbar_slot or current.get("item") != before.get("item"):
                            # An exhausted stack is valid only with observed hunger gain (below).
                            if not current and scene.get("hunger", 0) > initial_hunger:
                                result = outcome("succeeded", "food_consumed")
                            else:
                                result = outcome("blocked", "selected_food_changed")
                            break
                        if scene.get("hunger", 0) > initial_hunger and current.get("count", 0) < before["count"]:
                            result = outcome("succeeded", "food_consumed")
                            break
                        if control.blocked_reason or scene.get("target") or scene.get("pitch", 0) > -89 or scene.get("holding", {}).get("item") != before["item"]:
                            result = outcome("blocked", "clear_upward_food_use_required")
                            break
                        await self._buttons(control, ["use"], max(0., control.deadline-time.monotonic()))
                        await asyncio.sleep(.1)
            if original is not None and not self._stop.is_set() and time.monotonic() < control.deadline:
                await self._buttons(control, [], max(.01, control.deadline-time.monotonic()))
                inventory = await self.inventory()
                if inventory["selected_hotbar"] == goal.hotbar_slot and time.monotonic() < control.deadline:
                    await self._hotbar(control, original)
        except asyncio.CancelledError:
            result = outcome("cancelled", "cancel_requested")
            raise
        except ControllerStopped:
            result = outcome("timed_out" if time.monotonic() >= control.deadline else "blocked",
                             self._reason or "deadline_exceeded")
        finally:
            control.cancellation.set()
            await self._release(control, result)
        return result.model_dump(mode="json")

    async def _deliver(self, event):
        for callback in tuple(self._callbacks.get(event.name, ())):
            async with asyncio.timeout(self.parameters.callback_timeout_seconds):
                value = callback(self, Event(event.name, copy.deepcopy(event.data)))
                if inspect.isawaitable(value):
                    await value

    async def _events(self):
        while True:
            await self._deliver(await self._queue.get())

    async def _monitor(self):
        while True:
            await self._read("navigation")
            scene = await self.observe()
            async with self._gate:
                for control in self._controls:
                    if control.sky and control.buttons and (scene.get("target") or scene.get("pitch", 0) > -89
                            or scene.get("holding", {}).get("item") not in FOOD):
                        control.blocked_reason = "clear_upward_food_use_required"
                        control.buttons = ()
                await self._flush_locked()
            await asyncio.sleep(1/max(10., self.parameters.hz))

    async def _script(self, setup, loop):
        if setup is not None:
            value = setup(self)
            if inspect.isawaitable(value):
                await value
        self._setup_done = True
        self._emit("ready", actor_session=self._session)
        while True:
            self._check()
            value = loop(self)
            if inspect.isawaitable(value):
                await value
            await asyncio.sleep(1/self.parameters.hz)

    async def _guard(self, coroutine, reason):
        try:
            await coroutine
        except asyncio.CancelledError:
            if not self._closing:
                self._signal("script_cancelled")
            raise
        except (ControllerStopped, BridgeError):
            if not self._stop.is_set():
                self._signal(reason)
        except Exception as error:
            self._errors.append(type(error).__name__)
            self._signal("callback_timeout" if reason == "callback_error" and isinstance(error, TimeoutError) else reason)

    async def _shutdown(self):
        self._closing = True
        current = asyncio.current_task()
        tasks = set(self._background) | {c.task for c in self._controls}
        for control in self._controls:
            control.cancellation.set()
        for task in tasks - {current}:
            if not task.done() and not task.cancelling():
                task.cancel()
        await asyncio.gather(*(task for task in tasks if task is not current), return_exceptions=True)
        cleanup = "not_confirmed"
        if not self._transport_lost:
            try:
                async with self._gate:
                    await self._wire("stop")
                cleanup = "released"
            except Exception:
                pass
        self._controls.clear()
        self._emit("stopped", reason=self._reason, cleanup=cleanup)
        for event in tuple(self._terminal.values()):
            try:
                await self._deliver(event)
            except Exception as error:
                self._errors.append(type(error).__name__)
        return cleanup

    async def run(self, script) -> ControllerResult:
        setup, loop = getattr(script, "setup", None), getattr(script, "loop", None)
        if not callable(loop) or (setup is not None and not callable(setup)):
            raise ValueError("Controller needs loop(bot) and optionally setup(bot)")
        if self._started:
            raise RuntimeError("A Controller is single-use")
        event_loop = asyncio.get_running_loop()
        lease = claim_control(self._player, lambda: event_loop.call_soon_threadsafe(self.stop))
        self._started = True
        self._deadline = time.monotonic() + self.parameters.duration_seconds
        cleanup = "not_confirmed"
        try:
            try:
                await self._read("navigation")
                if not (self._nav.get("hotbar_actor_session") and self._nav.get("independent_input_leases")):
                    self._signal("controller_mod_upgrade_required")
                    raise ControllerStopped("controller_mod_upgrade_required")
                scene = await self.observe()
                self._yaw, self._pitch = scene.get("yaw", 0.), scene.get("pitch", 0.)
                self._background = [asyncio.create_task(self._guard(coro, reason)) for coro, reason in (
                    (self._monitor(), "monitor_error"), (self._events(), "callback_error"),
                    (self._script(setup, loop), "script_error"))]
                try:
                    async with asyncio.timeout(max(0., self._deadline-time.monotonic())):
                        await self._stop.wait()
                except TimeoutError:
                    self._signal("deadline_exceeded")
            except (ControllerStopped, BridgeError):
                pass
        finally:
            self._closing = True
            shutdown = asyncio.create_task(self._shutdown())
            try:
                try:
                    cleanup = await asyncio.shield(shutdown)
                except asyncio.CancelledError:
                    await _drain(shutdown)
                    raise
            finally:
                release_control(self._player, lease)
        reason = self._reason or "requested"
        if reason == "requested" and (cleanup != "released" or self._errors):
            reason = "stop_not_confirmed" if cleanup != "released" else "callback_error"
        status = ({"requested": "stopped", "deadline_exceeded": "timed_out", "script_cancelled": "cancelled"}
                  .get(reason, "blocked"))
        if self._errors or reason in {"transport_error", "event_queue_overflow"} or cleanup != "released":
            status = "failed"
        return ControllerResult(status, reason, cleanup, tuple(self._errors))


async def run_controller(script, *, player: Player | None = None, **parameters) -> ControllerResult:
    """Run an explicitly supplied trusted local script. No MCP or implicit imports."""
    connection = None
    if player is None:
        connection = Bridge.from_env()
        player = Player(connection)
    try:
        return await Controller(player, **parameters).run(script)
    finally:
        if connection is not None:
            await asyncio.to_thread(connection.close)
