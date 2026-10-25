"""Run with BLOCKWIRE_TOKEN_FILE set and F8 enabled in your own game."""
from blockwire import Bridge, Player

with Bridge.from_env() as connection:
    player = Player(connection)
    print(player.observe()["text"])
    print(player.inventory()["text"])
    # Explicit bounded script, not an autonomous pathfinder or a fake player:
    player.look(yaw=0, pitch=0)
    print(player.drive(["forward"], ticks=10)["text"])
    player.stop()
