"""CR01–CR19: controller contracts with a simulated native backend, NOT Minecraft acceptance."""
import asyncio
import copy
from dataclasses import FrozenInstanceError
import math
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pydantic import ValidationError
from blockwire import CallableBackend, Controller, Player, ResourceBusy
from blockwire.client import BridgeError
from blockwire.controller import _Control
from blockwire.controller_cli import load_controller
from blockwire.ownership import cancel_control, control_busy
from blockwire.skills import SkillManager, default_registry, run_skill
from test_skills import FlatPlayer


class Native:
    """Simulation of native per-key leases, physics and food consumption, not real gameplay."""
    def __init__(self):
        self.flat = FlatPlayer()
        self.flat.yaw = -90.
        self.pitch = 0.
        self.hunger = 12
        self.slot = 0
        self.count = 3
        self.offhand = False
        self.item = "minecraft:bread"
        self.calls = []
        self.effects = []
        self.deadlines = {}
        self.last = time.monotonic()
        self.progress = 0.
        self.consume_seconds = .16
        self.hunger_gain = True
        self.decrease_count = True
        self.target = None
        self.before_hotbar = None
        self.before_observe = None
        self.connected = True
        self.drive_entered = threading.Event()
        self.drive_release = None
        self.capabilities = True
        self.stop_fails = False
        self.overlap = False

    def advance(self):
        now = time.monotonic()
        forward = max(0., min(now, self.deadlines.get("forward", 0))-self.last)
        if forward:
            speed = 1.3 if self.deadlines.get("sneak", 0) > self.last else 4.3
            self.flat.position[0] -= math.sin(math.radians(self.flat.yaw))*forward*speed
            self.flat.position[2] += math.cos(math.radians(self.flat.yaw))*forward*speed
        use = max(0., min(now, self.deadlines.get("use", 0))-self.last)
        if use and forward:
            self.overlap = True
        if use and self.slot == 8 and self.count and self.hunger < 20:
            self.progress += use
            if self.progress >= self.consume_seconds:
                if self.decrease_count:
                    self.count -= 1
                if self.hunger_gain:
                    self.hunger = min(20, self.hunger+4)
                self.progress = 0.
        if self.deadlines.get("use", 0) < now:
            self.progress = 0.
        self.last = now

    def call(self, op, **q):
        self.advance()
        self.calls.append((op, copy.deepcopy(q)))
        if not self.connected:
            if not hasattr(self, "failure_index"):
                self.failure_index = len(self.calls)-1
            raise BridgeError("Bridge connection failed; operation outcome may be unknown. Observe before retrying.")
        if op == "navigation":
            nav = self.flat.navigation()
            nav.update(hotbar_actor_session=self.capabilities, independent_input_leases=self.capabilities)
            return nav
        if op == "observe":
            if self.before_observe:
                self.before_observe()
                self.before_observe = None
            return dict(actor_session=self.flat.session, in_world=True, alive=self.flat.health > 0, yaw=self.flat.yaw, pitch=self.pitch,
                position=self.flat.position[:], health=self.flat.health, hunger=self.hunger,
                target=self.target, holding={"item": self.item if self.slot == 8 else "minecraft:wooden_sword"})
        if op == "inventory":
            items = ([dict(inventory_index=8, item=self.item, count=self.count)] if self.count else [])
            if self.offhand:
                items.append(dict(inventory_index=40, item="minecraft:torch", count=1))
            return dict(items=items, selected_hotbar=self.slot)
        if op == "stop":
            if self.stop_fails:
                raise BridgeError("uncertain stop")
            self.deadlines.clear()
            return {"text": "released"}
        if op == "drive" and q["buttons"]:
            self.drive_entered.set()
            if self.drive_release is not None:
                self.drive_release.wait(2)
        if op == "hotbar" and self.before_hotbar:
            self.before_hotbar()
            self.before_hotbar = None
        if "actor_session" in q and q["actor_session"] != self.flat.session:
            raise BridgeError("actor_session_changed")
        self.effects.append((self.flat.session, op, copy.deepcopy(q)))
        if op == "look":
            self.flat.yaw, self.pitch = q["yaw"], q["pitch"]
        elif op == "hotbar":
            self.slot = q["slot"]
        elif op == "drive":
            assert 1 <= q["ticks"] <= 100
            durations = q.get("button_ticks", {key: q["ticks"] for key in q["buttons"]})
            assert set(durations) <= set(q["buttons"])
            assert all(1 <= ticks <= q["ticks"] for ticks in durations.values())
            if "use" not in q["buttons"]:
                self.progress = 0.
            retained = {key: deadline for key, deadline in self.deadlines.items()
                        if key in q["buttons"] and deadline > time.monotonic()}
            retained.update({key: time.monotonic()+ticks*.05 for key, ticks in durations.items()})
            self.deadlines = retained
        else:
            raise AssertionError(op)
        return {"text": "submitted, not an outcome"}


async def until(predicate):
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(.001)


class ControllerContracts(unittest.IsolatedAsyncioTestCase):
    async def run_script(self, loop, *, setup=None, native=None, **parameters):
        native = native or Native()
        bot = Controller(Player(native), duration_seconds=3., **parameters)
        result = await bot.run(SimpleNamespace(loop=loop, setup=setup))
        self.assertFalse(control_busy(bot._player))
        return result, native, bot

    async def test_CR01_setup_once_nonoverlapping_loop_state_and_ready(self):
        counts = dict(setup=0, loop=0, ready=0, running=0)
        async def ready(bot, event):
            counts["ready"] += 1
        async def setup(bot):
            counts["setup"] += 1
            bot.on("ready", ready)
            self.assertTrue(bot.state.ready)
            with self.assertRaises(FrozenInstanceError):
                bot.state.health = 1
            self.assertIsInstance(bot.state.position, tuple)
        async def loop(bot):
            self.assertEqual(counts["running"], 0)
            counts["running"] += 1
            await asyncio.sleep(.01)
            counts["running"] -= 1
            counts["loop"] += 1
            if counts["loop"] == 3:
                bot.stop()
        result, native, bot = await self.run_script(loop, setup=setup)
        self.assertEqual(result.status, "stopped")
        self.assertEqual(counts, dict(setup=1, loop=3, ready=1, running=0))
        self.assertFalse(bot.state.ready)
        self.assertEqual(native.calls[-1][0], "stop")

    async def test_CR02_walk_and_eat_overlap_observed_goals_and_scoped_cleanup(self):
        outcomes, events = {}, []
        async def setup(bot):
            bot.on("skill_finished", lambda bot, event: events.append(event.data))
        async def loop(bot):
            async with asyncio.TaskGroup() as group:
                walk = group.create_task(bot.walk_to(2.5, 64., .5, avoid_damage=False))
                eat = group.create_task(bot.eat(hotbar_slot=8))
            outcomes.update(walk=walk.result(), eat=eat.result())
            await until(lambda: len(events) == 2)
            bot.stop()
        result, native, _ = await self.run_script(loop, setup=setup)
        self.assertEqual(result.status, "stopped", result)
        self.assertEqual([outcomes[k]["status"] for k in ("walk", "eat")], ["succeeded"]*2)
        self.assertTrue(native.overlap)
        self.assertGreater(native.hunger, 12)
        self.assertLess(native.count, 3)
        self.assertEqual(native.slot, 0)
        drives = [q for op, q in native.calls if op == "drive"]
        combined = [q for q in drives if {"forward", "use"} <= set(q["buttons"])]
        self.assertTrue(combined)
        self.assertTrue(all(q["ticks"] <= 8 and all(t <= 8 for t in q["button_ticks"].values()) for q in drives))
        self.assertTrue(any(q["button_ticks"].get("forward", 0) < q["button_ticks"]["use"] for q in combined))
        self.assertEqual(sum(op == "stop" for op, _ in native.calls), 1)
        self.assertTrue(all(q["actor_session"] == "actor-a" for _, op, q in native.effects))

    async def test_CR27_scoped_observation_hides_temporary_food_pitch_override(self):
        native = Native();native.pitch = -90.
        bot = Controller(Player(native), duration_seconds=3.)
        bot._deadline = time.monotonic()+2.;bot._session = native.flat.session;bot._pitch = 12.
        task = asyncio.current_task();deadline = time.monotonic()+1.
        observer = _Control('observer', frozenset({'movement'}), task, deadline)
        eater = _Control('eater', frozenset({'food'}), task, deadline, sky=True)
        bot._controls = {observer,eater}
        scene = await bot._skill_call(observer,'observe',{})
        self.assertEqual(scene['pitch'],12.)
        self.assertEqual(native.pitch,-90.)

    async def test_CR03_cancel_eating_does_not_cancel_or_stop_walking(self):
        native = Native()
        native.consume_seconds = 2.
        async def loop(bot):
            walk = asyncio.create_task(bot.walk_to(2.5, 64., .5, avoid_damage=False))
            eat = asyncio.create_task(bot.eat(hotbar_slot=8))
            await until(lambda: native.overlap)
            eat.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await eat
            cut = len(native.calls)
            self.assertEqual((await walk)["status"], "succeeded")
            self.assertTrue(any(op == "drive" and "forward" in q["buttons"] and "use" not in q["buttons"]
                                for op, q in native.calls[cut:]))
            bot.stop()
        result, native, _ = await self.run_script(loop, native=native)
        self.assertEqual(result.status, "stopped", result)
        self.assertEqual(native.count, 3)
        self.assertEqual(sum(op == "stop" for op, _ in native.calls), 1)

    async def test_CR04_cancel_walking_preserves_food_hold(self):
        native = Native()
        native.consume_seconds = .35
        async def loop(bot):
            walk = asyncio.create_task(bot.walk_to(4.5, 64., .5, avoid_damage=False))
            eat = asyncio.create_task(bot.eat(hotbar_slot=8))
            await until(lambda: native.overlap)
            walk.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await walk
            cut = len(native.calls)
            self.assertEqual((await eat)["status"], "succeeded")
            self.assertTrue(any(op == "drive" and q["buttons"] == ["use"] for op, q in native.calls[cut:]))
            bot.stop()
        result, native, _ = await self.run_script(loop, native=native)
        self.assertEqual(result.status, "stopped", result)
        self.assertEqual(sum(op == "stop" for op, _ in native.calls), 1)

    async def test_CR05_resource_conflict_has_no_effect_and_preserves_owner(self):
        async def loop(bot):
            walk = asyncio.create_task(bot.walk_to(1.5, 64., .5, avoid_damage=False))
            await until(lambda: native.drive_entered.is_set())
            cut = len(native.calls)
            with self.assertRaises(ResourceBusy):
                await bot.walk_to(-2., 64., .5)
            with self.assertRaises(ResourceBusy):
                await bot.skill("fight", duration_seconds=.1)
            self.assertEqual(len(native.calls), cut)
            self.assertEqual((await walk)["status"], "succeeded")
            bot.stop()
        native = Native()
        result, _, _ = await self.run_script(loop, native=native)
        self.assertEqual(result.status, "stopped", result)

    async def test_CR06_invalid_parameters_do_not_touch_native_inputs(self):
        async def loop(bot):
            cut = len(native.calls)
            for kwargs in [dict(hotbar_slot=True), dict(hotbar_slot=9), dict(hotbar_slot=8, timeout_seconds=math.nan)]:
                with self.assertRaises(ValidationError):
                    await bot.eat(**kwargs)
            with self.assertRaises(ValidationError):
                await bot.walk_to(math.inf, 64., .5)
            self.assertEqual(len(native.calls), cut)
            bot.stop()
        native = Native()
        result, _, _ = await self.run_script(loop, native=native)
        self.assertEqual(result.status, "stopped", result)
        for bad in [dict(duration_seconds=True), dict(hz=0), dict(duration_seconds=math.inf), dict(typo=1)]:
            with self.assertRaises(ValidationError):
                Controller(Player(native), **bad)

    async def test_CR07_receipts_or_stack_loss_without_hunger_are_not_success(self):
        native = Native()
        native.hunger_gain = False
        outcomes = []
        async def loop(bot):
            outcomes.append(await bot.eat(hotbar_slot=8, timeout_seconds=.5))
            bot.stop()
        result, _, _ = await self.run_script(loop, native=native)
        self.assertEqual(result.status, "stopped", result)
        self.assertNotEqual(outcomes[0]["status"], "succeeded")
        self.assertLess(native.count, 3)
        native = Native()
        native.decrease_count = False
        outcomes.clear()
        result, _, _ = await self.run_script(loop, native=native)
        self.assertEqual(result.status, "stopped", result)
        self.assertNotEqual(outcomes[0]["status"], "succeeded")
        self.assertGreater(native.hunger, 12)
        self.assertEqual(native.count, 3)

    async def test_CR08_food_offhand_crosshair_full_and_timeout_guards(self):
        for case, reason in [("item", "select_supported_food"), ("offhand", "empty_offhand_required"),
                             ("target", "clear_upward_food_use_required"), ("full", "already_full"),
                             ("slow", "deadline_exceeded")]:
            native = Native()
            if case == "item": native.item = "minecraft:pufferfish"
            if case == "offhand": native.offhand = True
            if case == "target": native.target = dict(kind="block", id="minecraft:chest")
            if case == "full": native.hunger = 20
            if case == "slow": native.consume_seconds = 10.
            outcomes = []
            async def loop(bot):
                outcomes.append(await bot.eat(hotbar_slot=8, timeout_seconds=.35))
                bot.stop()
            with self.subTest(case=case):
                result, _, _ = await self.run_script(loop, native=native)
                self.assertEqual(result.status, "stopped", result)
                self.assertEqual(outcomes[0]["reason"], reason)
                self.assertEqual(native.count, 3)
                if case != "slow":
                    self.assertFalse(any(op == "drive" and "use" in q["buttons"] for op, q in native.calls))

    async def test_CR09_actor_replacement_death_and_screen_stop_tasks(self):
        for reason in ["actor_session_changed", "player_dead", "screen_or_pause", "not_grounded"]:
            native = Native()
            events = []
            async def setup(bot):
                bot.on("actor_changed", lambda bot, event: events.append(event.name))
                bot.on("death", lambda bot, event: events.append(event.name))
            async def loop(bot):
                walk = asyncio.create_task(bot.walk_to(4.5, 64., .5, avoid_damage=False))
                await until(lambda: native.drive_entered.is_set())
                if reason == "actor_session_changed":
                    native.flat.session = "actor-b"
                else:
                    native.flat.transform = lambda s: dict(s, ready=False, reason=reason,
                        alive=reason != "player_dead", health=0. if reason == "player_dead" else 20.)
                await walk
            with self.subTest(reason=reason):
                result, _, _ = await self.run_script(loop, native=native, setup=setup)
                self.assertEqual(result.reason, reason)
                self.assertEqual(result.status, "blocked")
                self.assertEqual(result.cleanup, "released")
                self.assertFalse(any(actor == "actor-b" for actor, _, _ in native.effects))
                if reason == "actor_session_changed": self.assertIn("actor_changed", events)
                if reason == "player_dead": self.assertIn("death", events)

    async def test_CR10_hotbar_race_is_natively_fenced(self):
        native = Native()
        native.before_hotbar = lambda: setattr(native.flat, "session", "actor-b")
        async def loop(bot):
            await bot.eat(hotbar_slot=8)
        result, native, _ = await self.run_script(loop, native=native)
        self.assertEqual(result.reason, "actor_session_changed")
        self.assertEqual(native.slot, 0)
        self.assertFalse(native.effects)

    async def test_CR11_disconnect_never_reconnects_or_retries(self):
        native = Native()
        events = []
        async def setup(bot):
            bot.on("disconnected", lambda bot, event: events.append(event.data))
        async def loop(bot):
            native.connected = False
            await bot.observe()
        result, native, _ = await self.run_script(loop, native=native, setup=setup)
        self.assertEqual(result.reason, "transport_error")
        self.assertEqual(result.cleanup, "not_confirmed")
        self.assertEqual(len(native.calls), native.failure_index+1)
        self.assertEqual(len(events), 1)

    async def test_CR12_slow_callback_deadline_and_script_errors_cleanup(self):
        async def setup(bot):
            async def hung(bot, event):
                await asyncio.Event().wait()
            bot.on("ready", hung)
        result, native, _ = await self.run_script(lambda bot: None, setup=setup, callback_timeout_seconds=.05)
        self.assertEqual(result.reason, "callback_timeout")
        self.assertEqual(result.status, "failed")
        self.assertEqual(native.calls[-1][0], "stop")
        async def broken(bot):
            raise ValueError("trusted script failure")
        result, _, _ = await self.run_script(broken)
        self.assertEqual(result.reason, "script_error")
        self.assertEqual(result.errors, ("ValueError",))
        bot = Controller(Player(Native()), duration_seconds=.1)
        result = await bot.run(SimpleNamespace(loop=lambda bot: None))
        self.assertEqual(result.status, "timed_out")
        self.assertEqual(result.cleanup, "released")

    async def test_CR13_event_and_subscription_bounds(self):
        async def setup(bot):
            for _ in range(32): bot.on("ready", lambda bot, event: None)
            with self.assertRaises(ValueError): bot.on("ready", lambda bot, event: None)
            with self.assertRaises(ValueError): bot.on("unknown", lambda bot, event: None)
            for i in range(33): bot._emit("health_changed", current=i)
        result, _, _ = await self.run_script(lambda bot: None, setup=setup)
        self.assertEqual(result.reason, "event_queue_overflow")

    async def test_CR14_runtime_and_legacy_mcp_ownership_are_exclusive(self):
        native = Native()
        player = Player(native)
        other = Player(native)
        manager = SkillManager(default_registry(), other)
        async def loop(bot):
            with self.assertRaisesRegex(RuntimeError, "A skill owns player control"):
                manager.ensure_idle()
            with self.assertRaises(RuntimeError):
                manager.start("walk_to", dict(x=1., y=64., z=.5))
            with self.assertRaises(RuntimeError):
                run_skill(default_registry(), other, "walk_to", dict(x=1., y=64., z=.5))
            with self.assertRaises(RuntimeError):
                await Controller(other).run(SimpleNamespace(loop=lambda bot: bot.stop()))
            bot.stop()
        result = await Controller(player).run(SimpleNamespace(loop=loop))
        self.assertEqual(result.status, "stopped", result)
        manager.ensure_idle()

    async def test_CR15_repeated_cancellation_joins_inflight_rpc_before_reuse(self):
        native = Native()
        native.drive_release = threading.Event()
        player = Player(native)
        async def loop(bot):
            await bot.walk_to(2.5, 64., .5, avoid_damage=False)
        from blockwire.controller import _execute as execute
        finished = threading.Event()
        release_worker = threading.Event()
        def delayed_return(*args):
            result = execute(*args)
            finished.set()
            release_worker.wait(2)
            return result
        patched = patch("blockwire.controller._execute", delayed_return)
        patched.start()
        self.addCleanup(patched.stop)
        task = asyncio.create_task(Controller(player).run(SimpleNamespace(loop=loop)))
        await until(lambda: native.drive_entered.is_set())
        task.cancel()
        await asyncio.sleep(.02)
        task.cancel()
        await asyncio.sleep(.02)
        self.assertFalse(task.done())
        self.assertTrue(control_busy(player))
        native.drive_release.set()
        try:
            await until(finished.is_set)
            await asyncio.sleep(.02)
            self.assertFalse(task.done())
            self.assertTrue(control_busy(player))
        finally:
            release_worker.set()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2.)
        self.assertFalse(control_busy(player))
        self.assertEqual(native.calls[-1][0], "stop")
        self.assertFalse(native.deadlines)

    async def test_CR16_upgrade_stale_observation_and_cleanup_failure(self):
        native = Native()
        native.capabilities = False
        result, native, _ = await self.run_script(lambda bot: self.fail("must not run"), native=native)
        self.assertEqual(result.reason, "controller_mod_upgrade_required")
        self.assertEqual([op for op, _ in native.calls], ["navigation", "stop"])
        async def stale(bot):
            bot._sampled_at -= 1.
            await bot.walk_to(2., 64., .5)
        result, native, _ = await self.run_script(stale)
        self.assertEqual(result.reason, "stale_navigation")
        self.assertFalse(native.effects)
        native = Native()
        native.stop_fails = True
        result, _, _ = await self.run_script(lambda bot: bot.stop(), native=native)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.cleanup, "not_confirmed")

    async def test_CR17_selected_provider_only_and_ambiguity_before_load(self):
        selected = SimpleNamespace(name="selected", load=lambda: SimpleNamespace(loop=lambda bot: None))
        other = SimpleNamespace(name="other", load=lambda: self.fail("unselected provider loaded"))
        with patch("blockwire.controller_cli.entry_points", return_value=[selected, other]):
            self.assertTrue(callable(load_controller("selected").loop))
            with self.assertRaises(ValueError): load_controller("missing")
        with patch("blockwire.controller_cli.entry_points", return_value=[selected, selected]):
            with self.assertRaises(ValueError): load_controller("selected")

    async def test_CR18_health_event_has_no_invented_cause_and_is_isolated(self):
        observed = []
        async def setup(bot):
            bot.on("health_changed", lambda bot, event: event.data.update(current=999))
            bot.on("health_changed", lambda bot, event: observed.append(event.data))
        async def loop(bot):
            native.flat.health = 18.
            await until(lambda: observed)
            self.assertEqual(bot.state.health, 18.)
            bot.stop()
        native = Native()
        result, _, _ = await self.run_script(loop, native=native, setup=setup)
        self.assertEqual(result.status, "stopped", result)
        self.assertEqual(observed, [dict(previous=20., current=18.)])

    async def test_CR20_external_stop_request_cancels_runtime_without_reassertion(self):
        native = Native()
        player = Player(native)
        async def loop(bot):
            await bot.walk_to(4.5, 64., .5, avoid_damage=False)
        runner = asyncio.create_task(Controller(player).run(SimpleNamespace(loop=loop)))
        await until(lambda: native.drive_entered.is_set())
        cancel_control(Player(native))
        result = await asyncio.wait_for(runner, 2.)
        self.assertEqual(result.status, "stopped", result)
        self.assertEqual(native.calls[-1][0], "stop")
        cut = len(native.calls)
        await asyncio.sleep(.1)
        self.assertEqual(len(native.calls), cut)
        self.assertFalse(control_busy(player))

    async def test_CR21_hunger_state_updates_without_running_food_goal(self):
        native = Native()
        async def loop(bot):
            native.hunger = 10
            await until(lambda: bot.state.hunger == 10)
            bot.stop()
        result, _, _ = await self.run_script(loop, native=native)
        self.assertEqual(result.status, "stopped", result)

    async def test_CR22_inflight_hotbar_is_joined_before_cleanup_or_reuse(self):
        native = Native()
        entered, release = threading.Event(), threading.Event()
        def block():
            entered.set()
            release.wait(2)
        native.before_hotbar = block
        player = Player(native)
        async def loop(bot):
            await bot.eat(hotbar_slot=8)
        task = asyncio.create_task(Controller(player).run(SimpleNamespace(loop=loop)))
        await until(entered.is_set)
        task.cancel()
        try:
            await asyncio.sleep(.03)
            self.assertFalse(task.done())
            self.assertTrue(control_busy(player))
        finally:
            release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(native.calls[-1][0], "stop")
        self.assertFalse(control_busy(player))

    async def test_CR23_legacy_owner_blocks_runtime_before_any_observation(self):
        from blockwire.skills import SkillDefinition, SkillParameters, SkillRegistry, SkillResult
        registry = SkillRegistry()
        def waiting(ctx, args):
            while True: ctx.pause(.01)
        registry.register(SkillDefinition("waiting", "owned fixture", SkillParameters, waiting))
        native = Native()
        player = Player(native)
        manager = SkillManager(registry, player)
        job = manager.start("waiting", {})
        try:
            with self.assertRaises(RuntimeError):
                await Controller(Player(native)).run(SimpleNamespace(loop=lambda bot: bot.stop()))
            self.assertEqual(native.calls, [])
        finally:
            manager.cancel(job["id"])
            await until(lambda: manager.status(job["id"])["status"] != "running")
        manager.ensure_idle()

    async def test_CR26_slow_user_loop_does_not_slow_input_state_watchdog(self):
        async def loop(bot):
            for _ in range(5):
                await asyncio.sleep(.12)
                self.assertLess(time.monotonic()-bot.state.sampled_at, .25)
            bot.stop()
        result, _, _ = await self.run_script(loop, hz=2.)
        self.assertEqual(result.status, "stopped", result)

    async def test_CR25_example_help_needs_no_world_or_connection(self):
        from pathlib import Path
        import subprocess
        import sys
        example = Path(__file__).resolve().parents[2] / "examples/controller.py"
        process = await asyncio.to_thread(subprocess.run, [sys.executable, str(example), "--help"],
                                         capture_output=True, text=True, timeout=5)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("--food-slot", process.stdout)

    async def test_CR24_scene_actor_replacement_stops_before_setup(self):
        native = Native()
        native.before_observe = lambda: setattr(native.flat, "session", "actor-b")
        setup_calls = []
        result, _, _ = await self.run_script(lambda bot: bot.stop(), native=native,
            setup=lambda bot: setup_calls.append(True))
        self.assertEqual(result.reason, "actor_session_changed")
        self.assertFalse(setup_calls)
        self.assertFalse(native.effects)

    async def test_CR19_parent_cancels_detached_goal_and_invalid_script_has_no_io(self):
        native = Native()
        detached = []
        async def loop(bot):
            detached.append(asyncio.create_task(bot.walk_to(4.5, 64., .5, avoid_damage=False)))
            await until(lambda: native.drive_entered.is_set())
            bot.stop()
        result, _, bot = await self.run_script(loop, native=native)
        self.assertEqual(result.status, "stopped", result)
        self.assertTrue(detached[0].done())
        self.assertTrue(detached[0].cancelled())
        self.assertFalse(bot._controls)
        calls = len(native.calls)
        with self.assertRaises(ValueError):
            await Controller(Player(native)).run(SimpleNamespace())
        self.assertEqual(len(native.calls), calls)


if __name__ == "__main__":
    unittest.main()
