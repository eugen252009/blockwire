#!/usr/bin/env python3
"""Generate BCL reference/autocomplete schema from the actual authoritative registry."""
import json
from pathlib import Path
from blockwire.bcl import default_commands

def main():
    root=Path(__file__).resolve().parents[1];r=default_commands()
    definitions=[r.describe(('' if c.namespace=='core' else c.namespace+':')+c.opcode) for c in r._commands.values()]
    (root/'docs/bcl-commands.json').write_text(json.dumps({'language':'BCL/1','commands':definitions,'events':r.events},indent=2,allow_nan=False)+'\n')
    lines=['# BCL/1 command reference (generated)','','Do not edit manually. Regenerate: `.venv/bin/python tools/generate_bcl_reference.py`.','',
           'Limits and validation come from existing skill schemas. Availability describes an adapter, not current world readiness.','Server-to-client event opcodes are NOT executable client commands. See [normative specification](bcl.md).','']
    for d in definitions:
        lines += ['## '+d['opcode']+' — '+d['command'],'',d['description'],'',
                  '- Signature: `'+d['signature']+'`','- Category/direction: '+d['category']+' / '+d['direction'],
                  '- Available: '+str(d['available']).lower(),'- Existing skill: `'+str(d['skill'])+'`',
                  '- Permissions: '+', '.join(d['permissions']),'- Preconditions: '+', '.join(d['preconditions']),
                  '- Return: '+d['return_type'],'- Errors: '+', '.join(d['errors']),'']
        if 'setting' in d:lines+=['Setting: `'+json.dumps(d['setting'],sort_keys=True)+'`','']
        for p in d['parameters']:
            lines += ['- `'+p['key']+'` → `'+p['name']+'`: '+p['type']+'; '+p['default_kind']+' default `'+json.dumps(p['default'])+'`.',
                      '  Schema: `'+json.dumps(p['schema'],sort_keys=True)+'`']
        lines+=['']
    (root/'docs/bcl-reference.md').write_text('\n'.join(lines)+'\n')
    print(f'Generated {len(definitions)} command definitions and {len(r.events)} event definitions')
if __name__=='__main__':main()
