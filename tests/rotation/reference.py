"""Versioned hardcoded camera-rotation scenarios for the owned Minecraft 26.3 fixture."""
from dataclasses import dataclass,asdict
import hashlib,json,math


@dataclass(frozen=True)
class RotationScenario:
    name:str
    start_yaw:float
    start_pitch:float
    target_yaw:float
    target_pitch:float
    duration_ms:int
    movement:tuple[str,...]=()
    repeats:int=3
    supersede_after_ms:int|None=None
    supersede_yaw:float|None=None
    supersede_pitch:float|None=None
    cancel_after_ms:int|None=None
    sequence:tuple[tuple[int,float,float],...]=()
    requested_arc_degrees:float|None=None
    description:str=''
    def __post_init__(self):
        values=(self.start_yaw,self.start_pitch,self.target_yaw,self.target_pitch)
        if not all(math.isfinite(value) for value in values):raise ValueError('finite angles required')
        if not 1<=self.duration_ms<=5000 or not 1<=self.repeats<=10:raise ValueError('bounded scenario')
        if not -90<=self.start_pitch<=90 or not -90<=self.target_pitch<=90:raise ValueError('valid pitch required')
        if not -180<=self.target_yaw<=180 or not -180<=self.start_yaw<=180:raise ValueError('normalized yaw required')
        if self.supersede_after_ms is not None:
            if self.cancel_after_ms is not None or self.sequence:raise ValueError('one interruption policy')
            if self.supersede_yaw is None or self.supersede_pitch is None:raise ValueError('supersede target required')
        if self.cancel_after_ms is not None and self.sequence:raise ValueError('one interruption policy')
        if self.sequence and self.sequence[0][0]!=0:raise ValueError('sequence begins at zero')
    def document(self):
        row=asdict(self);row['movement']=list(self.movement);row['sequence']=[list(v) for v in self.sequence];return row


def _normal(yaw):return (yaw+180)%360-180


def scenarios():
    rows=[]
    def add(name,start_yaw,start_pitch,target_yaw,target_pitch,duration_ms,**kw):
        rows.append(RotationScenario(name,start_yaw,start_pitch,target_yaw,target_pitch,duration_ms,**kw))
    for angle in (15,45,90,135,180,270):
        for duration in (100,200,400):
            add(f'yaw_{angle}_{duration}ms',0.,0.,_normal(angle),0.,duration,requested_arc_degrees=float(angle))
    for duration in (100,200,400):
        add(f'pitch_up_30_{duration}ms',0.,0.,0.,-30.,duration)
        add(f'pitch_down_45_{duration}ms',0.,0.,0.,45.,duration)
        add(f'combined_yaw90_pitch30_{duration}ms',0.,0.,90.,-30.,duration)
        add(f'wrap_179_to_negative179_{duration}ms',179.,0.,-179.,0.,duration)
    add('wrap_negative179_to_179_200ms',-179.,0.,179.,0.,200)
    add('yaw_90_to_negative90_200ms',90.,0.,-90.,0.,200)
    add('yaw_180_to_0_200ms',180.,0.,0.,0.,200)
    add('identical_yaw_pitch_200ms',37.,-12.,37.,-12.,200)
    add('pitch_to_upper_boundary_200ms',0.,80.,0.,-90.,200)
    add('pitch_to_lower_boundary_200ms',0.,-80.,0.,90.,200)

    add('moving_walk_yaw45_200ms',0.,0.,45.,0.,200,movement=('forward',))
    for duration in (100,200,400):
        add(f'moving_walk_yaw90_{duration}ms',0.,0.,90.,0.,duration,movement=('forward',))
    add('moving_walk_yaw180_200ms',0.,0.,-180.,0.,200,movement=('forward',))
    add('moving_sprint_yaw90_200ms',0.,0.,90.,0.,200,movement=('forward','sprint'))
    add('moving_sneak_yaw90_200ms',0.,0.,90.,0.,200,movement=('forward','sneak'))
    add('moving_diagonal_yaw90_200ms',0.,0.,90.,0.,200,movement=('forward','right'))
    add('moving_diagonal_yaw135_200ms',0.,0.,135.,0.,200,movement=('forward','right'))

    add('supersede_yaw90_to150_after80ms',0.,0.,90.,0.,200,
        supersede_after_ms=80,supersede_yaw=150.,supersede_pitch=0.)
    add('moving_supersede_yaw90_to150_after80ms',0.,0.,90.,0.,200,movement=('forward',),
        supersede_after_ms=80,supersede_yaw=150.,supersede_pitch=0.)
    add('cancel_yaw180_after80ms',0.,0.,-180.,0.,400,cancel_after_ms=80)
    add('moving_cancel_yaw180_after80ms',0.,0.,-180.,0.,400,movement=('forward',),cancel_after_ms=80)
    add('moving_three_curves_200ms',0.,0.,45.,0.,200,movement=('forward',),
        sequence=((0,45.,0.),(220,-45.,0.),(440,90.,0.)),description='Three authorized targets without a full movement stop.')
    return tuple(rows)


def document():
    return {'schema_version':1,'fixture':'blockwire-native-motion-v1','minecraft_version':'26.3',
            'normal_rotation_uses_shortest_yaw_arc':True,'scenarios':[scenario.document() for scenario in scenarios()]}


def digest():
    return hashlib.sha256(json.dumps(document(),sort_keys=True,separators=(',',':')).encode()).hexdigest()
