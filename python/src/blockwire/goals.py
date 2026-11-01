"""Declarative acceptance predicates, NOT action plans or progression scripts."""
import re


class InventoryMilestone:
    """Require current possession and/or same-actor observed inventory peaks.

    A peak survives crafting consumption, never an actor-session replacement.
    The runtime supplies fresh native observations, not model assertions.
    """
    def __init__(self, *, inventory=None, inventory_high_water=None):
        self.requirements={}
        for field,rules in [('inventory',inventory),('inventory_high_water',inventory_high_water)]:
            rules={} if rules is None else rules
            if not isinstance(rules,dict) or len(rules)>16:raise ValueError('Bounded inventory predicates required')
            if any(not isinstance(k,str) or len(k)>128 or not re.fullmatch(r'[a-z0-9_.-]+:[a-z0-9_./-]+',k) or
                   type(v) is not int or not 1<=v<=2304 for k,v in rules.items()):
                raise ValueError('Explicit item IDs and positive bounded counts required')
            self.requirements[field]=dict(rules)
        if not any(self.requirements.values()):raise ValueError('At least one acceptance predicate required')
    def describe(self):
        return {'kind':'inventory_milestone','all_of':[{'observation_field':f,'item':item,'minimum':n}
                for f,rules in self.requirements.items() for item,n in rules.items()],
                'semantics':'inventory is current possession; inventory_high_water is a verified same-actor observed peak, retained after crafting consumption. No action order specified.'}
    def __call__(self, observation):
        return all(type(observation.get(f,{}).get(item,0)) is int and observation.get(f,{}).get(item,0)>=n
                   for f,rules in self.requirements.items() for item,n in rules.items())
