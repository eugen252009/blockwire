"""Benchmark-only SMT-aware allocation and explicit owned-process affinity.

Never moves OS services, other users' tasks, or the caller. Affinity is not an
exclusive CPU reservation: unmodified system tasks can still use these CPUs.
"""
from dataclasses import dataclass
import math
import os
from pathlib import Path
import time


@dataclass(frozen=True)
class CoreAllocation:
    minecraft: tuple[int, ...]
    inference: tuple[int, ...]
    operating_system: tuple[int, ...]
    physical_cores: tuple[tuple[int, int, tuple[int, ...]], ...]


def allocation_6_1_1(document, *, allowed):
    groups = {}
    seen = set()
    for row in document['cpus']:
        online = row.get('online', True)
        if online in (False, 'no', 'false'):
            continue
        cpu, core, socket = (int(row[k]) for k in ('cpu', 'core', 'socket'))
        if cpu < 0 or core < 0 or socket < 0 or cpu in seen:
            raise ValueError('Invalid or duplicate CPU topology')
        seen.add(cpu)
        groups.setdefault((socket, core), []).append(cpu)
    cores = tuple((s, c, tuple(sorted(cpus))) for (s, c), cpus in sorted(groups.items()))
    if len(cores) != 8 or any(len(cpus) != 2 for _, _, cpus in cores):
        raise ValueError('Initial 6+1+1 requires eight complete two-thread physical cores')
    if not seen <= set(allowed):
        raise ValueError('Some SMT siblings are unavailable; do not silently allocate partial cores')
    # Leave the lowest physical core, often servicing interrupts, to the OS.
    os_cpus = cores[0][2]
    llm_cpus = cores[-1][2]
    mc = tuple(sorted(cpu for _, _, cpus in cores[1:-1] for cpu in cpus))
    return CoreAllocation(mc, llm_cpus, os_cpus, cores)


def nearest_rank(values, fraction):
    if not values or not 0 < fraction <= 1:
        raise ValueError('Nonempty samples and a bounded quantile required')
    return sorted(values)[math.ceil(fraction * len(values)) - 1]


def cpu_utilization(before, after):
    """Per-logical-CPU host utilization; guest counters are already in user/nice."""
    result = {}
    for cpu in before.keys() & after.keys():
        a, b = before[cpu][:8], after[cpu][:8]
        total = sum(b) - sum(a)
        idle = b[3] + b[4] - a[3] - a[4]
        if total <= 0 or not 0 <= idle <= total:
            raise ValueError('Invalid/nonadvancing CPU counters')
        result[cpu] = 1 - idle / total
    return result


def _identity(pid):
    if type(pid) is not int or pid <= 1 or pid == os.getpid():
        raise ValueError('Explicit non-caller owned process required')
    p = Path('/proc') / str(pid)
    return p.stat().st_uid, (p / 'cwd').resolve(strict=True), (p / 'stat').read_text().rsplit(')', 1)[1].split()[19]


def _require_owner(pid, *, expected_cwd, expected_start_time):
    actual = _identity(pid)
    if actual != (os.getuid(), Path(expected_cwd).resolve(), str(expected_start_time)):
        raise RuntimeError('Owned process identity changed; no affinity action authorized')


def affinity_snapshot(pid, *, expected_cwd, expected_start_time):
    _require_owner(pid, expected_cwd=expected_cwd, expected_start_time=expected_start_time)
    result = {}
    for task in (Path('/proc') / str(pid) / 'task').iterdir():
        try:
            result[int(task.name)] = tuple(sorted(os.sched_getaffinity(int(task.name))))
        except ProcessLookupError:
            continue
    _require_owner(pid, expected_cwd=expected_cwd, expected_start_time=expected_start_time)
    if not result:
        raise RuntimeError('No live owned threads to verify')
    return result


def pin_owned_process(pid, cpus, *, expected_cwd, expected_start_time, timeout=5.):
    cpus = frozenset(cpus)
    if not cpus or any(type(cpu) is not int or cpu < 0 for cpu in cpus) or not .01 <= timeout <= 10:
        raise ValueError('Explicit nonempty CPU set and bounded timeout required')
    proof = dict(expected_cwd=expected_cwd, expected_start_time=expected_start_time)
    _require_owner(pid, **proof)  # Must precede every affinity syscall.
    deadline = time.monotonic() + timeout
    stable = 0
    while time.monotonic() < deadline:
        _require_owner(pid, **proof)
        for task in (Path('/proc') / str(pid) / 'task').iterdir():
            tid = int(task.name)
            try:
                # Refuse a task identity not belonging to this exact process.
                status = (task / 'status').read_text()
                tgid = int(next(x for x in status.splitlines() if x.startswith('Tgid:')).split()[1])
                if tgid != pid:
                    raise RuntimeError('Thread no longer belongs to owned process')
                os.sched_setaffinity(tid, cpus)
            except (ProcessLookupError, FileNotFoundError):
                continue
        snapshot = affinity_snapshot(pid, **proof)
        stable = stable + 1 if all(set(mask) == cpus for mask in snapshot.values()) else 0
        if stable >= 2:
            return snapshot
        time.sleep(.01)
    raise RuntimeError('Could not establish stable affinity on every owned thread')
