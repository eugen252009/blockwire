"""Opt-in real-client portability qualification for the frozen relative Test-A fixture."""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time

from blockwire.agent import SessionStore
from blockwire.bcl import compile_bcl, default_commands
from blockwire.bcl.client import BCLClient
from blockwire.bcl.compiler import arguments
from blockwire.bcl.gateway import BCLGateway, server_tls
from blockwire.project_agent import ProjectAgent
from blockwire.projects import ProjectJournal
from blockwire.recipes import item_counts
from .anvil import voxels
from .audit import fixture_audit
from .evidence import write_json
from .fixture import NAME, INVENTORY, close, load, title
from .live import independent_native
from .portable import (
    FIXTURE_PATH, ORIGINS, PORTABLE_SOURCE_SHA256, expected_house, frame_sources,
    house_from_home, resolved_coordinate_rows, source, start_position,
)
from .reference import AIR, House, verify
from .snapshots import capture, restore, validate

os.umask(0o077)

REPL_PIPELINE = 'S0 sync\nS1 relative\nM0 X0 Y0 Z1\nM0 X0 Y0 Z0\n'


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _tree_digest(files):
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _source_files(root, tool_path):
    root = Path(root); result = {}
    paths = list((root / 'python/src/blockwire').rglob('*.py'))
    paths += list((root / 'tests/building').glob('*.py'))
    paths += [FIXTURE_PATH, Path(tool_path)]
    for path in sorted(set(path.resolve() for path in paths)):
        relative = path.relative_to(root.resolve()).as_posix()
        result[relative] = _sha256(path)
    return result


def cohort_dir(args):
    if not args.cohort or not args.cohort.replace('-', '').replace('_', '').isalnum():
        raise ValueError('Simple explicit cohort ID required')
    return Path(args.output) / args.cohort


def freeze(args):
    root = Path(__file__).resolve().parents[2]
    out = cohort_dir(args)
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    baseline = Path(args.baseline_private) / 'baseline'
    baseline_manifest = validate(baseline)
    checks = fixture_audit(baseline)
    installed_jar = Path(args.installed_jar)
    if not installed_jar.is_file():
        raise ValueError('Explicit installed Blockwire JAR required')
    files = _source_files(root, args.tool_path)
    record = {
        'schema': 'blockwire.bcl-portability.freeze.v1',
        'cohort': args.cohort,
        'created_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
        'working_source_files': files,
        'working_source_identity': _tree_digest(files),
        'portable_bcl_path': FIXTURE_PATH.relative_to(root).as_posix(),
        'portable_bcl_sha256': PORTABLE_SOURCE_SHA256,
        'portable_bcl_bytes': len(source().encode()),
        'fixture_snapshot_identity': baseline_manifest['identity'],
        'fixture_checks': checks['checks'],
        'installed_jar_sha256': _sha256(installed_jar),
        'registry_digest': default_commands().describe('S1')['language'] + ':' + hashlib.sha256(
            json.dumps([default_commands().resolve('core', code).describe() for code in sorted(
                code for namespace, code in default_commands()._commands if namespace == 'core')],
                sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        'status': 'FROZEN_BEFORE_NATIVE_RUNS',
    }
    write_json(out / 'source-freeze.json', record)
    return record


def validate_freeze(args):
    root = Path(__file__).resolve().parents[2]
    path = cohort_dir(args) / 'source-freeze.json'
    record = json.loads(path.read_text())
    files = _source_files(root, args.tool_path)
    if (record.get('cohort') != args.cohort
            or record.get('working_source_files') != files
            or record.get('working_source_identity') != _tree_digest(files)
            or record.get('portable_bcl_sha256') != PORTABLE_SOURCE_SHA256
            or _sha256(FIXTURE_PATH) != PORTABLE_SOURCE_SHA256
            or _sha256(args.installed_jar) != record.get('installed_jar_sha256')):
        raise ValueError('Portable qualification source freeze changed; preserve cohort and start a new ID')
    baseline = validate(Path(args.baseline_private) / 'baseline')
    if baseline['identity'] != record.get('fixture_snapshot_identity'):
        raise ValueError('Canonical fixture snapshot changed after source freeze')
    return record


def _run_id(args, suffix):
    value = args.run_id or f'{args.cohort}-{suffix}'
    if not value.replace('-', '').replace('_', '').isalnum():
        raise ValueError('Simple unique run ID required')
    return value


def _translated_start_audit(snapshot, house):
    manifest = validate(snapshot)
    observed = voxels(snapshot, house.workspace() | house.floors())
    checks = {
        'empty_workspace': all(observed.get(position) in AIR for position in house.workspace()),
        'intact_grass_floor': all(observed.get(position) == 'minecraft:grass_block' for position in house.floors()),
    }
    if not all(checks.values()):
        raise ValueError('Translated prepared fixture audit failed')
    return {'snapshot_identity': manifest['identity'], 'checks': checks,
            'verification_source': 'read-only closed prepared start snapshot'}


def _preparation_commands(label):
    house = expected_house(label); start = start_position(label)
    lower = house.point(-16, 0, -16); upper = house.point(16, 12, 16)
    floor_a = house.point(-16, -1, -16); floor_b = house.point(16, -1, 16)
    commands = [
        '/kill @e[type=!minecraft:player]',
        f'/tp @s {start[0]} {start[1]} {start[2]} 0 0',
        f'/fill {lower[0]} {lower[1]} {lower[2]} {upper[0]} {upper[1]} {upper[2]} minecraft:air',
        f'/fill {floor_a[0]} {floor_a[1]} {floor_a[2]} {floor_b[0]} {floor_b[1]} {floor_b[2]} minecraft:grass_block',
        '/clear @s',
    ]
    commands += [f'/give @s {block} {count}' for block, count in INVENTORY.items()]
    return commands


def _prepare_world(player, args, run_dir, label):
    baseline = Path(args.baseline_private) / 'baseline'
    world = Path(args.saves) / NAME
    restored = restore(baseline, world, run_dir / 'previous-closed-world', lambda: title(player))
    loaded = load(player)
    commands = _preparation_commands(label)
    for index, command in enumerate(commands):
        player.command(command)
        time.sleep(0.5 if index == 1 else 0.12)
    expected = start_position(label)
    scene = player.observe(); inventory = player.inventory()
    if max(abs(float(scene['position'][axis]) - expected[axis]) for axis in range(3)) > 0.03:
        close(player); raise ValueError('Administrative preparation did not establish exact translated start')
    if item_counts(inventory) != INVENTORY:
        close(player); raise ValueError('Administrative preparation inventory mismatch')
    if scene.get('dimension') != 'minecraft:overworld' or not scene.get('alive') or not scene.get('on_ground'):
        close(player); raise ValueError('Prepared actor is not safe and grounded')
    write_json(run_dir / 'preparation-private.json', {
        'restored_snapshot_identity': restored['identity'], 'commands': commands,
        'loaded_actor': loaded, 'prepared_scene': scene, 'prepared_inventory': inventory,
    })
    close(player)
    prepared = capture(world, run_dir / 'prepared-start-world', lambda: title(player))
    start_audit = _translated_start_audit(run_dir / 'prepared-start-world', expected_house(label))
    scene = load(player)
    inventory = player.inventory()
    if max(abs(float(scene['position'][axis]) - expected[axis]) for axis in range(3)) > 0.03 or item_counts(inventory) != INVENTORY:
        close(player); raise ValueError('Reloaded translated fixture differs from sealed prepared start')
    write_json(run_dir / 'initial-private.json', {'scene': scene, 'inventory': inventory})
    return scene, prepared, start_audit


def _plan(house, dimension):
    return {'site': list(house.origin), 'dimension': dimension, 'sections': ['walls', 'roof'],
            'blocks': [{'position': list(position), 'block': block,
                        'section': 'roof' if position[1] == house.origin[1] + house.height else 'walls'}
                       for position, block in house.blocks().items()]}


def _goal(house):
    return (f'Deterministically execute the frozen relative Test-A fixture at translated origin {house.origin}; '
            'preserve the clear entrance/interior, full roof, grass floor, no helpers and safe interior finish.')


def _mapping_for_home(home):
    return resolved_coordinate_rows(home)


def _check_home(home, scene, house):
    if home.get('mode') != 'relative' or home.get('status') != 'ready':
        raise ValueError('Runtime did not publish a ready relative home')
    if max(abs(float(home['home_position'][axis]) - float(scene['position'][axis])) for axis in range(3)) > 0.03:
        raise ValueError('Captured home differs from prepared native start')
    if tuple(home['voxel_origin']) != tuple(math.floor(float(value)) for value in home['home_position']):
        raise ValueError('Captured voxel origin does not floor the exact point home')
    if house_from_home(home['home_position']).origin != house.origin:
        raise ValueError('Captured home maps to the wrong translated house origin')


async def _start_gateway(player, args, run_dir, registry):
    token = secrets.token_urlsafe(48)
    gateway = BCLGateway(player, token, run_dir / 'gateway-state', registry=registry)
    server = await gateway.listen('127.0.0.1', 0, server_tls(args.certificate, args.private_key))
    url = f'wss://127.0.0.1:{server.sockets[0].getsockname()[1]}/v1'
    return token, gateway, server, url


async def _stop_gateway(gateway, server):
    server.close(); await server.wait_closed(); await gateway.aclose()
    if gateway.failed:
        raise RuntimeError('Gateway quarantined; no safe snapshot claim')


def _audit_callback(run_dir, records):
    def audit(value):
        index = len(records); records.append(value)
        write_json(run_dir / f'{index:03d}-exchange.json', value)
        print(json.dumps({'exchange': index + 1, 'status': value['response'].get('status')}), flush=True)
    return audit


def _operation_rows(records):
    return [operation for record in records
            for operation in record['response'].get('result', {}).get('operations', [])]


def _original_origin_clear(snapshot, label):
    if label == 'A':
        return True
    original = House(origin=ORIGINS['A'])
    observed = voxels(snapshot, original.workspace() | original.floors())
    return (all(observed.get(position) in AIR for position in original.workspace())
            and all(observed.get(position) == 'minecraft:grass_block' for position in original.floors()))


def _finalize_world(player, args, run_dir, label, scene, native, records, failure, metadata, home, journal_summary):
    world = Path(args.saves) / NAME
    close(player)
    ended = capture(world, run_dir / 'ended-world', lambda: title(player))
    house = expected_house(label)
    observed = voxels(run_dir / 'ended-world', house.workspace() | house.floors())
    verification = verify(house, observed, native=native)
    operations = _operation_rows(records)
    result = {
        'schema': 'blockwire.bcl-portability.run.v1', 'metadata': metadata,
        'failure': failure, 'home': home, 'resolved_coordinates': _mapping_for_home(home['home_position']) if home else [],
        'executed_operations': len(operations),
        'failed_actions': sum(operation.get('status') != 'succeeded' for operation in operations),
        'verified_placement_events': sum(operation.get('status') == 'succeeded' and operation.get('reason') == 'block_placed' for operation in operations),
        'movement_results': [operation for operation in operations if operation.get('command') == 'core:movement.walk'],
        'placement_results': [operation for operation in operations if operation.get('command') == 'core:inventory.place_at'],
        'native': native, 'verification': verification, 'project_summary': journal_summary,
        'prepared_snapshot_identity': metadata['prepared_snapshot_identity'],
        'ended_snapshot_identity': ended['identity'],
        'original_origin_clear': _original_origin_clear(run_dir / 'ended-world', label),
    }
    result['passed'] = bool(not failure and verification['objective_verified']
                            and result['failed_actions'] == 0 and result['original_origin_clear'])
    write_json(run_dir / 'verification.json', verification)
    write_json(run_dir / 'result.json', result)
    return result


async def _run_build(player, args, *, label, mode):
    freeze_record = validate_freeze(args); run_id = _run_id(args, label if mode == 'portable' else mode.upper())
    run_dir = cohort_dir(args) / run_id; run_dir.mkdir(mode=0o700, exist_ok=False)
    (run_dir / 'program.bcl').write_bytes(FIXTURE_PATH.read_bytes())
    write_json(run_dir / 'source-freeze-copy.json', freeze_record)
    scene, prepared, start_audit = _prepare_world(player, args, run_dir, label)
    house = expected_house(label); registry = default_commands(); records = []; failure = None; home = None; native = {}; summary = {}
    metadata = {
        'run_id': run_id, 'cohort': args.cohort, 'mode': mode, 'origin_label': label,
        'origin': list(house.origin), 'start_position': scene['position'], 'minecraft_version': '26.3',
        'language': 'BCL/1', 'portable_bcl_sha256': PORTABLE_SOURCE_SHA256,
        'portable_bcl_bytes': len(source().encode()), 'source_freeze_identity': freeze_record['working_source_identity'],
        'canonical_snapshot_identity': freeze_record['fixture_snapshot_identity'],
        'prepared_snapshot_identity': prepared['identity'], 'prepared_start_audit': start_audit,
        'scope': 'Fresh restored/prepared uninterrupted portability run' if mode == 'portable' else 'Fresh split-home cross-request persistence run',
    }
    token, gateway, server, url = await _start_gateway(player, args, run_dir, registry)
    try:
        identity = {'agent_id': 'bcl-portability', 'world_id': prepared['identity'], 'player_id': scene['player_uuid']}
        with ProjectJournal(run_dir / 'project.sqlite', identity, run_id, _goal(house), policy='blocks_v1') as journal:
            journal.bind(scene); journal.revise(_plan(house, scene['dimension']))
            async with BCLClient(url, token, args.certificate, session_id=run_id,
                                 agent_id=identity['agent_id'], world_id=identity['world_id'],
                                 player_uuid=scene['player_uuid'], actor_session=scene['actor_session'], timeout=150.) as client:
                agent = ProjectAgent(client, journal, None, registry, duration=2700., audit=_audit_callback(run_dir, records))
                agent.deadline = time.monotonic() + 2700.
                parts = frame_sources(split_home=(mode == 'split'))
                if mode == 'split':
                    response = await agent.exchange('S0 sync\nS1 relative')
                    if response.get('status') != 'completed':
                        failure = {'layer': 'execution', 'phase': 'home', 'response': response}
                    else:
                        home = response['coordinate_context']; _check_home(home, scene, house)
                for index, part in enumerate(parts):
                    if failure: break
                    response = await agent.exchange(part, intent=True)
                    if index == 0 and mode == 'portable':
                        home = response.get('coordinate_context'); _check_home(home, scene, house)
                    if response.get('status') != 'completed':
                        failure = {'layer': 'execution', 'frame': index, 'response': response}; break
                    if response.get('coordinate_context') != home:
                        failure = {'layer': 'coordinate_context', 'frame': index, 'reason': 'home_changed'}; break
                    await agent.exchange('V0\nI0')
                if not failure:
                    await agent.exchange('V0\nI0')
                    native = independent_native(player, house, scene['actor_session'])
                summary = journal.summary()
    except BaseException as error:
        failure = {'layer': 'host_or_transport', 'type': type(error).__name__, 'reason': str(error)[:512]}
    finally:
        try:
            await _stop_gateway(gateway, server)
        except Exception as stop_error:
            if failure is None:
                failure = {'layer': 'gateway_cleanup', 'type': type(stop_error).__name__, 'reason': str(stop_error)[:512]}
        if player.menu().get('type') != 'TitleScreen':
            current = player.observe()
            if current.get('actor_session') != scene['actor_session']:
                raise RuntimeError('Actor replaced; refusing to close unrelated world')
    return _finalize_world(player, args, run_dir, label, scene, native, records, failure, metadata, home, summary)


async def run_origin(player, args):
    if args.origin not in ORIGINS:
        raise ValueError('Explicit origin A, B or C required')
    return await _run_build(player, args, label=args.origin, mode='portable')


async def run_split(player, args):
    return await _run_build(player, args, label=args.origin or 'A', mode='split')


async def run_mapping(player, args):
    validate_freeze(args); label = args.origin or 'A'; run_id = _run_id(args, 'MAP')
    run_dir = cohort_dir(args) / run_id; run_dir.mkdir(mode=0o700, exist_ok=False)
    scene, prepared, start_audit = _prepare_world(player, args, run_dir, label)
    registry = default_commands(); token, gateway, server, url = await _start_gateway(player, args, run_dir, registry)
    local = [(-2, 0, 4), (-2, 0, 8), (2, 0, 4)]
    lines = ['S0 sync', 'S1 relative', 'S2 normal', 'S3 stop', 'S4 60', 'I1 minecraft:cobblestone']
    for position in local:
        lines += [f'V2 X{position[0]} Y{position[1]} Z{position[2]}',
                  f'I4 Bminecraft:cobblestone P"[{position[0]},{position[1]},{position[2]}]"']
    probe = '\n'.join(lines); response = None; home = None; failure = None
    try:
        async with BCLClient(url, token, args.certificate, session_id=run_id, agent_id='bcl-portability',
                             world_id=prepared['identity'], player_uuid=scene['player_uuid'],
                             actor_session=scene['actor_session'], timeout=150.) as client:
            response = await client.send(probe, request_id=1)
            if response.get('status') != 'completed': failure = {'reason': 'mapping_execution_failed', 'response': response}
            else:
                home = response['coordinate_context']; _check_home(home, scene, expected_house(label))
    finally:
        try:
            await _stop_gateway(gateway, server)
        except Exception as stop_error:
            if failure is None: failure = {'reason': 'gateway_cleanup_failed', 'type': type(stop_error).__name__}
        finally:
            close(player)
    ended = capture(Path(args.saves) / NAME, run_dir / 'ended-world', lambda: title(player))
    resolved = [tuple(home['voxel_origin'][axis] + position[axis] for axis in range(3)) for position in local] if home else []
    actual = voxels(run_dir / 'ended-world', set(resolved)) if resolved else {}
    passed = bool(not failure and all(actual.get(position) == 'minecraft:cobblestone' for position in resolved))
    result = {'schema': 'blockwire.bcl-portability.mapping.v1', 'run_id': run_id, 'origin_label': label,
              'portable_bcl_sha256': PORTABLE_SOURCE_SHA256, 'prepared_snapshot_identity': prepared['identity'],
              'prepared_start_audit': start_audit, 'home': home, 'local_voxels': [list(value) for value in local],
              'resolved_world_voxels': [list(value) for value in resolved], 'observed_blocks': [actual.get(value) for value in resolved],
              'response': response, 'failure': failure, 'ended_snapshot_identity': ended['identity'], 'passed': passed}
    write_json(run_dir / 'result.json', result); return result


async def run_rehome(player, args):
    validate_freeze(args); label = args.origin or 'A'; run_id = _run_id(args, 'REHOME')
    run_dir = cohort_dir(args) / run_id; run_dir.mkdir(mode=0o700, exist_ok=False)
    scene, prepared, start_audit = _prepare_world(player, args, run_dir, label)
    registry = default_commands(); token, gateway, server, url = await _start_gateway(player, args, run_dir, registry)
    bcl = 'S0 sync\nS1 relative\nM0 X5 Y0 Z0\nS1 relative\nM0 X5 Y0 Z0'; response = None; failure = None
    before = scene; after = None
    try:
        async with BCLClient(url, token, args.certificate, session_id=run_id, agent_id='bcl-portability',
                             world_id=prepared['identity'], player_uuid=scene['player_uuid'],
                             actor_session=scene['actor_session'], timeout=150.) as client:
            response = await client.send(bcl, request_id=1); after = player.observe()
            operations = response.get('result', {}).get('operations', [])
            homes = [row['output']['coordinate_context'] for row in operations if row.get('reason') == 'relative_home_captured']
            if (response.get('status') != 'completed' or len(homes) != 2
                    or max(abs(homes[0]['home_position'][axis] - before['position'][axis]) for axis in range(3)) > .05
                    or abs(homes[1]['home_position'][0] - (homes[0]['home_position'][0] + 5)) > .8
                    or abs(after['position'][0] - (homes[1]['home_position'][0] + 5)) > .8):
                failure = {'reason': 'explicit_rehome_contract_failed'}
    finally:
        try:
            await _stop_gateway(gateway, server)
        except Exception as stop_error:
            if failure is None: failure = {'reason': 'gateway_cleanup_failed', 'type': type(stop_error).__name__}
        finally:
            close(player)
    ended = capture(Path(args.saves) / NAME, run_dir / 'ended-world', lambda: title(player))
    result = {'schema': 'blockwire.bcl-portability.rehome.v1', 'run_id': run_id, 'origin_label': label,
              'prepared_start_audit': start_audit, 'response': response, 'initial_scene': before, 'final_scene': after,
              'failure': failure, 'ended_snapshot_identity': ended['identity'], 'passed': failure is None}
    write_json(run_dir / 'result.json', result); return result


async def run_recovery(player, args):
    validate_freeze(args); label = args.origin or 'A'; run_id = _run_id(args, 'RECOVERY')
    run_dir = cohort_dir(args) / run_id; run_dir.mkdir(mode=0o700, exist_ok=False)
    (run_dir / 'program.bcl').write_bytes(FIXTURE_PATH.read_bytes())
    scene, prepared, start_audit = _prepare_world(player, args, run_dir, label)
    house = expected_house(label); registry = default_commands(); records = []; failure = None; home = None; native = {}; summary = {}
    identity = {'agent_id': 'bcl-portability', 'world_id': prepared['identity'], 'player_id': scene['player_uuid']}
    session_id = run_id; boundary = 8; parts = frame_sources(); lost_request = None; lost_source = parts[boundary]
    token, gateway, server, url = await _start_gateway(player, args, run_dir, registry)
    try:
        with ProjectJournal(run_dir / 'project.sqlite', identity, run_id, _goal(house), policy='blocks_v1') as journal:
            journal.bind(scene); journal.revise(_plan(house, scene['dimension']))
            async with BCLClient(url, token, args.certificate, session_id=session_id, agent_id=identity['agent_id'],
                                 world_id=identity['world_id'], player_uuid=scene['player_uuid'],
                                 actor_session=scene['actor_session'], timeout=150.) as client:
                agent = ProjectAgent(client, journal, None, registry, duration=2700., audit=_audit_callback(run_dir, records)); agent.deadline = time.monotonic() + 2700.
                for index in range(boundary):
                    response = await agent.exchange(parts[index], intent=True)
                    if index == 0:
                        home = response['coordinate_context']; _check_home(home, scene, house)
                    if response.get('status') != 'completed': raise RuntimeError('pre-restart frame failed')
                    await agent.exchange('V0\nI0')
                program = compile_bcl(lost_source, registry); lost_request = client.next_id
                for operation in program.operations:
                    command = registry.resolve(operation.namespace, operation.opcode); values = arguments(operation, command)
                    if command.skill in {'place_block', 'place_at'}:
                        journal.p['counters']['placement_requests'] = journal.p['counters'].get('placement_requests', 0) + 1
                    if command.skill in {'gather_block', 'gather_wood', 'remove_block'}:
                        journal.p['counters']['gather_requests'] = journal.p['counters'].get('gather_requests', 0) + values.get('count', 1)
                    if command.skill == 'craft_item':
                        journal.p['counters']['craft_batches'] = journal.p['counters'].get('craft_batches', 0) + values.get('batches', 1)
                journal.intent(lost_source, lost_request, session_id, len(program.operations))
                lost_response = await client.send(lost_source, request_id=lost_request)
                records.append({'source': lost_source, 'response': lost_response, 'injected_lost_project_ack': True})
                write_json(run_dir / f'{len(records)-1:03d}-exchange.json', records[-1])
                if lost_response.get('status') != 'completed': raise RuntimeError('injected lost-ack frame failed')
                # Deliberately do not call journal.result(): pending intent remains durable.
        await _stop_gateway(gateway, server)

        token, gateway, server, url = await _start_gateway(player, args, run_dir, registry)
        with ProjectJournal(run_dir / 'project.sqlite', identity, run_id, _goal(house), policy='blocks_v1') as journal:
            if not journal.p.get('pending'): raise RuntimeError('lost acknowledgement did not leave durable pending intent')
            journal.bind(player.observe())
            if journal.p.get('pending') is not None: raise RuntimeError('rebind did not quarantine uncertain pending intent')
            async with BCLClient(url, token, args.certificate, session_id=session_id, agent_id=identity['agent_id'],
                                 world_id=identity['world_id'], player_uuid=scene['player_uuid'],
                                 actor_session=scene['actor_session'], timeout=150.) as client:
                if client.coordinate_context != home: raise RuntimeError('persisted home changed across gateway restart')
                before_inventory = item_counts(player.inventory()); before_position = player.observe()['position']
                duplicate = await client.send(lost_source, request_id=lost_request)
                after_inventory = item_counts(player.inventory()); after_position = player.observe()['position']
                write_json(run_dir / 'deduplicated-lost-ack.json', duplicate)
                if (duplicate.get('deduplicated') is not True or before_inventory != after_inventory
                        or max(abs(before_position[axis] - after_position[axis]) for axis in range(3)) > .03):
                    raise RuntimeError('deduplicated lost acknowledgement replayed effects')
                agent = ProjectAgent(client, journal, None, registry, duration=2700., audit=_audit_callback(run_dir, records)); agent.deadline = time.monotonic() + 2700.
                await agent.exchange('V0\nI0')
                for index in range(boundary + 1, len(parts)):
                    response = await agent.exchange(parts[index], intent=True)
                    if response.get('status') != 'completed' or response.get('coordinate_context') != home:
                        raise RuntimeError('post-restart continuation failed')
                    await agent.exchange('V0\nI0')
                await agent.exchange('V0\nI0'); native = independent_native(player, house, scene['actor_session']); summary = journal.summary()
    except BaseException as error:
        failure = {'layer': 'recovery', 'type': type(error).__name__, 'reason': str(error)[:512]}
    finally:
        try: await _stop_gateway(gateway, server)
        except Exception as stop_error:
            if failure is None: failure = {'layer': 'gateway_cleanup', 'type': type(stop_error).__name__, 'reason': str(stop_error)[:512]}
    metadata = {'run_id': run_id, 'cohort': args.cohort, 'mode': 'recovery', 'origin_label': label,
                'origin': list(house.origin), 'start_position': scene['position'], 'portable_bcl_sha256': PORTABLE_SOURCE_SHA256,
                'prepared_snapshot_identity': prepared['identity'], 'prepared_start_audit': start_audit,
                'boundary_frame': boundary, 'lost_request_id': lost_request,
                'scope': 'Separate gateway restart/project reconciliation/lost-ack dedup qualification'}
    return _finalize_world(player, args, run_dir, label, scene, native, records, failure, metadata, home, summary)


async def _subprocess(argv, *, stdin=None, env=None):
    process = await asyncio.create_subprocess_exec(*argv, stdin=asyncio.subprocess.PIPE if stdin is not None else None,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env)
    stdout, stderr = await asyncio.wait_for(process.communicate(stdin.encode() if stdin is not None else None), 300.)
    return {'argv': [str(value) for value in argv], 'returncode': process.returncode,
            'stdout': stdout.decode(errors='replace'), 'stderr': stderr.decode(errors='replace')}


async def run_interfaces(player, args):
    validate_freeze(args); label = args.origin or 'A'; run_id = _run_id(args, 'INTERFACES')
    run_dir = cohort_dir(args) / run_id; run_dir.mkdir(mode=0o700, exist_ok=False)
    scene, prepared, start_audit = _prepare_world(player, args, run_dir, label)
    registry = default_commands(); token, gateway, server, url = await _start_gateway(player, args, run_dir, registry)
    token_path = run_dir / 'gateway.token'; token_path.write_text(token); token_path.chmod(0o600)
    common = ['--url', url, '--certificate', str(args.certificate), '--token-file', str(token_path),
              '--agent-id', 'bcl-portability-cli', '--world-id', prepared['identity'],
              '--player-uuid', scene['player_uuid'], '--actor-session', scene['actor_session'], '--timeout', '150', '--json']
    env = dict(os.environ); records = {}; failure = None
    try:
        first = run_dir / 'cli-home.bcl'; first.write_text('S0 sync\nS1 relative\nM0 X1 Y0 Z0\n')
        second = run_dir / 'cli-return.bcl'; second.write_text('M0 X0 Y0 Z0\n')
        records['run_home'] = await _subprocess([sys.executable, '-m', 'blockwire', 'run', str(first), '--session-id', run_id + '-cli', *common], env=env)
        records['run_return'] = await _subprocess([sys.executable, '-m', 'blockwire', 'run', str(second), '--session-id', run_id + '-cli', *common], env=env)
        legacy = run_dir / 'legacy-status.bcl'; legacy.write_text('S1 status\n')
        records['legacy_alias'] = await _subprocess([str(Path(sys.executable).with_name('blockwire-bcl')), '--file', str(legacy), '--session-id', run_id + '-cli', *common], env=env)
        after_cli = player.observe()
        records['repl'] = await _subprocess([sys.executable, '-m', 'blockwire', 'repl', '--session-id', run_id + '-repl', *common], stdin=REPL_PIPELINE, env=env)
        after_repl = player.observe()
        if (any(value['returncode'] != 0 for value in records.values())
                or max(abs(after_cli['position'][axis] - scene['position'][axis]) for axis in range(3)) > .8
                or max(abs(after_repl['position'][axis] - after_cli['position'][axis]) for axis in range(3)) > .8):
            failure = {'reason': 'native_cli_or_repl_contract_failed'}
        write_json(run_dir / 'interface-private.json', {'records': records, 'after_cli': after_cli, 'after_repl': after_repl})
    finally:
        try:
            await _stop_gateway(gateway, server)
        except Exception as stop_error:
            if failure is None: failure = {'reason': 'gateway_cleanup_failed', 'type': type(stop_error).__name__}
        finally:
            close(player)
    ended = capture(Path(args.saves) / NAME, run_dir / 'ended-world', lambda: title(player))
    result = {'schema': 'blockwire.bcl-portability.interfaces.v1', 'run_id': run_id, 'origin_label': label,
              'prepared_start_audit': start_audit, 'interfaces': {'python_module_run': records.get('run_home', {}).get('returncode') == 0 and records.get('run_return', {}).get('returncode') == 0,
              'legacy_blockwire_bcl': records.get('legacy_alias', {}).get('returncode') == 0,
              'python_module_repl': records.get('repl', {}).get('returncode') == 0},
              'failure': failure, 'ended_snapshot_identity': ended['identity'], 'passed': failure is None}
    write_json(run_dir / 'result.json', result); return result


def finalize(args):
    freeze_record = validate_freeze(args); root = cohort_dir(args)
    names = {label: f'{args.cohort}-{label}' for label in ORIGINS}
    runs = {label: json.loads((root / run_id / 'result.json').read_text()) for label, run_id in names.items()}
    if any(not value.get('passed') for value in runs.values()):
        raise ValueError('All three uninterrupted portability runs must pass before finalization')
    if len({value['metadata']['portable_bcl_sha256'] for value in runs.values()}) != 1:
        raise ValueError('Portable source hash differs across origins')
    requirements = {label: value['verification']['requirements'] for label, value in runs.items()}
    translations = {}
    for left, right in [('A', 'B'), ('A', 'C'), ('B', 'C')]:
        left_rows = sorted(requirements[left], key=lambda row: row['position'])
        right_rows = sorted(requirements[right], key=lambda row: row['position'])
        home_left = runs[left]['home']['voxel_origin']; home_right = runs[right]['home']['voxel_origin']
        delta = [home_right[index] - home_left[index] for index in range(3)]
        valid = all([right_rows[i]['position'][axis] - left_rows[i]['position'][axis] for axis in range(3)] == delta
                    and left_rows[i]['state'] == right_rows[i]['state'] == 'CORRECT' for i in range(71))
        translations[f'{left}_to_{right}'] = {'voxel_home_delta': delta, 'all_71_corresponding_blocks': valid}
    extras = {}
    for suffix in ('MAP', 'SPLIT', 'REHOME', 'RECOVERY', 'INTERFACES'):
        path = root / f'{args.cohort}-{suffix}' / 'result.json'
        extras[suffix.lower()] = json.loads(path.read_text()) if path.exists() else {'passed': False, 'status': 'NOT_RUN'}
    result = {
        'schema': 'blockwire.bcl-portability.cohort.v1', 'cohort': args.cohort,
        'source_freeze_identity': freeze_record['working_source_identity'],
        'portable_bcl_sha256': PORTABLE_SOURCE_SHA256, 'portable_bcl_bytes': len(source().encode()),
        'origins': {label: {'origin': value['metadata']['origin'], 'captured_home': value['home']['home_position'],
                            'voxel_origin': value['home']['voxel_origin'], 'verified_blocks': value['verification']['verified_blocks'],
                            'objective_verified': value['verification']['objective_verified'], 'failed_actions': value['failed_actions'],
                            'original_origin_clear': value['original_origin_clear']} for label, value in runs.items()},
        'translations': translations,
        'mapping': extras['map'].get('passed') is True,
        'cross_request': extras['split'].get('passed') is True,
        'rehome': extras['rehome'].get('passed') is True,
        'recovery': extras['recovery'].get('passed') is True,
        'interfaces': extras['interfaces'].get('passed') is True,
    }
    result['portable_building_go'] = bool(all(value['objective_verified'] and value['verified_blocks'] == 71 for value in result['origins'].values())
                                                  and all(value['all_71_corresponding_blocks'] for value in translations.values()))
    result['passed'] = bool(result['portable_building_go'] and all(result[key] for key in ('mapping', 'cross_request', 'rehome', 'recovery', 'interfaces')))
    write_json(root / 'cohort-result.json', result); return result
