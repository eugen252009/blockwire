"""Saved-statistics contracts, not synchronized live Minecraft telemetry."""
import hashlib
import io
import json
from pathlib import Path
import runpy
import tempfile
import unittest
from contextlib import redirect_stdout

from blockwire.statistics import (MAX_BYTES, capture_statistics, load_statistics,
                                 parse_statistics, statistics_report)


def snapshot(custom=None, **categories):
    return parse_statistics(json.dumps({'stats': {'minecraft:custom': custom or {}, **categories}}).encode())


class StatisticsContracts(unittest.TestCase):
    def test_ST01_native_units_and_aggregate_counts(self):
        value = snapshot({'minecraft:deaths': 2, 'minecraft:mob_kills': 7,
                          'minecraft:walk_one_cm': 588, 'minecraft:sprint_one_cm': 69,
                          'minecraft:play_time': 1098, 'minecraft:damage_taken': 50},
                         **{'minecraft:mined': {'minecraft:stone': 3, 'minecraft:oak_log': 2},
                            'minecraft:crafted': {'minecraft:oak_planks': 4}})
        totals = statistics_report(value)['totals']
        self.assertEqual(totals['deaths'], 2)
        self.assertEqual(totals['mob_kills'], 7)
        self.assertEqual(totals['walked_m'], 5.88)
        self.assertEqual(totals['sprinted_m'], .69)
        self.assertEqual(totals['play_time_seconds'], 54.9)
        self.assertEqual(totals['damage_taken_hp'], 5.)
        self.assertEqual(totals['blocks_mined'], 5)
        self.assertEqual(totals['items_crafted'], 4)
        self.assertEqual(totals['player_kills'], 0)

    def test_ST02_saved_deltas_are_not_world_totals_or_live_proof(self):
        before = snapshot({'minecraft:deaths': 2, 'minecraft:mob_kills': 7, 'minecraft:walk_one_cm': 100})
        after = snapshot({'minecraft:deaths': 3, 'minecraft:mob_kills': 9, 'minecraft:walk_one_cm': 350})
        report = statistics_report(after, before)
        self.assertEqual(report['totals']['deaths'], 3)
        self.assertEqual(report['run_delta']['deaths'], 1)
        self.assertEqual(report['run_delta']['mob_kills'], 2)
        self.assertEqual(report['run_delta']['walked_m'], 2.5)
        self.assertEqual(report['freshness'], 'saved_only_not_live_verified')
        self.assertIsNone(statistics_report(after)['run_delta'])

    def test_ST03_same_snapshot_is_explicitly_marked_not_a_live_measurement(self):
        value = snapshot()
        report = statistics_report(value, value)
        self.assertTrue(report['snapshots_identical'])
        self.assertEqual(report['run_delta']['deaths'], 0)
        self.assertIn('unsaved', report['warning'])
        self.assertIn('not_verified_run_identity', report['comparison_scope'])

    def test_ST04_counter_reset_or_other_world_has_no_delta(self):
        report = statistics_report(snapshot({'minecraft:deaths': 0}), snapshot({'minecraft:deaths': 3}))
        self.assertIsNone(report['run_delta'])
        self.assertEqual(report['delta_status'], 'counter_decreased_or_source_changed')
        self.assertIn('deaths', report['decreased_counters'])

    def test_ST05_invalid_counters_documents_and_duplicates_are_rejected(self):
        for value in [-1, True, 1.5, '2', 2**63]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                snapshot({'minecraft:deaths': value})
        for data in [b'{}', b'[]', b'{"stats":[]}', b'{"stats":{"minecraft:custom":[]}}',
                     b'{"stats":{"minecraft:custom":{"minecraft:deaths":NaN}}}',
                     b'{"stats":{},"stats":{}}', b'{"stats":{}}'+b' '*(MAX_BYTES+1)]:
            with self.subTest(data=data[:80]), self.assertRaises(ValueError):
                parse_statistics(data)
        with self.assertRaises(ValueError):
            snapshot(**{'minecraft:mined': {'minecraft:stone': -1}})

    def test_ST06_explicit_file_is_read_only_and_absence_is_not_zero_deaths(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'selected-statistics.json'
            data = b'{"stats":{"minecraft:custom":{"minecraft:deaths":2}}}'
            path.write_bytes(data)
            value = load_statistics(path)
            self.assertEqual(value.content_sha256, hashlib.sha256(data).hexdigest())
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual(value.saved_mtime_ns, path.stat().st_mtime_ns)
            value, report = capture_statistics(Path(folder)/'absent.json')
            self.assertIsNone(value)
            self.assertEqual(report['status'], 'unavailable')
            self.assertIsNone(report['totals'])
            self.assertIsNone(report['run_delta'])
        self.assertEqual(capture_statistics(None)[1]['status'], 'not_configured')

    def test_ST07_offline_cli_reports_only_selected_stats_without_bridge(self):
        entry = runpy.run_path(str(Path(__file__).resolve().parents[2]/'examples/report_statistics.py'))['main']
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'stats.json'
            path.write_text('{"stats":{"minecraft:custom":{"minecraft:mob_kills":4}}}')
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(entry([str(path)]), 0)
            report = json.loads(output.getvalue())
            self.assertEqual(report['totals']['mob_kills'], 4)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(entry([str(path), '--before', str(path.parent/'missing.json')]), 2)


if __name__ == '__main__':
    unittest.main()
