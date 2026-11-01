"""Independent closed-fixture audit; never supplied to a planning model."""
import gzip
from pathlib import Path
from .anvil import NBT,voxels,inflate
from .reference import House,AIR
from .snapshots import validate


def fixture_audit(snapshot):
    root=Path(snapshot);manifest=validate(root)
    def nbt(relative):return NBT(inflate((root/relative).read_bytes(),1)).root()
    level=nbt('level.dat')['Data']
    generator=nbt('data/minecraft/world_gen_settings.dat')['data']
    rules=nbt('data/minecraft/game_rules.dat')['data']
    weather=nbt('data/minecraft/weather.dat')['data']
    clocks=nbt('data/minecraft/world_clocks.dat')['data']
    h=House();actual=voxels(root,h.workspace()|h.floors())
    checks={'minecraft_version':level['Version']['Name']=='26.3',
            'survival':level['GameType']==0,
            'peaceful':level['difficulty_settings']['difficulty']=='peaceful',
            'seed':generator['seed']==31052026,
            'flat':generator['dimensions']['minecraft:overworld']['generator']['type']=='minecraft:flat',
            'no_generated_structures':generator['generate_structures']==0,
            'no_bonus_chest':generator['bonus_chest']==0,
            'time_frozen':rules['minecraft:advance_time']==0,
            'weather_frozen':rules['minecraft:advance_weather']==0,
            'mob_spawning_disabled':rules['minecraft:spawn_mobs']==0,
            'wandering_traders_disabled':rules['minecraft:spawn_wandering_traders']==0,
            'random_ticks_disabled':rules['minecraft:random_tick_speed']==0,
            'noon':clocks['minecraft:overworld']['total_ticks']==6000,
            'dry':weather['raining']==0 and weather['thundering']==0,
            'no_persisted_nonplayer_entities':not any((root/'dimensions/minecraft/overworld/entities').glob('*.mca')) and not any((root/'entities').glob('*.mca')),
            'empty_site':all(actual.get(p) in AIR for p in h.workspace()),
            'intact_grass_floor':all(actual.get(p)=='minecraft:grass_block' for p in h.floors())}
    if not all(checks.values()):raise ValueError('Fixture audit failed: '+str(checks))
    return {'snapshot_identity':manifest['identity'],'checks':checks,'data_version':level['DataVersion'],
            'verification_source':'read-only CLOSED dedicated benchmark snapshot, not an agent API'}
