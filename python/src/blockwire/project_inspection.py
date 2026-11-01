"""Bounded mechanical inspection of a MODEL's existing plan through BCL only.

No construction, mining, resource choices, hidden lookup or independent controls.
Face-centre aiming avoids rays to cube centres hitting an intervening neighbor.
The exchange callback owns existing SDK routing, actor fences, budgets and cleanup.
"""
import math
from .skills.approaching import _reachable

async def inspect_project(journal,exchange,*,max_operations=64,check=lambda:None):
    if type(max_operations)is not int or not 1<=max_operations<=128:raise ValueError('Bounded inspection required')
    if not journal.p['plan'] or journal.p['pending']:raise ValueError('Quiescent typed plan required')
    journal.begin_verification();used=0;scene=None;visited=set();attempted=set();origin=None
    async def send(source):
        nonlocal used,scene
        check();count=len(source.splitlines())
        if used+count>max_operations:return False
        used+=count
        response=await exchange(source)
        check()
        for op in response.get('result',{}).get('operations',[]):
            if op.get('output',{}).get('visibility'):scene=op['output']
        return response.get('status')=='completed'
    if not await send('V0'):return {'verified':False,'reason':'inspection_observation_failed','operations':used}
    if not scene or not scene.get('navigation',{}).get('ready'):return {'verified':False,'reason':'inspection_geometry_required','operations':used}
    origin=tuple(scene['navigation']['current_cell']);visited.add(origin)
    normals=((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1))
    for _ in range(8):
        check();journal.reconcile()
        if journal.p['status']=='OBJECTIVE_VERIFIED':return {'verified':True,'reason':'observed_project','operations':used}
        # A real mismatch needs external replanning, not repeated blind views.
        if any(r['status'] in {'wrong','missing'} for r in journal.p['progress'].values()):
            return {'verified':False,'reason':'observed_project_mismatch','operations':used}
        unknown=[list(map(int,k.split(','))) for k,r in journal.p['progress'].items() if r['status']=='unknown']
        eye=scene['eye_position']
        unknown.sort(key=lambda p:math.dist(eye,[v+.5 for v in p]))
        # Re-evaluate after every target: one native surface snapshot may confirm
        # many requirements. Never interpret aiming itself as block existence.
        for position in unknown[:2]:
            key=','.join(map(str,position))
            attempted.add((tuple(scene.get('navigation',{}).get('current_cell',origin)),key))
            if journal.p['progress'].get(key,{}).get('status')=='correct':continue
            points=[]
            for normal in normals:
                aim=[position[i]+.5+normal[i]*.5 for i in range(3)]
                if sum((eye[i]-aim[i])*normal[i] for i in range(3))>.01:points.append(aim)
            points.sort(key=lambda p:math.dist(eye,p))
            for aim in points[:3]:
                if used+2>max_operations:break
                if not await send('V2 X'+str(float(aim[0]))+' Y'+str(float(aim[1]))+' Z'+str(float(aim[2]))+'\nV0'):break
                if journal.p['status']=='OBJECTIVE_VERIFIED':return {'verified':True,'reason':'observed_project','operations':used}
                if journal.p['progress'].get(key,{}).get('status')=='correct':break
        if used+3>max_operations:break
        nav=scene.get('navigation',{});current=tuple(nav.get('current_cell',origin));reachable=_reachable(nav,True) if nav.get('ready') else []
        unknown=[list(map(int,k.split(','))) for k,r in journal.p['progress'].items() if r['status']=='unknown']
        if not unknown:
            # Keep floor/entrance proof in the original local elevation band.
            candidates=[origin] if origin in reachable and current!=origin else []
        else:
            candidates=[tuple(c) for c in reachable if any((tuple(c),','.join(map(str,p))) not in attempted for p in unknown) and abs(c[1]-origin[1])<=1
                        and any(math.dist((c[0]+.5,c[1]+1.62,c[2]+.5),[v+.5 for v in p])<=6 for p in unknown)]
            candidates.sort(key=lambda c:(min(math.dist((c[0]+.5,c[1]+1.62,c[2]+.5),[v+.5 for v in p]) for p in unknown),math.dist(current,c)))
        if not candidates:break
        cell=candidates[0];visited.add(cell)
        if not await send(f'M0 X{cell[0]+.5} Y{float(cell[1])} Z{cell[2]+.5}\nV0'):break
    journal.reconcile()
    return {'verified':journal.p['status']=='OBJECTIVE_VERIFIED','reason':'inspection_budget_or_visibility_limit','operations':used}
