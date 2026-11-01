"""Deterministic TEST fixture program, never a productive build_house skill."""
import json
from blockwire.bcl import compile_bcl
from .reference import House

SEPARATOR='; @frame'

def frames(source,registry):
    chunks=[part.strip() for part in source.split(SEPARATOR) if part.strip()]
    if not chunks or len(chunks)>128:raise ValueError('Bounded explicit frame collection required')
    # Validate EVERY frame before first native effect, retain original frame IDs.
    return [(part,compile_bcl(part,registry)) for part in chunks]

def fixture_program():
    """Reviewed fixed 5x5 itinerary. Coordinates are fixture data, not navigation code."""
    lines=['S0 sync','S1 absolute','S2 normal','S3 stop','S4 60','I1 minecraft:cobblestone']
    def move(x,y,z):lines.append(f'M0 X{x} Y{y} Z{z}')
    cobblestone_requests=0
    def place(x,y,z,block='minecraft:cobblestone'):
        nonlocal cobblestone_requests
        if block=='minecraft:cobblestone':
            cobblestone_requests+=1
            if cobblestone_requests==65:lines.append('I1 minecraft:cobblestone')
        lines.extend([f'V2 X{x+.5} Y{float(y)} Z{z+.5}',f'I4 B{block} P"[{x},{y},{z}]"'])
    move(2.5,-60,-.5);move(2.5,-60,2.5)
    h=House()
    corners=[(0,0),(0,4),(4,0),(4,4)]
    wall_order=corners+[(x,z) for x in range(5) for z in range(5)
                        if (x in (0,4) or z in (0,4)) and (x,z) not in corners]
    # Corners first: a below-corner top face can become occluded by two already
    # raised adjacent walls even though its distance/face plane are legal.
    for y in (-60,-59):
        for x,z in wall_order:
            if not (x==2 and z==0):place(x,y,z)
    move(2.5,-60,1.5);lines.append('I1 minecraft:dirt');place(2,-60,2,'minecraft:dirt')
    move(2.5,-59,2.5);lines.append('I1 minecraft:cobblestone')
    for x,z in wall_order:place(x,-58,z)
    move(2.5,-60,1.5);lines.extend(['I1 minecraft:diamond_shovel','V2 X2.5 Y-59.5 Z2.5','C3 Bminecraft:dirt P"[2,-60,2]"'])
    move(2.5,-60,-.5);move(-.5,-60,-.5);move(-3.5,-60,1.5);lines.append('I1 minecraft:dirt')
    for y,xs in [(-60,range(-4,0)),(-59,range(-3,0)),(-58,range(-2,0)),(-57,range(-1,0))]:
        if y!=-60:move(float(y+55)+.5,y,2.5)  # previous, one-lower stair column
        for x in xs:place(x,y,2,'minecraft:dirt')
    move(-.5,-56,2.5);lines.append('I1 minecraft:cobblestone')
    perimeter=[(0,2),(0,1),(0,0),(1,0),(2,0),(3,0),(4,0),(4,1),(4,2),(4,3),(4,4),(3,4),(2,4),(1,4),(0,4),(0,3)]
    for x,z in perimeter:place(x,-57,z)
    for x in range(1,4):
        for z in range(1,4):place(x,-57,z)
    move(2.5,-56,2.5);move(.5,-56,2.5);lines.append('I1 minecraft:diamond_shovel')
    def remove(x,y):
        lines.extend([f'V2 X{x+.5} Y{y+.5} Z2.5',f'C3 Bminecraft:dirt Dtrue P"[{x},{y},2]"',f'M0 X{x+.5} Y{y} Z2.5'])
    # Dismantle TOP DOWN from retained cardinal support. C3 proves removal,
    # not pickup; explicit M0 descents still require native edges and floors.
    remove(-1,-57)
    move(-1.5,-57,2.5);remove(-1,-58);remove(-2,-58)
    move(-1.5,-58,2.5);remove(-1,-59);remove(-2,-59);remove(-3,-59)
    move(-1.5,-59,2.5)
    for x in (-1,-2,-3,-4):remove(x,-60)
    move(-1.5,-60,-.5);move(2.5,-60,-.5);move(2.5,-60,1.5);lines.extend(['V0','I0'])
    # Explicit small frames are transport bounds, NOT a new BCL language feature.
    # Eight operations leave cancellation responsive and fit the native task TTL.
    return ('\n'+SEPARATOR+'\n').join('\n'.join(lines[i:i+8]) for i in range(0,len(lines),8))+'\n'
