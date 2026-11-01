"""Bounded persistent project facts, not a construction/progression planner.

Plans and revisions come from the external model. Only observations may establish
progress. Journals reuse SessionStore's private SQLite/ownership boundary.
"""
from __future__ import annotations
import copy
from collections import Counter
import hashlib
import json
import math
import time
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .agent import SessionStore
from .recipes import RECIPES, PLANKS
from .skills.distance import _observed

Position = Annotated[list[int], Field(min_length=3, max_length=3)]
SOLIDS = frozenset({'minecraft:dirt','minecraft:grass_block','minecraft:stone','minecraft:cobblestone',*PLANKS})

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,allow_inf_nan=False)

class BlockRequirement(Strict):
    position: Position
    block: str = Field(pattern=r'^[a-z0-9_.-]+:[a-z0-9_./-]+$',max_length=128)
    section: str = Field(min_length=1,max_length=48)

class Enclosure(Strict):
    interior: list[Position] = Field(min_length=1,max_length=36)
    entrance: Position
    height: int = Field(default=2,ge=2,le=4)

class ProjectPlan(Strict):
    site: Position
    dimension: str = Field(min_length=1,max_length=128)
    blocks: list[BlockRequirement] = Field(min_length=1,max_length=256)
    sections: list[str] = Field(min_length=1,max_length=16)
    reserves: dict[str,int] = Field(default_factory=dict,max_length=16)
    enclosure: Enclosure | None = None

    @model_validator(mode='after')
    def bounds(self):
        positions=[tuple(b.position) for b in self.blocks]
        if len(set(positions))!=len(positions):raise ValueError('Duplicate block requirement')
        if len(set(self.sections))!=len(self.sections) or any(not 1<=len(s)<=48 for s in self.sections):raise ValueError('Unique bounded sections required')
        if any(b.section not in self.sections for b in self.blocks):raise ValueError('Unknown section')
        if any(type(n)is not int or not 0<=n<=256 for n in self.reserves.values()):raise ValueError('Bounded material reserves required')
        points=[self.site]+[b.position for b in self.blocks]
        if self.enclosure:points+=self.enclosure.interior+[self.enclosure.entrance]
        if any(abs(p[0])>29999984 or abs(p[2])>29999984 or not -64<=p[1]<=320 or max(abs(p[i]-self.site[i]) for i in range(3))>16 for p in points):raise ValueError('Project exceeds bounded local site')
        return self


def enclosure_contract(plan: ProjectPlan):
    """Validate the MODEL'S geometry, never generate blocks or actions for it."""
    e=plan.enclosure
    if e is None:return {'valid':False,'reason':'enclosure_manifest_required'}
    inside={tuple(p) for p in e.interior};door=tuple(e.entrance)
    if len(inside)!=len(e.interior) or door in inside or len({p[1] for p in inside|{door}})!=1:return {'valid':False,'reason':'invalid_interior_or_entrance'}
    neighbors=lambda p:[(p[0]+dx,p[1],p[2]+dz) for dx,dz in ((1,0),(-1,0),(0,1),(0,-1))]
    seen={next(iter(inside))}
    while True:
        expanded=seen|{q for p in seen for q in neighbors(p) if q in inside}
        if expanded==seen:break
        seen=expanded
    boundary={(x+dx,y,z+dz) for x,y,z in inside for dx in (-1,0,1) for dz in (-1,0,1) if (x+dx,y,z+dz) not in inside}
    if seen!=inside or not any(door in neighbors(p) for p in inside):return {'valid':False,'reason':'connected_interior_and_adjacent_entrance_required'}
    materials={tuple(b.position):b.block for b in plan.blocks};blocks=set(materials)
    required={(x,y+e.height,z) for x,y,z in inside|{door}}
    required|={(x,y+h,z) for x,y,z in boundary-{door} for h in range(e.height)}
    if any(materials.get(p) not in SOLIDS for p in required):return {'valid':False,'reason':'planned_envelope_has_holes','undeclared':list(map(list,sorted(required-blocks)))}
    if any((x,y+h,z) in blocks for x,y,z in inside|{door} for h in (0,1)):return {'valid':False,'reason':'planned_headroom_obstructed'}
    return {'valid':True,'interior_cells':len(inside),'required_envelope_blocks':len(required)}


def material_report(plan,progress,inventory):
    """Counts and independent one-recipe options, NOT a resource-selection policy."""
    demand=Counter(b.block for b in plan.blocks if progress.get(_key(b.position),{}).get('status')!='correct')
    demand.update(plan.reserves);result={}
    known=Counter(b.block for b in plan.blocks if progress.get(_key(b.position),{}).get('status') in {'missing','wrong'})
    unknown=Counter(b.block for b in plan.blocks if progress.get(_key(b.position),{}).get('status','unknown')=='unknown')
    for item,needed in demand.items():
        available=inventory.get(item,0);short=max(0,needed-available);options=[]
        recipe=RECIPES.get(item)
        if recipe:
            ingredients=Counter(t for row in recipe.rows for t in row if t)
            batches=min((sum(inventory.get(p,0) for p in PLANKS) if token=='#planks' else inventory.get(token,0))//count for token,count in ingredients.items())
            options=[{'recipe':recipe.describe(),'available_batches':batches,'possible_output':batches*recipe.count,'shortfall_after_this_option':max(0,short-batches*recipe.count),'independent_option_not_reserved':True}]
        result[item]={'unverified_or_missing':needed,'known_missing_or_wrong':known[item],'unknown_requires_observation':unknown[item],
                      'inventory':available,'shortfall_known':max(0,known[item]+plan.reserves.get(item,0)-available),
                      'shortfall_worst_case':short,'shortfall':short,'craft_options':options}
    return result


def _key(position):return ','.join(map(str,position))

def _digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

class ProjectJournal:
    """One exclusive journal per project; world ID is explicit operator identity.

    It is NOT a hidden native save UUID. Callers must select the correct world and
    explicitly authorize actor replacement. On every activation old proof is stale.
    """
    def __init__(self,path,identity,project_id,goal,*,policy='enclosure_v1',clock=time.time):
        if policy not in {'enclosure_v1','blocks_v1'}:raise ValueError('Unknown trusted acceptance policy')
        if not isinstance(project_id,str) or not 1<=len(project_id)<=128 or not isinstance(goal,str) or not 1<=len(goal)<=2048:raise ValueError('Bounded project identity/goal required')
        self.store=SessionStore(path,identity);self.project_id=project_id;self.goal=goal;self.policy=policy;self.clock=clock;self.state=None;self.actor=None
    def __enter__(self):
        try:
            self.state=self.store.acquire()
            if 'project' not in self.state:
                self.state['project']={'id':self.project_id,'goal':self.goal,'policy':self.policy,'revision':0,'plan':None,'evidence':{},'progress':{},'inventory':{},'last_world':None,'pending':None,'status':'OBJECTIVE_INCOMPLETE','history':[],'blockers':[],'counters':{'model_calls':0,'operations':0,'placement_events':0},'material_ledger':{},'constructed_targets':{},'observed_unfulfilled':{},'inventory_witness':False,'binding':None,'request_watermarks':{},'last_receipt':None,'final_sweep':False}
            self.p=self.state['project']
            if (self.p['id'],self.p['goal'],self.p['policy'])!=(self.project_id,self.goal,self.policy):raise ValueError('Project contract mismatch')
            self.invalidate('activation_requires_fresh_observation')
            return self
        except BaseException:self.store.release();raise
    def __exit__(self,*_):self.store.release()
    def save(self):self.store.save(self.state)
    def event(self,kind,**data):
        self.p['history']=(self.p['history']+[{'kind':kind,'at':self.clock(),**data}])[-16:]
    def invalidate(self,reason):
        self.p.update(evidence={},navigation={},progress={},inventory={},inventory_witness=False,status='OBJECTIVE_INCOMPLETE',acceptance={'verified':False,'reason':reason},final_sweep=False)
        self.event('proof_invalidated',reason=reason);self.save()
    def bind(self,scene,*,allow_rebind=False):
        if type(allow_rebind)is not bool:raise ValueError('Explicit boolean actor rebind permission required')
        if not scene.get('in_world') or not scene.get('alive') or scene.get('player_uuid')!=self.store.identity['player_id']:raise ValueError('Live matching player required')
        binding={'actor_session':scene.get('actor_session'),'dimension':scene.get('dimension')}
        if not all(isinstance(v,str) and v for v in binding.values()):raise ValueError('Native actor and dimension required')
        if self.p['plan'] and self.p['plan']['dimension']!=binding['dimension']:raise ValueError('Different dimension requires a separate project')
        if self.p['binding'] and self.p['binding']!=binding and not allow_rebind:raise ValueError('Explicit project actor rebind required')
        if self.p.get('pending'):self.event('interrupted_intent_not_replayed',intent=self.p['pending']);self.p['pending']=None
        self.p['binding']=binding;self.p['activation_confirmed']=[];self.actor=binding['actor_session'];self.invalidate('new_activation_binding')
    def revise(self,value):
        if self.p['pending']:raise ValueError('Resolve uncertain pending work before revising the project')
        plan=ProjectPlan.model_validate(value)
        if not self.actor or plan.dimension!=self.p['binding']['dimension']:raise ValueError('Plan dimension mismatch')
        contract=enclosure_contract(plan) if self.policy=='enclosure_v1' else {'valid':True}
        if not contract['valid']:raise ValueError(json.dumps(contract))
        dumped=plan.model_dump()
        if dumped==self.p['plan']:return
        desired={_key(b.position):b.block for b in plan.blocks}
        baseline={k:v for k,v in self.p.get('observed_unfulfilled',{}).items() if desired.get(k)==v}
        self.p.update(plan=dumped,revision=self.p['revision']+1,confirmed_high_water=[],activation_confirmed=[],observed_unfulfilled=baseline)
        self.event('plan_revised',revision=self.p['revision'],digest=_digest(dumped));self.invalidate('plan_revision_requires_reconciliation')
    def intent(self,source,request_id,session_id,operation_count):
        if self.p['pending']:raise ValueError('Uncertain pending work: observe/rebind, never replay')
        if not self.actor or not self.p['plan']:raise ValueError('Bound project plan required before actions')
        if not isinstance(source,str) or not 1<=len(source)<=16384 or type(request_id)is not int or not 1<=request_id<=9007199254740991 or not isinstance(session_id,str) or not 1<=len(session_id)<=128 or type(operation_count)is not int or not 1<=operation_count<=32:raise ValueError('Bounded intent required')
        if self.p['counters']['operations']+operation_count>512:raise ValueError('Project operation budget exhausted')
        watermarks=self.p.setdefault('request_watermarks',{})
        if request_id<=watermarks.get(session_id,0):raise ValueError('Stale project request ID; inspect outcomes, never replay')
        if session_id not in watermarks and len(watermarks)>=32:raise ValueError('Project session bound exhausted')
        watermarks[session_id]=request_id
        self.p['counters']['operations']+=operation_count
        self.p['pending']={'source':source,'request_id':request_id,'session_id':session_id,'revision':self.p['revision'],'digest':_digest(source)}
        self.p['status']='OBJECTIVE_INCOMPLETE';self.save()  # Durable BEFORE effects, never auto-replayed.
    def observe(self,scene,inventory=None,*,observed_at=None):
        if not self.actor or scene.get('actor_session')!=self.actor or scene.get('dimension')!=self.p['binding']['dimension']:raise ValueError('Project observation actor/dimension mismatch')
        if scene.get('player_uuid',self.store.identity['player_id'])!=self.store.identity['player_id']:raise ValueError('Project observation player mismatch')
        if scene.get('alive') is False or scene.get('in_world') is False:self.invalidate('actor_not_alive');return
        now=self.clock();stamp=now if observed_at is None else observed_at
        if type(stamp)not in (int,float) or not math.isfinite(stamp) or stamp>now+2:raise ValueError('Invalid observation timestamp')
        evidence=self.p['evidence']
        for row in _observed(type('ReadOnly',(),{'check':lambda _:None})(),scene):
            evidence[_key(row['position'])]={'position':row['position'],'block':row['id'],'at':stamp,'source':'native_visible_surface'}
        nav=scene.get('navigation') or {}
        if not nav.get('ready') or nav.get('profile')!='stepped_full_blocks_v1':self.p['navigation']={}
        if nav.get('ready') and nav.get('profile')=='stepped_full_blocks_v1':
            if nav.get('actor_session',self.actor)!=self.actor:raise ValueError('Navigation actor mismatch')
            # A full cube cannot occupy the native standing body/head volume.
            # This is NOT proof of literal air, nor arbitrary hidden block lookup.
            solids=set()
            for cell in nav['cells']:
                if cell['hazards']:continue
                x,y,z=cell['position']
                for p in ([x,y,z],[x,y+1,z]):
                    k=_key(p);solids.add(k)
                    if k in evidence and evidence[k]['block'] in SOLIDS:evidence.pop(k)
            self.p['navigation']={'value':nav,'at':stamp,'clear_full_cube':list(solids)}
        # Store only current-plan targets (not an expanding world map).
        targets={_key(b['position']) for b in (self.p['plan'] or {}).get('blocks',[])}
        self.p['evidence']={k:v for k,v in evidence.items() if k in targets and now-v['at']<=120}
        if inventory is not None:self.inventory(inventory)
        self.p['last_world']={'actor_session':self.actor,'dimension':scene['dimension'],'position':scene.get('position'),'health':scene.get('health'),'at':now}
        self.reconcile();self.save()
    def inventory(self,counts):
        if not isinstance(counts,dict) or len(counts)>256 or any(not isinstance(k,str) or len(k)>128 or type(v)is not int or not 0<=v<=100000 for k,v in counts.items()):raise ValueError('Bounded observed inventory required')
        if self.p.get('inventory_witness'):
            delta={k:counts.get(k,0)-self.p['inventory'].get(k,0) for k in counts.keys()|self.p['inventory'].keys() if counts.get(k,0)!=self.p['inventory'].get(k,0)}
            if delta:self.event('inventory_delta_observed',delta=delta,attribution='Net change, not proof of gathering/crafting/consumption cause')
        self.p['inventory']=dict(counts);self.p['inventory_witness']=True
    def reconcile(self):
        if not self.p['plan']:return
        plan=ProjectPlan.model_validate(self.p['plan']);now=self.clock();nav=self.p.get('navigation',{});fresh_nav=now-nav.get('at',0)<=10
        clear=set(nav.get('clear_full_cube',[])) if fresh_nav else set();rows={};old=self.p.get('progress',{})
        for b in plan.blocks:
            key=_key(b.position);proof=self.p['evidence'].get(key)
            if proof and now-proof['at']<=120:status='correct' if proof['block']==b.block else 'wrong'
            elif b.block in SOLIDS and key in clear:status='missing'
            else:status='unknown'
            rows[key]={'status':status,'expected':b.block,'observed':proof['block'] if proof else None,'section':b.section}
            if old.get(key,{}).get('status')=='correct' and status in {'wrong','missing'}:self.event('world_change_observed',position=b.position,status=status)
        self.p['progress']=rows
        baseline=self.p.setdefault('observed_unfulfilled',{})
        for key,row in rows.items():
            if row['status'] in {'missing','wrong'}:baseline[key]=row['expected']
        correct={k for k,r in rows.items() if r['status']=='correct'}
        self.p['confirmed_high_water']=sorted(set(self.p.get('confirmed_high_water',[]))|correct)
        self.p['activation_confirmed']=sorted(set(self.p.get('activation_confirmed',[]))|correct)
        if rows!=old:self.event('PROJECT_PROGRESS',correct=sum(r['status']=='correct' for r in rows.values()),total=len(rows),revision=self.p['revision'])
        complete=all(r['status']=='correct' for r in rows.values())
        acceptance={'verified':complete,'reason':'all_planned_blocks_observed' if complete else 'planned_blocks_unconfirmed'}
        if self.policy=='enclosure_v1' and complete:
            e=plan.enclosure;geometry=nav.get('value',{})
            from .skills.approaching import _reachable
            reachable=set(_reachable(geometry,True)) if fresh_nav else set()
            needed={tuple(p) for p in e.interior+[e.entrance]}
            edges={frozenset((tuple(geometry['cells'][a]['position']),tuple(geometry['cells'][b]['position']))) for a,b in geometry.get('edges',[])}
            door=tuple(e.entrance)
            connected=any(frozenset((door,tuple(p))) in edges for p in e.interior)
            valid=enclosure_contract(plan)['valid'] and needed<=reachable and connected
            acceptance={'verified':valid,'reason':'observed_envelope_and_native_interior_entrance' if valid else 'fresh_reachable_interior_floor_headroom_entrance_required'}
        # Observed subconditions do not yet attest a final, quiescent objective.
        observed=acceptance['verified']
        changed=any(baseline.get(_key(b.position))==b.block and rows[_key(b.position)]['status']=='correct' for b in plan.blocks)
        # A verified placement outcome already contains actual native appearance
        # AND consumption proof, unlike a raw input receipt. It may supplement a
        # missing baseline; it NEVER replaces fresh full-objective observations.
        contributed=any(self.p.get('constructed_targets',{}).get(_key(b.position))==b.block and rows[_key(b.position)]['status']=='correct' for b in plan.blocks)
        verified=bool(observed and not self.p['pending'] and self.p.get('final_sweep') and (self.policy!='enclosure_v1' or changed or contributed))
        self.p['acceptance']={**acceptance,'postconditions_observed':observed,'verified':verified}
        status='OBJECTIVE_VERIFIED' if verified else 'OBJECTIVE_INCOMPLETE'
        if status!=self.p['status']:self.event(status,reason=acceptance['reason'])
        self.p['status']=status
    def result(self,response):
        receipt=[response.get('session_id'),response.get('request_id')]
        if receipt==self.p.get('last_receipt'):return
        pending=self.p['pending']
        if not pending or receipt!=[pending['session_id'],pending['request_id']]:raise ValueError('Uncorrelated project result')
        actual=response.get('result') or {};ops=actual.get('operations',[])
        # Movement/camera do not prove block changes. Mining/placement may invalidate
        # old surface claims, even if their batch fails or is partially executed.
        mutators={'core:inventory.place','core:inventory.place_at','core:movement.dig_step','core:crafting.gather_block','core:crafting.gather_wood','core:crafting.remove_block'}
        for op in ops:
            self.event('COMMAND_COMPLETED',command=op.get('command'),status=op.get('status'),reason=op.get('reason'))
            if op.get('command') in mutators and not (op.get('command') in {'core:inventory.place','core:inventory.place_at'} and op.get('status')=='succeeded' and op.get('reason')=='desired_block_already_observed'):
                self.p['final_sweep']=False
                target=op.get('evidence',{}).get('position')
                if op.get('command') in {'core:inventory.place','core:inventory.place_at'} and target:
                    self.p['evidence'].pop(_key(target),None);self.p['navigation']={}
                else:self.invalidate('world_mutation_requires_fresh_sweep')
            if op.get('command') in {'core:inventory.place','core:inventory.place_at'} and op.get('status')=='succeeded' and op.get('reason')=='block_placed':
                self.p['counters']['placement_events']+=1
                block=op.get('evidence',{}).get('block')
                if block in SOLIDS:self.p['material_ledger'][block]=self.p['material_ledger'].get(block,0)+1
                position=op.get('evidence',{}).get('position')
                if block and position:
                    built=self.p.setdefault('constructed_targets',{})
                    if len(built)>=256 and _key(position) not in built:raise ValueError('Constructed target bound exceeded')
                    built[_key(position)]=block
            scene=op.get('output',{})
            if scene.get('visibility'):self.observe(scene,observed_at=op.get('observed_at'))
            if 'inventory' in scene:self.inventory(scene['inventory'])
        failures=[{'command':o.get('command'),'reason':o.get('reason'),'evidence':o.get('evidence',{}),'scope':'current_native_observation_not_global_unreachable'} for o in ops if o.get('status')!='succeeded']
        self.p['blockers']=(self.p['blockers']+failures)[-16:]
        self.event('BATCH_COMPLETED',status=response.get('status'),operations=[{k:o.get(k) for k in ('command','status','reason')} for o in ops][:32])
        if response.get('status')!='completed':
            self.p['navigation']={}
            if not ops or any(o.get('command') in mutators for o in ops):self.invalidate('failed_or_partial_batch_requires_reconciliation')
            # A local walking/aiming/precondition failure is not evidence that
            # every observed wall disappeared. Keep bounded surface proof.
        self.p['last_receipt']=receipt;self.p['pending']=None;self.reconcile();self.save()
    def begin_verification(self):
        if self.p['pending']:raise ValueError('Cannot verify uncertain outstanding effects')
        self.invalidate('independent_read_only_final_sweep');self.p['final_sweep']=True;self.save()
    def summary(self):
        self.reconcile()
        progress=self.p['progress'];sections={}
        for name in (self.p['plan'] or {}).get('sections',[]):
            counts=Counter(r['status'] for r in progress.values() if r['section']==name);sections[name]=dict(counts)
        return copy.deepcopy({'project_id':self.project_id,'goal':self.goal,'acceptance_policy':self.policy,'verification_sweep':bool(self.p.get('final_sweep')),'evidence_max_age_seconds':{'surfaces':120,'navigation':10},'world_identity':self.store.identity,'world_identity_source':'operator-selected namespace, not hidden native save UUID','revision':self.p['revision'],'plan':self.p['plan'],'status':self.p['status'],'acceptance':self.p['acceptance'],'sections':sections,'requirements':[{'position':list(map(int,k.split(','))),'view_point':[v+.5 for v in map(int,k.split(','))],**r} for k,r in progress.items()],'verified_placement_consumption':self.p['material_ledger'],'materials':material_report(ProjectPlan.model_validate(self.p['plan']),progress,self.p['inventory']) if self.p['plan'] else {},'inventory':self.p['inventory'],'blockers':self.p['blockers'],'pending':self.p['pending'],'last_observed_world':self.p['last_world'],'last_observed_world_requires_revalidation':not bool(self.p['evidence']) or self.p['last_world'] is None or self.p['last_world']['actor_session']!=self.actor,'counters':self.p['counters'],'persistent_limits':{'model_calls':160,'operations':512,'placement_requests':256,'gather_requests':512,'craft_batches':128},'recent_events':self.p['history'][-8:]})
