"""Versioned hardcoded movement scenarios. Coordinates are feet positions in the owned fixture."""
from dataclasses import dataclass,asdict
from typing import Literal
import hashlib,json,math

Mode=Literal['normal','fast','sneak']

@dataclass(frozen=True)
class MovementScenario:
    name:str
    category:str
    start:tuple[float,float,float]
    target:tuple[float,float,float]
    mode:Mode='normal'
    terrain:bool=False
    baseline_path:tuple[tuple[float,float,float],...]=()
    jump:bool=False
    repeats:int=5
    max_ticks:int=180
    expected:str='reachable'
    arrival_radius:float=.3
    prelude_ticks:int=0
    prelude_yaw:float|None=None
    baseline_stop_waypoints:bool=False
    baseline_acceptance_radius:float=1.0
    description:str=''
    def __post_init__(self):
        values=(*self.start,*self.target)
        if not all(math.isfinite(v) for v in values):raise ValueError('finite coordinates required')
        if self.repeats<1 or not 1<=self.max_ticks<=400:raise ValueError('bounded scenario')
        if self.baseline_path and self.baseline_path[-1]!=self.target:raise ValueError('baseline path must end at target')
    @property
    def path(self):return self.baseline_path or (self.target,)
    def document(self):return asdict(self)


def scenarios():
    rows=[]
    def add(name,category,start,target,**kw):rows.append(MovementScenario(name,category,start,target,**kw))
    # Axis-isolated, all on the same native full-block surface.
    for axis,orth in [('x',-20.5),('z',-20.5)]:
        for sign,label in [(1,'positive'),(-1,'negative')]:
            for distance,size in [(2,'short'),(10,'medium'),(30,'long')]:
                start=(-15.5,64.,orth) if axis=='x' else (orth,64.,-15.5)
                target=(start[0]+sign*distance,64.,start[2]) if axis=='x' else (start[0],64.,start[2]+sign*distance)
                add(f'linear_{axis}_{label}_{size}','linear',start,target,max_ticks=260 if distance==30 else 140)
    # Native diagonal physics versus the same final Blockwire goal.
    for dx,dz,label in [(10,10,'pp'),(-10,10,'np'),(10,-10,'pn'),(-10,-10,'nn')]:
        add('diagonal_xz_'+label,'combined',(.5,64.,.5),(.5+dx,64.,.5+dz),max_ticks=180)
    # Modes use one common lane.
    for mode in ('normal','fast','sneak'):
        add('mode_'+mode+'_straight','modes',(-5.5,64.,-10.5),(9.5,64.,-10.5),mode=mode,max_ticks=260)
        add('mode_'+mode+'_diagonal','modes',(-5.5,64.,-5.5),(4.5,64.,4.5),mode=mode,max_ticks=280)
    # Short stopping tasks deliberately include sub-block targets.
    for distance in (.2,.5,1.,2.):
        add('precision_'+str(distance).replace('.','_'),'precision',(-30.5,64.,-5.5),(-30.5+distance,64.,-5.5),max_ticks=100)
    # Real one-block changes and stairs in the raised fixture area.
    add('step_x_ascend','vertical',(-40.5,64.,40.5),(-38.5,65.,40.5),terrain=True,jump=True,repeats=3)
    add('step_x_descend','vertical',(-37.5,65.,40.5),(-41.5,64.,40.5),terrain=True,repeats=3)
    add('step_z_ascend','vertical',(-25.5,64.,39.5),(-25.5,65.,42.5),terrain=True,jump=True,repeats=3)
    add('step_z_descend','vertical',(-25.5,65.,42.5),(-25.5,64.,39.5),terrain=True,repeats=3)
    add('stairs_x_ascend','vertical',(-16.5,64.,40.5),(-12.5,67.,40.5),terrain=True,jump=True,repeats=3,max_ticks=180)
    add('stairs_x_descend','vertical',(-12.5,67.,40.5),(-16.5,64.,40.5),terrain=True,repeats=3,max_ticks=180)
    add('combined_xy','combined',(-16.5,64.,40.5),(-12.5,67.,40.5),terrain=True,jump=True,repeats=3)
    add('combined_yz','combined',(-2.5,64.,39.5),(-2.5,67.,43.5),terrain=True,jump=True,repeats=3)
    add('combined_xyz','combined',(4.5,64.,39.5),(8.5,67.,43.5),terrain=True,jump=True,repeats=3,max_ticks=220)
    # Single-goal routes through fixed collision corridors; path is only the vanilla input reference.
    add('turn_90_left','turns',(21.5,64.,6.5),(25.5,64.,10.5),baseline_path=((25.5,64.,6.5),(25.5,64.,10.5)),repeats=5)
    add('turn_90_right','turns',(21.5,64.,20.5),(25.5,64.,16.5),baseline_path=((25.5,64.,20.5),(25.5,64.,16.5)),repeats=5)
    add('curve_gentle_45','curves',(10.5,64.,10.5),(18.5,64.,18.5),repeats=5)
    add('curve_s','curves',(31.5,64.,6.5),(38.5,64.,14.5),baseline_path=((34.5,64.,6.5),(34.5,64.,10.5),(38.5,64.,10.5),(38.5,64.,14.5)),repeats=3,max_ticks=220)
    add('curve_zigzag','curves',(43.5,64.,6.5),(50.5,64.,14.5),baseline_path=((46.5,64.,6.5),(46.5,64.,10.5),(49.5,64.,10.5),(49.5,64.,14.5),(50.5,64.,14.5)),repeats=3,max_ticks=240)
    add('turn_180_while_moving','turns',(0.5,64.,-25.5),(0.5,64.,-35.5),baseline_path=((.5,64.,-35.5),),prelude_ticks=8,prelude_yaw=0.,repeats=5,description='Prelude moves south; measured task reverses north toward the target.')
    # Bounded physically reachable parkour fixtures. Gaps are not assumed safe by definition.
    add('parkour_level1_rise','parkour',(-40.5,64.,40.5),(-38.5,65.,40.5),terrain=True,jump=True,repeats=3)
    add('parkour_level2_gap','parkour',(12.5,64.,41.5),(15.5,64.,41.5),terrain=True,jump=True,repeats=3,max_ticks=120)
    add('parkour_level2_two_gaps','parkour',(21.5,64.,41.5),(29.5,64.,41.5),terrain=True,jump=True,repeats=3,max_ticks=220)
    add('parkour_level3_diagonal','parkour',(41.5,64.,41.5),(45.5,64.,45.5),terrain=True,jump=True,repeats=3,max_ticks=180)
    add('parkour_level4_platforms','parkour',(11.5,64.,52.5),(29.5,66.,59.5),terrain=True,jump=True,repeats=3,max_ticks=320,
        baseline_path=((16.5,64.,53.0),(20.5,65.,55.0),(24.5,65.,57.0),(29.5,66.,59.5)))
    # Exact reproduction class for the B01 partial-support roof edge plus normal access directions.
    add('roof_access_ascend','building',(52.5,64.,48.5),(52.5,67.,44.5),terrain=True,jump=True,repeats=3,max_ticks=220,
        baseline_path=((52.5,64.,47.5),(52.5,65.,46.5),(52.5,66.,45.5),(52.5,67.,44.5)),baseline_stop_waypoints=True)
    add('roof_descent_center','building',(52.5,67.,44.5),(52.5,64.,48.5),terrain=True,repeats=5,max_ticks=220,
        baseline_path=((52.5,66.,45.5),(52.5,65.,46.5),(52.5,64.,47.5),(52.5,64.,48.5)),baseline_stop_waypoints=True)
    add('roof_overhang_recovery','building',(52.5,66.,46.007832),(52.5,64.,48.5),terrain=True,repeats=5,max_ticks=180,
        baseline_path=((52.5,66.,45.5),(52.5,65.,46.5),(52.5,64.,47.5),(52.5,64.,48.5)),baseline_stop_waypoints=True,
        description='Center lacks support while the native body remains grounded on the adjacent top scaffold.')
    return tuple(rows)


def document():
    rows=[s.document() for s in scenarios()]
    return {'schema_version':1,'fixture':'blockwire-native-motion-v1','minecraft_version':'26.3',
            'coordinate_semantics':'feet positions','dynamic_generation':False,'scenarios':rows}


def digest():
    return hashlib.sha256(json.dumps(document(),sort_keys=True,separators=(',',':')).encode()).hexdigest()
