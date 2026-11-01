"""Explicit native-UI creation of the dedicated deterministic motion fixture."""
import json,time
from pathlib import Path
from .snapshots import OWNER,FIXTURE,NAME,DIRECTORY,capture

SEED=31052027
START=[.5,64.,.5]

def fixture_commands():
    commands=['/gamerule minecraft:advance_time false','/gamerule minecraft:advance_weather false',
      '/gamerule minecraft:spawn_mobs false','/gamerule minecraft:random_tick_speed 0',
      '/gamerule minecraft:spawn_wandering_traders false','/gamerule minecraft:keep_inventory true',
      '/time set noon','/weather clear','/kill @e[type=!minecraft:player]','/clear @s','/effect clear @s',
      '/fill -82 64 -62 82 82 66 minecraft:air','/fill -80 63 -60 80 63 30 minecraft:smooth_stone',
      '/fill -60 59 34 70 82 64 minecraft:air','/fill -60 58 34 70 58 64 minecraft:smooth_stone']
    # Raised steps/stairs; every support is an actual full block.
    commands += ['/fill -43 63 39 -40 63 42 minecraft:smooth_stone','/fill -39 64 39 -34 64 42 minecraft:smooth_stone',
      '/fill -27 63 37 -24 63 39 minecraft:smooth_stone','/fill -27 64 40 -24 64 45 minecraft:smooth_stone',
      '/fill -18 63 39 -16 63 42 minecraft:smooth_stone','/fill -15 64 39 -15 64 42 minecraft:smooth_stone',
      '/fill -14 65 39 -14 65 42 minecraft:smooth_stone','/fill -13 66 39 -10 66 42 minecraft:smooth_stone',
      '/fill -4 63 37 -1 63 39 minecraft:smooth_stone','/fill -4 64 40 -1 64 40 minecraft:smooth_stone',
      '/fill -4 65 41 -1 65 41 minecraft:smooth_stone','/fill -4 66 42 -1 66 45 minecraft:smooth_stone',
      '/fill 3 63 38 5 63 40 minecraft:smooth_stone','/setblock 5 64 39 minecraft:smooth_stone',
      '/setblock 5 65 40 minecraft:smooth_stone','/setblock 6 66 40 minecraft:smooth_stone',
      '/setblock 6 66 41 minecraft:smooth_stone','/setblock 7 66 41 minecraft:smooth_stone',
      '/setblock 7 66 42 minecraft:smooth_stone','/setblock 8 66 42 minecraft:smooth_stone',
      '/fill 8 66 43 10 66 45 minecraft:smooth_stone']
    # Parkour platforms over a safety floor.
    commands += ['/fill 10 63 40 12 63 43 minecraft:smooth_stone','/fill 14 63 40 18 63 43 minecraft:smooth_stone',
      '/fill 20 63 40 22 63 43 minecraft:smooth_stone','/fill 24 63 40 25 63 43 minecraft:smooth_stone','/fill 27 63 40 30 63 43 minecraft:smooth_stone',
      '/fill 40 63 40 42 63 42 minecraft:smooth_stone','/fill 44 63 44 47 63 47 minecraft:smooth_stone',
      '/fill 10 63 51 13 63 54 minecraft:smooth_stone','/fill 15 63 51 18 63 55 minecraft:smooth_stone',
      '/fill 19 64 53 22 64 57 minecraft:smooth_stone','/fill 23 64 55 26 64 59 minecraft:smooth_stone',
      '/fill 27 65 57 31 65 62 minecraft:smooth_stone']
    # Fixed collision corridors for single-goal turns/S-curves.
    commands += ['/fill 20 64 5 26 66 11 minecraft:stone','/fill 21 64 6 25 66 6 minecraft:air','/fill 25 64 6 25 66 10 minecraft:air',
      '/fill 20 64 15 26 66 21 minecraft:stone','/fill 21 64 20 25 66 20 minecraft:air','/fill 25 64 16 25 66 20 minecraft:air',
      '/fill 30 64 5 39 66 15 minecraft:stone','/fill 31 64 6 34 66 6 minecraft:air','/fill 34 64 6 34 66 10 minecraft:air',
      '/fill 34 64 10 38 66 10 minecraft:air','/fill 38 64 10 38 66 14 minecraft:air',
      '/fill 42 64 5 51 66 15 minecraft:stone','/fill 43 64 6 46 66 6 minecraft:air','/fill 46 64 6 46 66 10 minecraft:air',
      '/fill 46 64 10 49 66 10 minecraft:air','/fill 49 64 10 49 66 14 minecraft:air','/fill 49 64 14 50 66 14 minecraft:air']
    # B01-shaped roof/stair. The partial-support start is z=46.007832 at feet Y=66.
    commands += ['/fill 50 66 40 54 66 44 minecraft:cobblestone','/fill 49 63 39 55 63 49 minecraft:smooth_stone',
      '/setblock 52 63 48 minecraft:dirt','/setblock 52 63 47 minecraft:dirt','/setblock 52 64 47 minecraft:dirt',
      '/setblock 52 63 46 minecraft:dirt','/setblock 52 64 46 minecraft:dirt','/setblock 52 65 45 minecraft:dirt',
      '/tp @s 0.5 64 0.5 0 0']
    return commands

COMMANDS=fixture_commands()

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
    title(player);click(player,'Singleplayer');menu=player.menu()
    rows=[w for w in menu['widgets'] if w['label'].split('\n')[0]==NAME and w['active']]
    if len(rows)!=1:rows=[w for w in menu['widgets'] if NAME in w['label'] and 'last played:' in w['label'] and w['active']]
    if len(rows)!=1:raise ValueError('Dedicated movement world must be uniquely selectable')
    player.click_widget(menu['screen_id'],rows[0]['widget_id'])
    from blockwire.client import BridgeError,NativeRejected
    uncertain=False
    try:click(player,'Play Selected World')
    except NativeRejected:raise
    except BridgeError:
        uncertain=True;audit({'phase':'fixture_load','receipt':'uncertain','action_replayed':False})
    end=time.monotonic()+60
    while time.monotonic()<end:
        try:
            scene=player.observe()
            if scene.get('alive') and scene.get('on_ground') and not player.menu().get('screen_open'):
                if uncertain:audit({'phase':'fixture_load','receipt':'uncertain','action_replayed':False,'actor_session':scene['actor_session']})
                return scene
        except BridgeError:
            if not uncertain:raise
        time.sleep(.1)
    raise RuntimeError('Movement fixture did not become ready')

def create(player,saves,private):
    world=Path(saves)/DIRECTORY;private=Path(private)
    if world.exists():raise ValueError('Dedicated movement world already exists; never overwrite')
    private.mkdir(parents=True,exist_ok=True)
    if (private/'baseline').exists() or (private/'fixture.json').exists():raise ValueError('Movement fixture metadata already exists')
    title(player);click(player,'Singleplayer');click(player,'Create New World');click(player,'Game')
    field(player,'World Name',NAME)
    for _ in range(4):
        row=next(w for w in player.menu()['widgets'] if w['label'].startswith('Difficulty:'))
        if row['label']=='Difficulty: Peaceful':break
        click(player,row['label'])
    click(player,'Allow Commands: OFF');click(player,'World');click(player,'World Type: Default')
    assert any(w['label']=='World Type: Superflat' for w in player.menu()['widgets'])
    field(player,'Seed for the world generator',str(SEED))
    menu=player.menu();(private/'world-menu.json').write_text(json.dumps(menu,indent=2)+'\n')
    for row in [w for w in menu['widgets'] if w['type']=='CycleButton' and w['label']=='ON']:
        player.click_widget(menu['screen_id'],row['widget_id']);menu=player.menu()
    click(player,'Game');click(player,'Create New World')
    for _ in range(300):
        scene=player.observe()
        if scene.get('alive') and scene.get('on_ground'):break
        time.sleep(.2)
    else:raise RuntimeError('Creation timeout')
    for command in COMMANDS:player.command(command);time.sleep(.12)
    time.sleep(1);scene=player.observe();assert max(abs(a-b) for a,b in zip(scene['position'],START))<.05
    close(player);(world/OWNER).write_text(json.dumps({'fixture':FIXTURE})+'\n')
    manifest=capture(world,private/'baseline',lambda:title(player))
    metadata={'fixture':FIXTURE,'world':NAME,'minecraft_version':'26.3','seed':SEED,'mode':'Survival','difficulty':'Peaceful',
      'superflat':True,'start':START,'administrative_fixture_commands':COMMANDS,'snapshot_identity':manifest['identity'],'initial_scene':scene}
    (private/'fixture.json').write_text(json.dumps(metadata,indent=2)+'\n');return metadata
