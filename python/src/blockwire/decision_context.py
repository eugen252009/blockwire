"""Bounded descriptive feedback for external deciders, never a gameplay planner.

Uses only explicitly supplied native observations. Does not discover resources,
select routes/actions, infer omitted blocks as air, or execute model instructions.
"""
import copy,json

def native_navigation(scene,inventory,navigation):
    actor=scene.get('actor_session')
    if not isinstance(actor,str) or not actor or navigation.get('actor_session')!=actor or inventory.get('actor_session')!=actor:
        raise ValueError('Fresh observation/inventory/navigation actor mismatch')
    keys=('actor_session','profile','ready','reason','position','current_cell','current_center_access','cells','edges')
    result={k:copy.deepcopy(navigation[k]) for k in keys if k in navigation}
    if len(result.get('cells',[]))>405 or len(result.get('edges',[]))>4096:raise ValueError('Native local mesh bound')
    if len(json.dumps(result,allow_nan=False).encode())>32768:raise ValueError('Navigation context byte bound')
    result['limits']='Partial client-known local collision mesh; cells are feet voxels, x/z centers add .5. Edges reference cell indices. No global route, hidden resource, atomic snapshot or safety guarantee. Native skills revalidate.'
    return result

def result_history(history,*,max_bytes=12000):
    if type(max_bytes) is not int or not 512<=max_bytes<=16384:raise ValueError('Bounded result context required')
    result=[]
    for entry in reversed(history[-4:]):
        view={k:copy.deepcopy(entry[k]) for k in ('cycle','note','source','kind','started','ended') if k in entry}
        response=entry.get('response')
        if response:
            view['response']={k:copy.deepcopy(response.get(k)) for k in ('status','program_verified','diagnostics')}
            # Query outputs are already freshly sampled separately; preserve task
            # diagnostics instead of dropping geometry/progress evidence as before.
            view['response']['operations']=[{k:copy.deepcopy(op[k]) for k in ('command','status','reason','evidence') if k in op} for op in response.get('operations',[])]
        if 'chat' in entry:view['chat']=copy.deepcopy(entry['chat'])
        if len(json.dumps([view]+result,allow_nan=False).encode())>max_bytes:break
        result.insert(0,view)
    return {'entries':result,'omitted_older_or_large':len(history)>len(result),'query_outputs_replaced_by_fresh_native_samples':True}

def feedback_counters(history):
    """Report read-only repetition; no automatic replacement action or success."""
    count=0
    for entry in reversed(history):
        ops=entry.get('response',{}).get('operations',[])
        if not ops or any(o.get('command') not in {'core:view.observe','core:inventory.inspect'} for o in ops):break
        count+=1
    return {'consecutive_read_only_frames':count,'read_only_success_is_not_world_progress':True,
            'guidance':'Fresh scene, inventory and local navigation are already supplied. Additional unchanged V0/I0 alone do not resolve reachability. Choose independently from supported actions, a genuinely informative observation, another goal or a stop/feature proposal. Do not invent safe terrain or repeat uncertain receipts.'}
