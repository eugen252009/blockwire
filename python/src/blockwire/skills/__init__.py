"""Public extension API for trusted, descriptive player skills."""
from .core import (SkillContext, SkillDefinition, SkillManager, SkillParameters, SkillRegistry,
                   SkillResult, SkillStop, load_selected_plugins, run_skill)
from .walking import WALK_TO, WalkTo
from .autopilot import AUTOPILOT, Autopilot
from .approaching import APPROACH, Approach
from .fighting import FIGHT, Fight, Reactions
from .woodcutting import GATHER_WOOD, GatherWood
from .distance import ESTIMATE_DISTANCE, EstimateDistance
from .crafting import CRAFT_ITEM, CraftItem
from .item_actions import EQUIP_ITEM, INTERACT_BLOCK, PLACE_BLOCK, PLACE_AT
from .mining import GATHER_BLOCK
from .removing import REMOVE_BLOCK
from .eating import CONSUME_ITEM
from .searching import SEARCH_BLOCKS
from .excavating import DIG_STEP
from .viewing import AIM_AT


def default_registry(*, plugins: bool = False) -> SkillRegistry:
    registry = SkillRegistry()
    registry.register(WALK_TO)
    registry.register(AUTOPILOT)
    registry.register(APPROACH)
    registry.register(FIGHT)
    registry.register(GATHER_WOOD)
    registry.register(ESTIMATE_DISTANCE)
    for definition in (CRAFT_ITEM, EQUIP_ITEM, INTERACT_BLOCK, PLACE_BLOCK, PLACE_AT, GATHER_BLOCK, REMOVE_BLOCK, CONSUME_ITEM, SEARCH_BLOCKS, DIG_STEP, AIM_AT):
        registry.register(definition)
    if plugins:
        load_selected_plugins(registry)
    return registry


__all__ = ["SkillContext", "SkillDefinition", "SkillManager", "SkillParameters", "SkillRegistry",
           "SkillResult", "SkillStop", "load_selected_plugins", "run_skill", "default_registry", "WalkTo", "Autopilot", "Approach", "Fight", "Reactions", "GatherWood", "EstimateDistance", "CraftItem"]
