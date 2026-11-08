"""CPU benchmark contracts, not simulated multi-client Minecraft acceptance."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests'))
from building.cpu_allocation import allocation_6_1_1, cpu_utilization, nearest_rank, pin_owned_process, affinity_snapshot


class CpuAllocationContracts(unittest.TestCase):
    def topology(self):
        return {'cpus': [{'cpu': cpu, 'core': cpu % 8, 'socket': 0, 'online': True} for cpu in range(16)]}

    def test_CA01_complete_smt_pairs_and_os_core_are_preserved(self):
        a = allocation_6_1_1(self.topology(), allowed=range(16))
        self.assertEqual(a.minecraft, (1, 2, 3, 4, 5, 6, 9, 10, 11, 12, 13, 14))
        self.assertEqual(a.inference, (7, 15))
        self.assertEqual(a.operating_system, (0, 8))
        self.assertFalse(set(a.minecraft) & set(a.inference))
        self.assertEqual(set(a.minecraft + a.inference + a.operating_system), set(range(16)))

    def test_CA02_topology_not_cpu_number_assumptions(self):
        d = self.topology()
        for row in d['cpus']:
            row['cpu'] = 31 - row['cpu']
        a = allocation_6_1_1(d, allowed=range(16, 32))
        self.assertEqual(a.operating_system, (23, 31))
        self.assertEqual(a.inference, (16, 24))
        self.assertEqual(len(a.minecraft), 12)

    def test_CA03_partial_offline_duplicate_or_unavailable_cores_reject(self):
        cases = []
        d = self.topology(); d['cpus'][8]['online'] = False; cases.append(d)
        d = self.topology(); d['cpus'].append(d['cpus'][0].copy()); cases.append(d)
        d = self.topology(); d['cpus'].pop(); cases.append(d)
        for d in cases:
            with self.assertRaises(ValueError):
                allocation_6_1_1(d, allowed=range(16))
        with self.assertRaises(ValueError):
            allocation_6_1_1(self.topology(), allowed=range(15))

    def test_CA04_small_sample_tail_quantiles_do_not_round_down(self):
        self.assertEqual(nearest_rank(list(range(1, 13)), .95), 12)
        self.assertEqual(nearest_rank(list(range(1, 13)), .99), 12)
        self.assertEqual(nearest_rank(list(range(1, 61)), .5), 30)
        for values, q in [([], .95), ([1], 0), ([1], 1.01)]:
            with self.assertRaises(ValueError): nearest_rank(values, q)

    def test_CA05_guest_time_not_double_counted(self):
        a = {0: [0] * 10}
        b = {0: [40, 0, 10, 40, 10, 0, 0, 0, 20, 0]}
        self.assertAlmostEqual(cpu_utilization(a, b)[0], .5)
        with self.assertRaises(ValueError): cpu_utilization(a, a)

    def test_CA06_wrong_identity_and_caller_never_receive_affinity_syscall(self):
        with patch('building.cpu_allocation.os.sched_setaffinity') as changed:
            for pid in [0, 1, True, os.getpid()]:
                with self.assertRaises(ValueError):
                    pin_owned_process(pid, {0}, expected_cwd=Path.cwd(), expected_start_time='0')
            changed.assert_not_called()
        with patch('building.cpu_allocation._identity', return_value=(os.getuid(), Path('/owned'), '42')), \
             patch('building.cpu_allocation.os.sched_setaffinity') as changed:
            with self.assertRaises(RuntimeError):
                pin_owned_process(123, {0}, expected_cwd='/unrelated', expected_start_time='42')
            with self.assertRaises(RuntimeError):
                pin_owned_process(123, {0}, expected_cwd='/owned', expected_start_time='43')
            changed.assert_not_called()

    @unittest.skipUnless(hasattr(os, 'sched_setaffinity'), 'Linux CPU affinity')
    def test_CA07_only_explicit_owned_child_threads_are_pinned(self):
        parent = os.sched_getaffinity(0)
        with tempfile.TemporaryDirectory() as d:
            code = 'import threading,time;threading.Thread(target=lambda:time.sleep(30),daemon=True).start();print("READY",flush=True);time.sleep(30)'
            child = subprocess.Popen([sys.executable, '-c', code], cwd=d, stdout=subprocess.PIPE, text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(), 'READY')
                start = Path(f'/proc/{child.pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
                cpus = {min(parent)}
                before = affinity_snapshot(child.pid, expected_cwd=d, expected_start_time=start)
                self.assertGreaterEqual(len(before), 2)
                pin_owned_process(child.pid, cpus, expected_cwd=d, expected_start_time=start)
                after = affinity_snapshot(child.pid, expected_cwd=d, expected_start_time=start)
                self.assertTrue(all(set(mask) == cpus for mask in after.values()))
                self.assertEqual(os.sched_getaffinity(0), parent)
            finally:
                child.terminate();child.wait(timeout=5);child.stdout.close()
