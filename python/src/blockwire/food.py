"""Shared consumption contract for exclusive skills and the async input mixer."""
FOOD = frozenset('minecraft:'+name for name in (
    'bread', 'apple', 'baked_potato', 'cooked_beef', 'cooked_porkchop',
    'cooked_chicken', 'cooked_mutton', 'cooked_rabbit', 'cooked_cod', 'cooked_salmon'))


def consumption_observed(initial_hunger, hunger, before_count, after_count):
    return hunger > initial_hunger and after_count < before_count
