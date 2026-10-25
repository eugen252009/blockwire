"""Uses a verified TLS instance connection. No teleportation or item seeding."""
from blockwire import Bridge, Player

with Bridge.from_env() as connection:
    player = Player(connection)
    state = player.navigation()
    if not state.get("ready"):
        raise SystemExit(state.get("reason", "navigation unavailable"))
    x, y, z = state["position"]
    result = player.walk_to(x + 3, y, z, sneak=False, avoid_damage=True)
    print(result)  # Check status; a submitted input is not arrival.
