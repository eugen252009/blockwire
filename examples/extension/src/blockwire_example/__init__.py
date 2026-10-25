"""An opt-in trusted provider. Importing it does not open sockets or mutate Minecraft."""
from blockwire.skills import SkillDefinition, SkillParameters, SkillResult


class InventoryGoal(SkillParameters):
    pass


def summarize_inventory(context, goal):
    context.check()
    inventory = context.player.inventory()
    context.check()
    return SkillResult(status="succeeded", reason="inventory_observed",
                       text=inventory["text"], details={"items": inventory["items"]})


def register(registry):
    registry.register(SkillDefinition("inventory_summary",
        "Read the current inventory and summarize its item stacks without opening a screen.",
        InventoryGoal, summarize_inventory, controls_player=False))
