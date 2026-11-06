"""Descriptive crafting affordances for reporting. No clicks or recipe selection."""
from .recipes import RECIPES, Recipe, SPECIES, PLANKS

BUILDING_RECIPES=[Recipe('minecraft:chest',1,(('#planks',)*3,('#planks','','#planks'),('#planks',)*3))]
for species in SPECIES:
    plank='minecraft:'+species+'_planks'
    BUILDING_RECIPES.extend([
        Recipe('minecraft:'+species+'_door',3,((plank,plank),)*3),
        Recipe('minecraft:'+species+'_slab',6,((plank,)*3,)),
        Recipe('minecraft:'+species+'_stairs',4,((plank,'',''),(plank,plank,''),(plank,)*3)),
    ])

def crafting_report(inventory):
    menu=inventory.get('menu_type');width={'InventoryMenu':2,'CraftingMenu':3}.get(menu)
    slots={s['slot']:s for s in inventory.get('slots',[])}
    return {'actor_session':inventory.get('actor_session'),'player_uuid':inventory.get('player_uuid'),
        'menu_id':inventory.get('menu_id'),'state_id':inventory.get('state_id'),
        'container_open':inventory.get('container_open'),'supported_grid':width is not None,
        'grid_width':width,'grid_slots':list(range(1,width*width+1)) if width else [],
        'result':slots.get(0) if width else None,'carried':inventory.get('carried'),
        'recipes':[{k:v for k,v in r.describe().items() if k!='choices'} for r in [*RECIPES.values(),*BUILDING_RECIPES]],
        'ingredient_choices':{'#planks':PLANKS},
        'recipe_source':'host_vanilla_reference_not_native_recipe_registry',
        'recipe_catalog_complete':False,'native_result_is_authoritative':True,
        'instructions':'Choose a recipe yourself. Fill explicit slots using native clicks. Observe the result, output and material consumption. No item spawning or recipe execution occurs in reporting.'}
