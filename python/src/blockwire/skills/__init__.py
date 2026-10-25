"""Public extension API for trusted, descriptive player skills."""
from .core import (SkillContext, SkillDefinition, SkillManager, SkillParameters, SkillRegistry,
                   SkillResult, SkillStop, load_selected_plugins, run_skill)
from .walking import WALK_TO, WalkTo


def default_registry(*, plugins: bool = False) -> SkillRegistry:
    registry = SkillRegistry()
    registry.register(WALK_TO)
    if plugins:
        load_selected_plugins(registry)
    return registry


__all__ = ["SkillContext", "SkillDefinition", "SkillManager", "SkillParameters", "SkillRegistry",
           "SkillResult", "SkillStop", "load_selected_plugins", "run_skill", "default_registry", "WalkTo"]
