"""Finite supported vanilla mechanics, not goals or progression policy.

Native crafting/mining/drop observations remain authoritative. Modded rules are
not inferred from this catalogue. A hoe is a soil tool, never a mining pickaxe.
"""
from .recipes import RECIPES

MATERIALS = ('wooden', 'stone', 'iron', 'golden', 'diamond', 'netherite')
PICKS = frozenset('minecraft:'+m+'_pickaxe' for m in MATERIALS)
DROPS = {'minecraft:stone':'minecraft:cobblestone','minecraft:cobblestone':'minecraft:cobblestone',
         'minecraft:dirt':'minecraft:dirt','minecraft:grass_block':'minecraft:dirt','minecraft:crafting_table':'minecraft:crafting_table','minecraft:coal_ore':'minecraft:coal'}
MINING = {block:{'block':block,'blocks':[block],'drop':drop,'required_tool_class':None if block in {'minecraft:dirt','minecraft:grass_block','minecraft:crafting_table'} else 'pickaxe',
                 'accepted_held_items':[] if block in {'minecraft:dirt','minecraft:grass_block','minecraft:crafting_table'} else sorted(PICKS),
                 'silk_touch_supported':False,'observation':'currently exposed; native reach and supported standing cell required'}
          for block,drop in DROPS.items()}
MINING['ground_soil'] = {**MINING['minecraft:dirt'], 'block':'ground_soil', 'blocks':['minecraft:dirt','minecraft:grass_block']}
TOOLS = {f'minecraft:{m}_{kind}':{'class':kind,'material':m,'purpose':purpose}
         for m in MATERIALS for kind,purpose in [('pickaxe','mining stone and supported ores'),
                                                ('axe','wood cutting'),('hoe','tilling soil; NOT a pickaxe')]}


def describe_mechanics():
    return {'scope':'supported vanilla subset, not modpack/server rule discovery',
            'tools':TOOLS,'mining':MINING,
            'craftable_tools':{item:TOOLS[item] for item in RECIPES if item in TOOLS},
            'stations':{'minecraft:crafting_table':{'grid':[3,3],'portable':True,'recovery_skill':'gather_block',
                         'recovery_block':'minecraft:crafting_table','recovery_requires_closed_clean_gui':True,
                         'recovery_outcome':'Native block mining and the table item actually returned to inventory.'}},
            'failure_semantics':{'no_reachable_exposed_blocks':'Geometry/visibility/access failure, NOT a request to craft a different tool.',
                                 'appropriate_equipped_tool_required':'Equip a tool accepted by this block contract.',
                                 'drops_not_collected':'Breaking/attack receipt did not establish inventory gain.'}}
