"""Regenerate ONLY versioned deterministic test data; never connects to Minecraft."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from building.reference import House
from building.program import fixture_program,frames
from blockwire.bcl import default_commands
root=Path(__file__).resolve().parents[1]/'tests/building/fixtures'
source=fixture_program();compiled=frames(source,default_commands())
root.mkdir(exist_ok=True)
(root/'reference.json').write_text(json.dumps(House().document(),indent=2)+'\n')
(root/'build.bcl').write_text(source)
print(len(compiled),'frames',sum(len(p.operations) for _,p in compiled),'operations')
