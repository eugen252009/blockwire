#!/usr/bin/env python3
"""Qualification goal DATA, not a progression script.

Create a fresh Survival world yourself (no bonus chest/resources/commands), pause
it, then explicitly select a trusted external JSON model command. No gameplay
steps, search coordinates or recipe order are prescribed here. See
`docs/autonomous-survival.md`. Host commands are NOT sandboxed.
"""
import argparse
import json
import os
from pathlib import Path
import signal
from blockwire import Bridge,Player
from blockwire.agent import AgentRuntime,SessionStore
from blockwire.command_decider import CommandJSONDecider
from blockwire.goals import InventoryMilestone

OBJECTIVE='Beschaffe aus eigener Kraft mindestens 16 Bruchstein und stelle eine Steinspitzhacke her.'

def acceptance():
    return InventoryMilestone(inventory={'minecraft:stone_pickaxe':1},inventory_high_water={'minecraft:cobblestone':16})

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--describe',action='store_true',help='Offline goal/acceptance description')
    parser.add_argument('--model-argv-file',type=Path,help='Explicit trusted executable argv JSON array; stdin/stdout JSON, no shell')
    parser.add_argument('--confirm-fresh-survival-world',action='store_true')
    parser.add_argument('--resume-paused',action='store_true',help='Operator authorization to resume the initial paused test fixture')
    parser.add_argument('--agent-id');parser.add_argument('--world-id');parser.add_argument('--player-uuid')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--duration',type=float,default=1800.)
    parser.add_argument('--decisions',type=int,default=50)
    parser.add_argument('--failures',type=int,default=12)
    args=parser.parse_args(argv)
    if args.describe:
        print(json.dumps({'objective':OBJECTIVE,'completion_contract':acceptance().describe(),
            'start':'Operator-verified fresh Survival world; native inventory observed empty; no resources supplied.',
            'strategy':'External LLM chooses all progression; no action sequence in this example.',
            'trust':'Selected model command executes trusted host code, NOT a sandbox.'},indent=2));return 0
    if not all((args.model_argv_file,args.output,args.agent_id,args.world_id,args.player_uuid,args.confirm_fresh_survival_world)):
        parser.error('Explicit model argv, NEW output directory, identities and fresh-world confirmation required')
    command=json.loads(args.model_argv_file.read_text())
    if not isinstance(command,list) or not command or any(not isinstance(s,str) for s in command):
        parser.error('Model argv must be a nonempty JSON array of strings, NOT shell code')
    # Validate budgets/provider before connecting or changing the initial fixture UI.
    model=CommandJSONDecider(command,timeout=150.)
    if not 1<=args.duration<=1800 or not 1<=args.decisions<=100 or not 1<=args.failures<=100:
        parser.error('Bounded duration (1..1800), decisions/failures (1..100) required')
    os.umask(0o077);args.output.mkdir(mode=0o700,parents=True,exist_ok=False)
    model=CommandJSONDecider(command,timeout=150.,audit_directory=args.output/'model')
    def record(name,data):
        (args.output/name).write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
    with Bridge.from_env() as bridge:
        p=Player(bridge);s=p.observe();inventory=p.inventory();after=p.observe();menu=p.menu()
        if s.get('player_uuid')!=args.player_uuid or after.get('actor_session')!=s.get('actor_session') or not s.get('alive'):
            raise ValueError('Initial actor identity not verified; no gameplay mutation attempted')
        if inventory.get('actor_session')!=s['actor_session'] or inventory.get('items') or not inventory.get('carried',{}).get('empty'):
            raise ValueError('Fresh empty inventory/cursor not observed')
        record('initial.json',{'scene':s,'inventory':inventory,'menu':menu,'world_properties':'operator confirmed Survival/fresh/no supplied resources'})
        if menu.get('type')=='PauseScreen':
            if not args.resume_paused:raise ValueError('Paused fixture: explicit --resume-paused required')
            w=next(w for w in menu['widgets'] if w['label']=='Back to Game' and w['active'])
            p.click_widget(menu['screen_id'],w['widget_id'])
        elif menu.get('screen_open'):raise ValueError('Unexpected initial GUI; no blind dismissal')
        store=SessionStore(args.output/'session.sqlite',{'agent_id':args.agent_id,'world_id':args.world_id,'player_id':args.player_uuid})
        runtime=AgentRuntime(p,model,store,OBJECTIVE,duration_seconds=args.duration,decision_timeout_seconds=180.,
            action_timeout_seconds=90.,max_decisions=args.decisions,max_failures=args.failures,completion_check=acceptance())
        old=signal.signal(signal.SIGINT,lambda *_:runtime.cancel())
        try:result=runtime.run()
        finally:signal.signal(signal.SIGINT,old)
        record('result.json',result)
        if not runtime.transport_lost:
            record('final.json',{'scene':p.observe(),'inventory':p.inventory()})
        print(json.dumps({k:result.get(k) for k in ('status','reason','objective_verified','cleanup')}))
        return 0 if result.get('objective_verified') else 1

if __name__=='__main__':raise SystemExit(main())
