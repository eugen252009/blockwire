"""Small explicit vanilla recipe catalogue, NOT a progression planner.

Minecraft's native result slot remains authoritative. Unknown/modded recipes
are unsupported; this data supplies dependencies/choices to the LLM.
"""
from dataclasses import dataclass

SPECIES = ('oak', 'spruce', 'birch', 'jungle', 'acacia', 'dark_oak', 'mangrove', 'cherry', 'pale_oak')
PLANKS = tuple('minecraft:'+s+'_planks' for s in SPECIES)


@dataclass(frozen=True)
class Recipe:
    output: str
    count: int
    rows: tuple[tuple[str, ...], ...]

    @property
    def width(self): return max(map(len, self.rows))
    @property
    def height(self): return len(self.rows)

    def describe(self):
        return {'output': self.output, 'output_count': self.count, 'pattern': self.rows,
                'choices': {'#planks': PLANKS},
                'station': 'crafting_table' if self.width > 2 or self.height > 2 else 'inventory_or_crafting_table'}


RECIPES = {r.output: r for r in [
    *[Recipe('minecraft:'+s+'_planks', 4, (('minecraft:'+s+'_log',),)) for s in SPECIES],
    Recipe('minecraft:stick', 4, (('#planks',), ('#planks',))),
    Recipe('minecraft:crafting_table', 1, (('#planks', '#planks'), ('#planks', '#planks'))),
    Recipe('minecraft:wooden_pickaxe', 1, (('#planks', '#planks', '#planks'), ('', 'minecraft:stick', ''), ('', 'minecraft:stick', ''))),
    Recipe('minecraft:wooden_axe', 1, (('#planks', '#planks'), ('#planks', 'minecraft:stick'), ('', 'minecraft:stick'))),
    Recipe('minecraft:wooden_hoe', 1, (('#planks', '#planks'), ('', 'minecraft:stick'), ('', 'minecraft:stick'))),
    Recipe('minecraft:stone_pickaxe', 1, (('minecraft:cobblestone',)*3, ('', 'minecraft:stick', ''), ('', 'minecraft:stick', ''))),
    Recipe('minecraft:stone_shovel', 1, (('minecraft:cobblestone',), ('minecraft:stick',), ('minecraft:stick',))),
    Recipe('minecraft:stone_sword', 1, (('minecraft:cobblestone',), ('minecraft:cobblestone',), ('minecraft:stick',))),
    Recipe('minecraft:stone_axe', 1, (('minecraft:cobblestone',)*2, ('minecraft:cobblestone', 'minecraft:stick'), ('', 'minecraft:stick'))),
    Recipe('minecraft:stone_hoe', 1, (('minecraft:cobblestone',)*2, ('', 'minecraft:stick'), ('', 'minecraft:stick'))),
    Recipe('minecraft:furnace', 1, (('minecraft:cobblestone',)*3, ('minecraft:cobblestone', '', 'minecraft:cobblestone'), ('minecraft:cobblestone',)*3)),
    Recipe('minecraft:bread', 1, (('minecraft:wheat',)*3,)),
]}


def item_counts(inventory):
    result = {}
    for row in inventory.get('items', []):
        if not row.get('empty', False):
            result[row['item']] = result.get(row['item'], 0)+row['count']
    return result


def ingredients(recipe, available):
    """Resolve legal ingredient alternatives only; never choose a strategic goal."""
    remaining, plan, missing = dict(available), [], []
    for y, row in enumerate(recipe.rows):
        for x, token in enumerate(row):
            if not token: continue
            options = PLANKS if token == '#planks' else (token,)
            chosen = next((i for i in options if remaining.get(i, 0) > 0), None)
            if chosen is None:
                missing.append({'ingredient': token, 'alternatives': list(options), 'count': 1})
            else:
                remaining[chosen] -= 1
                plan.append((x, y, chosen))
    return plan, missing
