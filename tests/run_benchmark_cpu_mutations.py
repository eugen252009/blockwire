#!/usr/bin/env python3
"""Isolated CPU benchmark guard mutations; no game, services, or working edits."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get('BLOCKWIRE_VERIFICATION_DIR', ROOT / 'build/benchmark-cpu-verification')) / 'mutations'
MUTATIONS = [
    ('physical_not_logical_grouping', 'groups.setdefault((socket, core), []).append(cpu)',
     'groups.setdefault((socket, cpu), []).append(cpu)', 'test_CA01_complete_smt_pairs_and_os_core_are_preserved'),
    ('keep_os_core_distinct', 'os_cpus = cores[0][2]',
     'os_cpus = cores[-1][2]', 'test_CA01_complete_smt_pairs_and_os_core_are_preserved'),
    ('require_all_smt_siblings', 'if not seen <= set(allowed):',
     'if False:', 'test_CA03_partial_offline_duplicate_or_unavailable_cores_reject'),
    ('small_sample_tail_not_rounded_down', 'math.ceil(fraction * len(values))',
     'math.floor(fraction * len(values))', 'test_CA04_small_sample_tail_quantiles_do_not_round_down'),
    ('guest_time_not_double_counted', 'a, b = before[cpu][:8], after[cpu][:8]',
     'a, b = before[cpu][:], after[cpu][:]', 'test_CA05_guest_time_not_double_counted'),
    ('reject_caller_affinity_action', ' or pid == os.getpid()',
     '', 'test_CA06_wrong_identity_and_caller_never_receive_affinity_syscall'),
    ('require_exact_process_authority', 'if actual != (os.getuid(), Path(expected_cwd).resolve(), str(expected_start_time)):',
     'if False:', 'test_CA06_wrong_identity_and_caller_never_receive_affinity_syscall'),
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for name, old, new, test in MUTATIONS:
        with tempfile.TemporaryDirectory(prefix='blockwire-cpu-mutation-') as tmp:
            root = Path(tmp)
            package = root / 'tests/building'
            package.mkdir(parents=True)
            (package / '__init__.py').write_text('')
            source = (ROOT / 'tests/building/cpu_allocation.py').read_text()
            if source.count(old) != 1:
                results.append({'mutation': name, 'status': 'INVALID_ANCHOR'})
                continue
            (package / 'cpu_allocation.py').write_text(source.replace(old, new, 1))
            tests = root / 'python/tests'
            tests.mkdir(parents=True)
            shutil.copy2(ROOT / 'python/tests/test_benchmark_cpu_allocation.py', tests)
            env = {k: v for k, v in os.environ.items() if not k.startswith(('BLOCKWIRE_', 'BLOCK_BRIDGE_'))}
            env.update(PYTHONPATH=str(tests), PYTHONDONTWRITEBYTECODE='1')
            result = subprocess.run([str(ROOT / '.venv/bin/python'), '-m', 'unittest',
                                     'test_benchmark_cpu_allocation.CpuAllocationContracts.' + test],
                                    cwd=root, env=env, capture_output=True, text=True, timeout=20)
            log = result.stdout + result.stderr
            (OUT / (name + '.log')).write_text(log)
            killed = result.returncode != 0 and ('FAIL: ' + test in log or 'ERROR: ' + test in log)
            results.append({'mutation': name, 'status': 'KILLED' if killed else 'SURVIVED' if result.returncode == 0 else 'INVALID_FAILURE'})
    (OUT / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2))
    return int(any(row['status'] != 'KILLED' for row in results))


if __name__ == '__main__':
    raise SystemExit(main())
