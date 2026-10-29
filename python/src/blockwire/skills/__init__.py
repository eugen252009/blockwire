"""Public extension API for trusted, descriptive player skills."""
from .core import (SkillContext, SkillDefinition, SkillManager, SkillParameters, SkillRegistry,
                   SkillResult, SkillStop, load_selected_plugins, run_skill)
from .walking import WALK_TO, WalkTo
from .autopilot import AUTOPILOT, Autopilot
from .approaching import APPROACH, Approach
from .fighting import FIGHT, Fight, Reactions


def default_registry(*, plugins: bool = False) -> SkillRegistry:
    registry = SkillRegistry()
    registry.register(WALK_TO)
    registry.register(AUTOPILOT)
    registry.register(APPROACH)
    registry.register(FIGHT)
    if plugins:
        load_selected_plugins(registry)
    return registry


__all__ = ["SkillContext", "SkillDefinition", "SkillManager", "SkillParameters", "SkillRegistry",
           "SkillResult", "SkillStop", "load_selected_plugins", "run_skill", "default_registry", "WalkTo", "Autopilot", "Approach", "Fight", "Reactions"]
