"""Declarative benchmark geometry and independent predicates; never player actions."""
from collections import Counter
from dataclasses import dataclass
import hashlib
import json

AIR = frozenset({'minecraft:air', 'minecraft:cave_air', 'minecraft:void_air'})

@dataclass(frozen=True)
class House:
    origin: tuple = (0, -60, 0)
    width: int = 5
    depth: int = 5
    height: int = 3
    material: str = 'minecraft:cobblestone'

    def __post_init__(self):
        if (len(self.origin) != 3 or any(type(v) is not int for v in self.origin)
                or not all(type(v) is int and 3 <= v <= 9 for v in (self.width, self.depth))
                or type(self.height) is not int or not 2 <= self.height <= 4
                or self.width % 2 == 0 or not self.material.startswith('minecraft:')):
            raise ValueError('Bounded odd-width reference required')

    def point(self, x, y, z):
        return tuple(a+b for a, b in zip(self.origin, (x, y, z)))

    @property
    def entrance(self): return self.point(self.width//2, 0, 0)

    def blocks(self):
        result = {}
        for y in range(self.height):
            for x in range(self.width):
                for z in range(self.depth):
                    if x not in (0, self.width-1) and z not in (0, self.depth-1): continue
                    if x == self.width//2 and z == 0 and y < 2: continue
                    result[self.point(x,y,z)] = self.material
        result.update({self.point(x,self.height,z): self.material
                       for x in range(self.width) for z in range(self.depth)})
        return result

    def interior(self):
        return {self.point(x,0,z) for x in range(1,self.width-1) for z in range(1,self.depth-1)}

    def clear(self):
        result = {self.point(x,y,z) for x in range(1,self.width-1)
                  for z in range(1,self.depth-1) for y in range(self.height)}
        result |= {self.point(self.width//2,y,z) for y in range(2) for z in (0,-1,-2)}
        return result

    def workspace(self):
        # All above-ground cells in the declared local site must be either part
        # of the house or air. This also catches abandoned temporary scaffolds.
        return {self.point(x,y,z) for x in range(-16,17)
                for z in range(-16,17) for y in range(13)}

    def floors(self):
        return {self.point(x,-1,z) for x in range(-16,17)
                for z in range(-16,17)}

    def document(self):
        return {'id':'superflat_house_5x5', 'origin':list(self.origin),
                'width':self.width,'depth':self.depth,'height':self.height,
                'material':self.material,'entrance':list(self.entrance),
                'blocks':[{'position':list(p),'block':b} for p,b in sorted(self.blocks().items())],
                'clear':[list(p) for p in sorted(self.clear())],
                'workspace_bounds':[list(self.point(-16,0,-16)),list(self.point(16,12,16))],
                'floor_material':'minecraft:grass_block'}

    def digest(self):
        return hashlib.sha256(json.dumps(self.document(),sort_keys=True).encode()).hexdigest()


def verify(house, observed, *, native):
    """Only independent observed voxel IDs + final native geometry, NOT receipts.

    ``observed`` belongs to a closed, hashed test save, not the model's plan. A
    missing chunk/section or absent observation stays UNKNOWN (never inferred air).
    """
    rows=[]
    for position,block in sorted(house.blocks().items()):
        actual=observed.get(position)
        state=('UNKNOWN' if actual is None else 'CORRECT' if actual==block
               else 'MISSING' if actual in AIR else 'INCORRECT')
        rows.append({'position':list(position),'expected':block,'observed':actual,'state':state})
    counts=Counter(r['state'] for r in rows)
    clear=all(observed.get(p) in AIR for p in house.clear())
    extras=[list(p) for p in sorted(house.workspace()-set(house.blocks()))
            if observed.get(p) not in AIR]
    floor=all(observed.get(p)=='minecraft:grass_block' for p in house.floors())
    roof=all(observed.get(house.point(x,house.height,z))==house.material
             for x in range(house.width) for z in range(house.depth))
    # Native mesh proves collision, floor, headroom, connected entrance and safe
    # player state. It is captured after the final action, never from baseline.
    accessible=native.get('interior_accessible') is True
    safe=native.get('safe_player') is True
    result={'project':'superflat_house_5x5','expected_blocks':len(rows),
            'verified_blocks':counts['CORRECT'],'incorrect_blocks':counts['INCORRECT'],
            'missing_blocks':counts['MISSING'],'unknown_blocks':counts['UNKNOWN'],
            'entrance_clear':all(observed.get(house.point(house.width//2,y,0)) in AIR for y in range(2)),
            'interior_clear':clear,'interior_accessible':accessible,'roof_complete':roof,
            'floor_intact':floor,'safe_player':safe,'unexpected_or_unknown_cells':extras,'requirements':rows}
    result['objective_verified']=bool(counts['CORRECT']==len(rows) and clear and not extras and floor and roof and accessible and safe)
    return result
