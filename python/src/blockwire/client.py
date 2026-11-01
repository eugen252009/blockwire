from __future__ import annotations

import itertools
import json
import math
import os
import ssl
from pathlib import Path
import threading
import time
from typing import Any, Callable, Protocol
from urllib.parse import urlsplit

Json = dict[str, Any]


def _environment(name: str, default: str | None = None) -> str | None:
    """New names win; legacy variables remain an explicit compatibility fallback."""
    value = os.environ.get(name)
    return value if value is not None else os.environ.get(name.replace("BLOCKWIRE_", "BLOCK_BRIDGE_"), default)


class BridgeError(RuntimeError):
    """Rejected operation or unavailable bridge; requests are never automatically retried."""


from .errors import NativeOperationError

class NativeRejected(BridgeError,NativeOperationError):
    """Authenticated native reply ok=false; the transport is still trustworthy."""
    def __init__(self,code):NativeOperationError.__init__(self,code)


class Backend(Protocol):
    """Actor operations. Providers own authorization, game-thread scheduling and actor identity."""

    def call(self, op: str, **arguments: Any) -> Json: ...


class CallableBackend:
    """Direct Python route for trusted entity/script integrations without WebSockets.

    The callable implements the operation contract; this is NOT a Minecraft entity spawner.
    """

    def __init__(self, dispatch: Callable[[Json], Json]):
        self._dispatch = dispatch

    def call(self, op: str, **arguments: Any) -> Json:
        return self._dispatch({"op": op, **arguments})


class Bridge:
    """One persistent, exclusive WebSocket lease controlling one real game client."""

    # Wire identity is intentionally stable across the product rename.
    TLS_NAME = "block-bridge.invalid"

    def __init__(self, token: str, url: str = "wss://127.0.0.1:8765/v1", *,
                 certificate: str | Path | None = None):
        parsed = urlsplit(url)
        if (parsed.scheme != "wss" or not parsed.hostname
                or parsed.path != "/v1" or parsed.username or parsed.password
                or parsed.query or parsed.fragment):
            raise ValueError("Expected wss://HOST:PORT/v1 (TLS required) without credentials, query or fragment")
        if not 32 <= len(token) <= 256 or any(not (c.isascii() and (c.isalnum() or c in "_-")) for c in token):
            raise ValueError("Expected a 32..256 character URL-safe API key")
        self._token, self.url = token, url
        self.certificate = Path(certificate) if certificate is not None else None
        self._socket = None
        self._ids = itertools.count(1)
        self._lock = threading.RLock()

    @classmethod
    def from_token_file(cls, path: str | Path, url: str = "wss://127.0.0.1:8765/v1") -> Bridge:
        path = Path(path)
        if os.name == "posix" and path.stat().st_mode & 0o077:
            raise ValueError("Token permissions must be private (chmod 600)")
        return cls(path.read_text().strip(), url,
                   certificate=_environment("BLOCKWIRE_CERT_FILE", str(path.parent / "tls/certificate.pem")))

    @classmethod
    def from_config(cls, path: str | Path) -> Bridge:
        path = Path(path)
        if os.name == "posix" and path.stat().st_mode & 0o077:
            raise ValueError("Config contains an API key: chmod 600")
        config = json.loads(path.read_text())
        host = config["server_ip"]
        host = {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(host, host)
        if ":" in host:
            host = f"[{host}]"
        url = _environment("BLOCKWIRE_URL", f"wss://{host}:{config['port']}/v1")
        return cls(config["mcp_api_key"], url,
                   certificate=_environment("BLOCKWIRE_CERT_FILE", str(path.parent / "tls/certificate.pem")))

    @classmethod
    def from_env(cls) -> Bridge:
        config = _environment("BLOCKWIRE_CONFIG")
        if config:
            return cls.from_config(config)
        path = _environment("BLOCKWIRE_TOKEN_FILE")
        if not path:
            raise ValueError("Set BLOCKWIRE_CONFIG to settings.json (or legacy BLOCKWIRE_TOKEN_FILE)")
        return cls.from_token_file(path, _environment("BLOCKWIRE_URL", "wss://127.0.0.1:8765/v1"))

    def tls_context(self) -> ssl.SSLContext:
        if self.certificate is None:
            raise BridgeError("A trusted instance certificate is required; use BLOCKWIRE_CONFIG or BLOCKWIRE_CERT_FILE")
        pem = self.certificate.read_text(encoding="ascii")
        if pem.count("-----BEGIN CERTIFICATE-----") != 1 or pem.count("-----END CERTIFICATE-----") != 1:
            raise BridgeError("Expected exactly one trusted instance certificate")
        # Deliberately no system CA roots, CERT_NONE or hostname-verification bypass.
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_verify_locations(cadata=pem)
        return context

    def connect(self) -> Bridge:
        with self._lock:
            if self._socket is None:
                from websockets.sync.client import connect
                self._socket = connect(self.url, additional_headers={"Authorization": f"Bearer {self._token}"},
                                       ssl=self.tls_context(), server_hostname=self.TLS_NAME,
                                       proxy=None, open_timeout=3, close_timeout=1,
                                       max_size=1024 * 1024, ping_interval=10, ping_timeout=10)
        return self

    def call(self, op: str, **arguments: Any) -> Json:
        with self._lock:
            request = {"id": next(self._ids), "op": op, **arguments}
            payload = json.dumps(request, allow_nan=False)
            if len(payload.encode()) > 8192:
                raise ValueError("Request exceeds 8192 bytes")
            try:
                self.connect()
                self._socket.send(payload)
                reply = json.loads(self._socket.recv(timeout=5))
                if reply.get("id") != request["id"]:
                    raise BridgeError("Mismatched response ID")
                if not reply.get("ok"):
                    raise NativeRejected(reply.get("error", "request_failed"))
                return reply["result"]
            except BridgeError:
                raise
            except Exception as exc:
                self.close()
                raise BridgeError("Bridge connection failed; operation outcome may be unknown. Observe before retrying.") from exc

    def close(self) -> None:
        with self._lock:
            if self._socket is not None:
                self._socket.close()
                self._socket = None

    def __enter__(self) -> Bridge:
        return self.connect()

    def __exit__(self, *args: Any) -> None:
        self.close()


class Player:
    """Structured scripting API; the MCP facade uses this exact same actor contract."""

    def __init__(self, backend: Backend):
        self.backend = backend

    def observe(self) -> Json:
        """Client-known scene, including partial 64-block sight/interactables and compact sampled surfaces.

        visible_blocks uses palette_x_runs_v1: each run is [type_index, dx, dy, dz, x_length]
        relative to origin. Omitted cells are unknown, not air. This never extends action reach.
        """
        return self.backend.call("observe")

    def inventory(self) -> Json:
        return self.backend.call("inventory")

    def navigation(self, *, terrain: bool = False) -> Json:
        return self.backend.call("navigation", **({"terrain": True} if terrain else {}))

    def motion_trace(self, *, limit: int = 4096, reset: bool = False,
                     actor_session: str | None = None) -> Json:
        """Read bounded end-of-client-tick native motion samples; reset clears telemetry only."""
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 4096:
            raise ValueError("limit must be an integer in 1..4096")
        args: Json = {"limit": limit}
        if reset: args["reset"] = True
        if actor_session is not None: args["actor_session"] = actor_session
        return self.backend.call("motion_trace", **args)

    def look(self, yaw: float, pitch: float, *, actor_session: str | None = None,
             duration_ms: int | None = None, rotation_profile: str | None = None) -> Json:
        """Set legacy orientation immediately, or schedule one native time-based rotation."""
        if duration_ms is not None:
            if isinstance(duration_ms, bool) or not isinstance(duration_ms, int) or not 1 <= duration_ms <= 5000:
                raise ValueError("duration_ms must be an integer in 1..5000")
        if rotation_profile is not None:
            if duration_ms is None:
                raise ValueError("rotation_profile requires duration_ms")
            if rotation_profile not in {"linear", "smoothstep"}:
                raise ValueError("rotation_profile must be linear or smoothstep")
        args: Json = {"yaw": yaw, "pitch": pitch}
        if actor_session is not None: args["actor_session"] = actor_session
        if duration_ms is not None: args["duration_ms"] = duration_ms
        if rotation_profile is not None: args["rotation_profile"] = rotation_profile
        return self.backend.call("look", **args)

    def look_at(self, x: float, y: float, z: float) -> Json:
        if not all(math.isfinite(n) for n in (x, y, z)):
            raise ValueError("Coordinates must be finite")
        scene = self.observe()
        if not scene.get("in_world"):
            raise BridgeError("not_in_world")
        eye = scene["eye_position"]
        dx, dy, dz = x - eye[0], y - eye[1], z - eye[2]
        if dx == dy == dz == 0:
            raise ValueError("Target coincides with eyes")
        return self.look(math.degrees(math.atan2(-dx, dz)),
                         -math.degrees(math.atan2(dy, math.hypot(dx, dz))))

    def drive(self, buttons: list[str], ticks: int = 10, *, wait: bool = True,
              actor_session: str | None = None, button_ticks: dict[str, int] | None = None) -> Json:
        if isinstance(ticks, bool) or not isinstance(ticks, int) or not 1 <= ticks <= 100:
            raise ValueError("ticks must be an integer in 1..100")
        arguments: Json = {"buttons": buttons, "ticks": ticks}
        if button_ticks is not None:
            arguments["button_ticks"] = button_ticks
        if actor_session is not None:
            arguments["actor_session"] = actor_session
        receipt = self.backend.call("drive", **arguments)
        if not wait:
            return receipt
        time.sleep(ticks * 0.05 + 0.1)
        scene = self.observe()
        scene["receipt"] = receipt
        return scene

    def walk_to(self, x: float, y: float, z: float, sneak: bool = False, avoid_damage: bool = True,
                *, timeout_seconds: float = 30) -> Json:
        from .skills import default_registry, run_skill
        return run_skill(default_registry(), self, "walk_to", dict(x=x,y=y,z=z,sneak=sneak,
            avoid_damage=avoid_damage,timeout_seconds=timeout_seconds)).model_dump(mode="json")

    def craft_item(self, item: str, batches: int = 1, *, timeout_seconds: float = 30) -> Json:
        from .skills import default_registry, run_skill
        return run_skill(default_registry(), self, "craft_item", dict(item=item, batches=batches,
            timeout_seconds=timeout_seconds)).model_dump(mode="json")

    def equip_item(self, item: str, *, timeout_seconds: float = 30) -> Json:
        from .skills import default_registry, run_skill
        return run_skill(default_registry(), self, "equip_item", dict(item=item,
            timeout_seconds=timeout_seconds)).model_dump(mode="json")

    def estimate_distance(self, target: str = "minecraft:dirt", *, position: list[int] | None = None,
                          timeout_seconds: float = 30) -> Json:
        """Measure a current observed block only; no hidden coordinate query or controls."""
        from .skills import default_registry, run_skill
        return run_skill(default_registry(), self, "estimate_distance", dict(target=target, position=position,
            timeout_seconds=timeout_seconds)).model_dump(mode="json")

    def gather_wood(self, count: int = 1, *, scan: bool = True, timeout_seconds: float = 30) -> Json:
        """Gather additional observed vanilla logs locally; success requires inventory gain."""
        from .skills import default_registry, run_skill
        return run_skill(default_registry(), self, "gather_wood", dict(count=count, scan=scan,
            timeout_seconds=timeout_seconds)).model_dump(mode="json")

    def approach(self, target: str = "minecraft:chest", *, position: list[int] | None = None,
                 sneak: bool = False, avoid_damage: bool = True, timeout_seconds: float = 30) -> Json:
        """Approach an initially visible interactable and confirm native reach; never open or use it."""
        from .skills import default_registry, run_skill
        return run_skill(default_registry(), self, "approach", dict(target=target, position=position,
            sneak=sneak, avoid_damage=avoid_damage, timeout_seconds=timeout_seconds)).model_dump(mode="json")

    def autopilot(self, *, destination: Json | None = None, movement: str = "walk",
                  combat: str = "off", evade_creepers: bool = False,
                  duration_seconds: float = 20, timeout_seconds: float = 30) -> Json:
        """Explicit, synchronous bounded activation; MCP uses the same skill as a background job."""
        from .skills import default_registry, run_skill
        return run_skill(default_registry(), self, "autopilot", dict(destination=destination,
            movement=movement, combat=combat, evade_creepers=evade_creepers,
            duration_seconds=duration_seconds, timeout_seconds=timeout_seconds)).model_dump(mode="json")

    def fight(self, *, reactions: Json | None = None, duration_seconds: float = 20,
              min_health: float = 8, radius: float = 8, pursue: bool = True,
              allow_unarmed: bool = False, timeout_seconds: float = 30,
              melee_wait_seconds: float = 3) -> Json:
        """Bounded per-mob combat using native guarded attacks; never a kill guarantee."""
        from .skills import default_registry, run_skill
        parameters = dict(duration_seconds=duration_seconds, min_health=min_health, radius=radius,
                          pursue=pursue, allow_unarmed=allow_unarmed, timeout_seconds=timeout_seconds,
                          melee_wait_seconds=melee_wait_seconds)
        if reactions is not None:
            parameters["reactions"] = reactions
        return run_skill(default_registry(), self, "fight", parameters).model_dump(mode="json")

    def action(self, name: str, *, actor_session: str | None = None,
               target_entity_id: int | None = None) -> Json:
        arguments: Json = {"name": name}
        if actor_session is not None:
            arguments["actor_session"] = actor_session
        if target_entity_id is not None:
            arguments["target_entity_id"] = target_entity_id
        return self.backend.call("action", **arguments)

    def hotbar(self, slot: int, *, actor_session: str | None = None) -> Json:
        arguments: Json = {"slot": slot}
        if actor_session is not None:
            arguments["actor_session"] = actor_session
        return self.backend.call("hotbar", **arguments)

    def open_inventory(self, *, actor_session: str | None = None) -> Json:
        return self.backend.call("open_inventory", **({"actor_session": actor_session} if actor_session is not None else {}))

    def close_screen(self, *, actor_session: str | None = None) -> Json:
        return self.backend.call("close_screen", **({"actor_session": actor_session} if actor_session is not None else {}))

    def click_slot(self, slot: int, button: int = 0, mode: str = "pickup", *,
                   menu_id: int, state_id: int, actor_session: str | None = None) -> Json:
        return self.backend.call("click_slot", slot=slot, button=button, mode=mode,
                                 menu_id=menu_id, state_id=state_id,
                                 **({"actor_session": actor_session} if actor_session is not None else {}))

    def menu(self) -> Json:
        return self.backend.call("menu")

    def open_pause(self) -> Json:
        return self.backend.call("open_pause")

    def click_widget(self, screen_id: int, widget_id: int, button: int = 0) -> Json:
        return self.backend.call("menu_click", screen_id=screen_id, widget_id=widget_id, button=button)

    def click_menu_at(self, screen_id: int, x: float, y: float, button: int = 0) -> Json:
        return self.backend.call("menu_click", screen_id=screen_id, x=x, y=y, button=button)

    def menu_key(self, screen_id: int, key: str, modifiers: list[str] | None = None) -> Json:
        return self.backend.call("menu_key", screen_id=screen_id, key=key, modifiers=modifiers or [])

    def menu_text(self, screen_id: int, text: str, replace: bool = False) -> Json:
        return self.backend.call("menu_text", screen_id=screen_id, text=text, replace=replace)

    def menu_scroll(self, screen_id: int, x: float, y: float, amount: float) -> Json:
        return self.backend.call("menu_scroll", screen_id=screen_id, x=x, y=y, amount=amount)

    def stop(self) -> Json:
        return self.backend.call("stop")

    def command(self, command: str, *, actor_session: str | None = None) -> Json:
        """Submit one explicit slash command with native permissions, not a success result.

        May irreversibly change the world. Output is not captured; never blindly retry.
        """
        if (not isinstance(command, str) or not command.startswith("/") or len(command) < 2
                or command[1] == "/" or command[1].isspace()
                or any(ord(c) < 32 or 127 <= ord(c) <= 159 or c in "§\u2028\u2029"
                       or 0xD800 <= ord(c) <= 0xDFFF for c in command)
                or len(command.encode("utf-16-le")) // 2 > 256):
            raise ValueError("expected one slash command, max 256 UTF-16 code units, no control characters")
        arguments: Json = {"command": command}
        if actor_session is not None:
            arguments["actor_session"] = actor_session
        return self.backend.call("command", **arguments)

    def respawn(self, *, actor_session: str | None = None) -> Json:
        arguments = {} if actor_session is None else {"actor_session": actor_session}
        return self.backend.call("respawn", **arguments)
