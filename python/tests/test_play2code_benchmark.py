"""Preparation-only human benchmark contract; no Minecraft or recording is executed."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('play2code_benchmark_tool', ROOT/'tools/play2code_benchmark.py')
TOOL = importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(TOOL)


class Play2CodeBenchmarkContracts(unittest.TestCase):
    def test_P2B01_plan_is_pending_and_contains_no_fabricated_baseline(self):
        value = TOOL.plan('H01')
        self.assertEqual(value['status'], 'PENDING_OWNER_MANUAL_BUILD')
        self.assertFalse(value['human_baseline_recorded'])
        self.assertFalse(value['replay_attempted'])
        self.assertEqual(value['objective']['expected_blocks'], 71)
        self.assertEqual(value['fixture']['snapshot_identity'], TOOL.FIXTURE_IDENTITY)
        self.assertNotIn('recording', value)
        self.assertNotIn('generated_program', value)

    def test_P2B02_prepare_writes_only_private_pending_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = TOOL.prepare(Path(directory), 'H02')
            self.assertEqual([p.name for p in path.parent.iterdir()], ['status.json'])
            value = json.loads(path.read_text())
            self.assertEqual(value['status'], 'PENDING_OWNER_MANUAL_BUILD')
            self.assertIn('does not restore/load a world', value['note'])
            if __import__('os').name == 'posix':
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)

    def test_P2B03_invalid_or_reused_run_ids_fail_closed(self):
        for value in ('human-1', 'B01', '../H01'):
            with self.assertRaises(ValueError):TOOL.plan(value)
        with tempfile.TemporaryDirectory() as directory:
            TOOL.prepare(Path(directory), 'H03')
            with self.assertRaises(ValueError):TOOL.prepare(Path(directory), 'H03')


if __name__ == '__main__':unittest.main()
