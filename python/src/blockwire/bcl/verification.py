"""Pure observed-state acceptance. Generates NO actions or building plans.

Client surfaces and native collision cells only, never saved-world/hidden queries.
Unknown blocks remain unknown. The qualification host must separately require
actual native construction (not just occupation of a pre-existing natural cave).
"""
SOLIDS=frozenset({'minecraft:cobblestone','minecraft:dirt','minecraft:grass_block','minecraft:stone'})

def _evidence(expected_blocks,observed_blocks):
    if not isinstance(expected_blocks,list) or not 1<=len(expected_blocks)<=128:return None,None,{'verified':False,'reason':'bounded_manifest_required'}
    try:
        expected={tuple(r['position']):r['block'] for r in expected_blocks}
        observed={tuple(r['position']):r['id'] for r in observed_blocks}
    except (KeyError,TypeError):return None,None,{'verified':False,'reason':'invalid_manifest'}
    if len(expected)!=len(expected_blocks) or any(len(p)!=3 or any(type(n)is not int for n in p) or type(b)is not str or b not in SOLIDS for p,b in expected.items()):return None,None,{'verified':False,'reason':'invalid_manifest'}
    missing=[list(p) for p,b in expected.items() if observed.get(p)!=b]
    if missing:return None,None,{'verified':False,'reason':'shell_not_observed','missing':missing}
    return expected,observed,None

def verify_shelter(expected_blocks,observed_blocks,navigation):
    """Strict rectangular shell criterion used for the model-chosen Stage A design."""
    def fail(reason,**extra):return {'verified':False,'reason':reason,**extra}
    expected,observed,error=_evidence(expected_blocks,observed_blocks)
    if error:return error
    xs,ys,zs=zip(*expected);lo=(min(xs),min(ys),min(zs));hi=(max(xs),max(ys),max(zs))
    if not (2<=hi[0]-lo[0]<=6 and 2<=hi[2]-lo[2]<=6 and 2<=hi[1]-lo[1]<=4):return fail('unsupported_bounded_shelter_dimensions')
    x0,y0,z0=lo;x1,roof,z1=hi
    roof_cells={(x,roof,z) for x in range(x0,x1+1) for z in range(z0,z1+1)}
    walls={(x,y,z) for x in range(x0,x1+1) for z in range(z0,z1+1) for y in range(y0,roof) if x in {x0,x1} or z in {z0,z1}}
    opening=walls-set(expected)
    if len(opening)!=2:return fail('exactly_one_two_block_entrance_required')
    door=sorted(opening,key=lambda p:p[1]);a,b=door
    if a[0]!=b[0] or a[2]!=b[2] or (a[1],b[1])!=(y0,y0+1) or (a[0] in {x0,x1} and a[2] in {z0,z1}):return fail('invalid_entrance')
    if set(expected)!=(walls-opening)|roof_cells:return fail('manifest_not_closed_walls_and_full_roof')
    if not navigation.get('ready') or navigation.get('profile')!='stepped_full_blocks_v1':return fail('fresh_native_geometry_required')
    positions=[tuple(c['position']) for c in navigation['cells'] if not c['hazards']]
    interior={(x,y0,z) for x in range(x0+1,x1) for z in range(z0+1,z1)}
    if not interior<=set(positions) or a not in positions:return fail('floor_headroom_or_entrance_not_verified')
    full=[tuple(c['position']) for c in navigation['cells']]
    connected=any((full[i]==a and full[j] in interior) or (full[j]==a and full[i] in interior) for i,j in navigation['edges'])
    if not connected:return fail('native_doorway_edge_not_verified')
    return {'verified':True,'reason':'observed_shelter_shell_and_native_doorway','bounds':[list(lo),list(hi)],
            'wall_blocks':len(walls-opening),'roof_blocks':len(roof_cells),'entrance':[list(p) for p in door],
            'scope':'client-observed shell plus bounded native floor/headroom/doorway geometry, not server-atomic truth'}

def verify_usable_shelter(expected_blocks,observed_blocks,navigation):
    """Allow an earth-integrated shelter, not only a freestanding rectangular box.

    Requires a model-declared observed solid roof, three full side walls, native
    supported standing/headroom and an actual reachable native entrance edge.
    Natural materials do not excuse missing geometry or construction evidence.
    """
    expected,observed,error=_evidence(expected_blocks,observed_blocks)
    if error:return error
    if not navigation.get('ready') or navigation.get('profile')!='stepped_full_blocks_v1':return {'verified':False,'reason':'fresh_native_geometry_required'}
    from ..skills.approaching import _reachable
    reachable=set(_reachable(navigation,True));positions=[tuple(c['position']) for c in navigation['cells']]
    for x,y,z in reachable:
        for height in (2,3,4):
            roof=(x,y+height,z)
            if roof not in expected or observed.get(roof) not in SOLIDS:continue
            closed=[];openings=[]
            for dx,dz in ((1,0),(-1,0),(0,1),(0,-1)):
                column=[(x+dx,level,z+dz) for level in range(y,y+height)]
                if all(observed.get(p) in SOLIDS for p in column):closed.append(column)
                else:
                    adjacent=[p for p in reachable if p[0]==x+dx and p[2]==z+dz and abs(p[1]-y)<=1]
                    for other in adjacent:
                        a,b=positions.index((x,y,z)),positions.index(other)
                        if any(set(e)=={a,b} for e in navigation['edges']):openings.append(other)
            if len(closed)>=3 and openings:
                return {'verified':True,'reason':'observed_usable_shelter','interior':[x,y,z],'roof':list(roof),'wall_height':height,
                        'entrance':list(openings[0]),'natural_materials_allowed':True,
                        'scope':'observed roof/three side walls and native reachable entrance/floor/headroom; construction must be independently evidenced'}
    return {'verified':False,'reason':'closed_walls_roof_and_native_entrance_not_proven'}
