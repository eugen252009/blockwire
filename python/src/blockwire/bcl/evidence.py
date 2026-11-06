"""Additive bounded harvesting diagnostics, no new command/execution semantics."""
import json
HARVEST_FIELDS=frozenset({'cause','observed_logs','navigation_profile','local_radius',
 'tool_substitution_will_not_fix_geometry','collected','requested','baseline_logs',
 'inventory_logs','mining_targets','last_position','starting_position'})
def diagnostic_evidence(details,existing_keys):
    if not isinstance(details,dict):return {}
    original={k:v for k,v in details.items() if k in existing_keys}
    extra={k:v for k,v in details.items() if k in HARVEST_FIELDS and k not in original}
    try:body=json.dumps(extra,allow_nan=False).encode()
    except (ValueError,TypeError):return {**original,'harvest_diagnostics_omitted':'invalid_native_details'}
    if len(body)>2048:return {**original,'harvest_diagnostics_omitted':'byte_bound'}
    return {**original,**extra}
