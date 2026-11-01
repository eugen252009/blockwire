"""Explicit operator-only benchmark fixture creation through native menus/commands.

Administrative commands are NEVER called by either building test.
"""
import json
from pathlib import Path
import time
from .snapshots import OWNER,FIXTURE,capture

NAME='Blockwire Benchmark Superflat'
SEED=31052026
INVENTORY={'minecraft:cobblestone':128,'minecraft:dirt':32,'minecraft:diamond_pickaxe':1,'minecraft:diamond_shovel':1}
START=[2.5,-60.,-3.5]
COMMANDS=['/gamerule minecraft:advance_time false','/gamerule minecraft:advance_weather false',
          '/gamerule minecraft:spawn_mobs false','/gamerule minecraft:random_tick_speed 0',
          '/gamerule minecraft:spawn_wandering_traders false','/time set noon','/weather clear',
          '/kill @e[type=!minecraft:player]', '/fill -16 -60 -16 16 -48 16 minecraft:air',
          '/fill -16 -61 -16 16 -61 16 minecraft:grass_block','/clear @s',
          '/tp @s 2.5 -60 -3.5 0 0']
COMMANDS += [f'/give @s {block} {count}' for block,count in INVENTORY.items()]

def title(player):
    if player.menu().get('type')!='TitleScreen':raise ValueError('Closed world / TitleScreen required')

def click(player,label):
    menu=player.menu();rows=[w for w in menu['widgets'] if w['label']==label and w['active']]
    if len(rows)!=1:raise ValueError('Unambiguous active widget required: '+label)
    player.click_widget(menu['screen_id'],rows[0]['widget_id']);time.sleep(.15)

def field(player,label,value):
    menu=player.menu();row=next(w for w in menu['widgets'] if w['label']==label and w['type']!='StringWidget' and w['active'])
    player.click_widget(menu['screen_id'],row['widget_id']);player.menu_text(player.menu()['screen_id'],value,replace=True)

def close(player):
    menu=player.menu()
    if menu.get('type')=='TitleScreen':return
    if not menu.get('screen_open'):player.open_pause()
    click(player,'Save and Quit to Title')
    for _ in range(300):
        if player.menu()['type']=='TitleScreen':return
        time.sleep(.1)
    raise RuntimeError('World did not close')

def load(player,*,audit=lambda value:None):
    title(player);click(player,'Singleplayer')
    menu=player.menu();rows=[w for w in menu['widgets'] if w['label'].split('\n')[0]==NAME and w['active']]
    # Native list labels can include date/version on subsequent lines.
    if len(rows)!=1:rows=[w for w in menu['widgets'] if ('Selected '+NAME+', last played:') in w['label'] and w['active']]
    if len(rows)!=1:raise ValueError('Dedicated world must be uniquely selectable')
    player.click_widget(menu['screen_id'],rows[0]['widget_id'])
    from blockwire.client import BridgeError,NativeRejected
    uncertain=False
    try:click(player,'Play Selected World')
    except NativeRejected:raise
    except BridgeError:
        # Loading may block the native GUI callback longer than its bounded
        # receipt wait. NEVER repeat the click. Explicit fresh read-only state
        # acquisition is the only permitted continuation of this fixture step.
        uncertain=True;audit({'phase':'fixture_load','receipt':'uncertain','action_replayed':False,'follow_up':'fresh_read_only_native_state'})
    end=time.monotonic()+60.
    while time.monotonic()<end:
        try:
            scene=player.observe()
            if scene.get('alive') and scene.get('on_ground') and not player.menu().get('screen_open'):
                if uncertain:audit({'phase':'fixture_load','receipt':'uncertain','action_replayed':False,'follow_up':'fresh_native_actor_observed','actor_session':scene['actor_session']})
                return scene
        except BridgeError:
            if not uncertain:raise
        time.sleep(.1)
    raise RuntimeError('Fixture did not become ready')

def create(player,saves,private):
    world=Path(saves)/NAME;private=Path(private)
    if world.exists():raise ValueError('Dedicated world already exists; never overwrite during creation')
    private.mkdir(parents=True,exist_ok=False)
    title(player);click(player,'Singleplayer');click(player,'Create New World');click(player,'Game')
    field(player,'World Name',NAME)
    for _ in range(4):
        menu=player.menu();row=next(w for w in menu['widgets'] if w['label'].startswith('Difficulty:'))
        if row['label']=='Difficulty: Peaceful':break
        click(player,row['label'])
    click(player,'Allow Commands: OFF');click(player,'World');click(player,'World Type: Default')
    assert any(w['label']=='World Type: Superflat' for w in player.menu()['widgets'])
    field(player,'Seed for the world generator',str(SEED))
    # Disable structures in the native UI, not by editing the generated save.
    menu=player.menu()
    (private/'world-menu.json').write_text(json.dumps(menu,indent=2)+'\n')
    # The first world-tab ON/OFF cycle is Generate Structures; captured labels
    # and settings are retained, the local area is additionally cleared below.
    toggles=[w for w in menu['widgets'] if w['type']=='CycleButton' and w['label']=='ON']
    for w in toggles:player.click_widget(menu['screen_id'],w['widget_id']);menu=player.menu()
    click(player,'Game');menu=player.menu()
    labels=[w['label'] for w in menu['widgets']]
    assert all(v in labels for v in ('Game Mode: Survival','Difficulty: Peaceful','Allow Commands: ON'))
    (private/'creation-menu.json').write_text(json.dumps(menu,indent=2)+'\n');click(player,'Create New World')
    for _ in range(300):
        scene=player.observe()
        if scene.get('alive') and scene.get('on_ground'):break
        time.sleep(.2)
    else:raise RuntimeError('Creation timeout')
    for command in COMMANDS:player.command(command);time.sleep(.15)
    return seal(player,saves,private)

def seal(player,saves,private):
    """Seal only the administratively created dedicated fixture, after setup."""
    world=Path(saves)/NAME;private=Path(private)
    time.sleep(.5)
    scene=player.observe();inv=player.inventory()
    from blockwire.recipes import item_counts
    assert item_counts(inv)==INVENTORY,(item_counts(inv),INVENTORY)
    assert max(abs(a-b) for a,b in zip(scene['position'],START))<.05
    close(player)
    (world/OWNER).write_text(json.dumps({'fixture':FIXTURE})+'\n')
    manifest=capture(world,private/'baseline',lambda:title(player))
    metadata={'fixture':FIXTURE,'world':NAME,'minecraft_version':'26.3','seed':SEED,
              'mode':'Survival','difficulty':'Peaceful','superflat':True,'start':START,
              'inventory':INVENTORY,'administrative_fixture_commands':COMMANDS,
              'construction_commands_permitted':False,'snapshot_identity':manifest['identity'],
              'initial_scene':scene,'initial_inventory':inv}
    (private/'fixture.json').write_text(json.dumps(metadata,indent=2)+'\n')
    return metadata
