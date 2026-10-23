import csv
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core import SafetyError, Store
from engine import EngineDocument, START, END
from experience import verify_record, Deferred
from pvp import quality_profile, renderer_profile, tested_city_profile
from benchmarks import analyze, compare
from test_engine import SOURCE

EXISTING = SOURCE + b'\r\n[SystemSettings]\r\n  r.ShadowQuality = 2 ; keep\r\nr.SSR.Quality=1\r\nr.UnknownGameOption=42\r\n\r\n[WindowsApplication.Accessibility]\r\nStickyKeysHotkey=True\r\n'


class PvpTests(unittest.TestCase):
    def test_three_parameter_experiment_preserves_other_values(self):
        values = tested_city_profile()
        self.assertEqual(values, {'r.ShadowQuality': '0', 'r.ViewDistanceScale': '0.7', 'r.SkeletalMeshLODBias': '1'})
        after = EngineDocument(EXISTING).patch(values, merge=True)
        self.assertEqual(EngineDocument(after).read_settings(values), values)
        self.assertIn(b'r.SSR.Quality=1\r\n', after)
        self.assertIn(b'r.UnknownGameOption=42\r\n', after)

    def test_merge_preserves_unknown_settings_comments_sections_and_crlf(self):
        after = EngineDocument(EXISTING).patch(renderer_profile(), merge=True)
        self.assertTrue(after.startswith(SOURCE))
        self.assertIn(b'  r.ShadowQuality = 0 ; keep\r\n', after)
        self.assertIn(b'r.UnknownGameOption=42\r\n', after)
        self.assertEqual(after.split(b'[WindowsApplication.Accessibility]')[1], EXISTING.split(b'[WindowsApplication.Accessibility]')[1])
        self.assertEqual(after.count(b'[SystemSettings]'), 1)
        self.assertEqual(EngineDocument(after).read_settings(renderer_profile()), renderer_profile())
        self.assertEqual(EngineDocument(after).patch(renderer_profile(), merge=True), after)

    def test_merge_refuses_duplicate_sections_keys_and_foreign_section_overrides(self):
        for source in [EXISTING + b'[SystemSettings]\r\n',
                       EXISTING.replace(b'r.SSR.Quality=1', b'r.SSR.Quality=1\r\nr.ssr.quality=0'),
                       SOURCE + b'r.ShadowQuality=2\r\n']:
            with self.assertRaises(SafetyError):
                EngineDocument(source).patch(renderer_profile(), merge=True)

    def test_merge_updates_existing_managed_block_without_escaping_its_markers(self):
        initial = EngineDocument(SOURCE).patch({'r.ShadowQuality': '2'})
        after = EngineDocument(initial).patch(renderer_profile(), merge=True)
        self.assertEqual(after.count(START.encode()), 1)
        self.assertEqual(after.count(END.encode()), 1)
        self.assertIn('r.Lumen.Reflections.Allow=0', EngineDocument(after).managed)

    @patch('core.ensure_closed')
    def test_merged_write_receipt_and_exact_rollback(self, guard):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'Engine.ini'
            path.write_bytes(EXISTING)
            store = Store(Path(tmp) / 'studio')
            item = store.apply_engine(path, EXISTING, renderer_profile(), 'PvP', merge=True)
            self.assertTrue(verify_record(item)['all_same'])
            store.restore(item['id'], path)
            self.assertEqual(path.read_bytes(), EXISTING)
            receipt = max(store.records(), key=lambda r: r.get('applied_ns', 0))
            self.assertTrue(verify_record(receipt)['all_same'])
            self.assertIsNone(receipt['expected']['r.Lumen.DiffuseIndirect.Allow'])

    def test_quality_and_optional_engine_controls(self):
        self.assertEqual(quality_profile()['sg.MassiveGameQuality'], 0)
        self.assertEqual(quality_profile()['sg.ViewDistanceQuality'], 1)
        self.assertEqual(quality_profile()['sg.EffectsQuality'], 1)
        values = renderer_profile(False, False)
        self.assertNotIn('r.Lumen.DiffuseIndirect.Allow', values)
        self.assertNotIn('t.MaxFPS', values)
        self.assertNotIn('r.Streaming.PoolSize', values)
        self.assertNotIn('r.Fog', values)

    @patch('core.ensure_closed')
    def test_deferred_merge_preserves_existing_custom_keys(self, guard):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'Engine.ini'
            path.write_bytes(EXISTING)
            clock = [0.0]
            pending = Deferred(Store(Path(tmp) / 'studio'), clock=lambda: clock[0])
            pending.arm(path, renderer_profile(), 'PvP', 'engine-merged', True)
            pending.tick(False)
            clock[0] = 8
            self.assertIn('записаны', pending.tick(False))
            self.assertIn(b'r.UnknownGameOption=42', path.read_bytes())
            self.assertEqual(EngineDocument(path.read_bytes()).read_settings(renderer_profile()), renderer_profile())


class BenchmarkTests(unittest.TestCase):
    def make_csv(self, path):
        with path.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.writer(stream)
            writer.writerow(['Application', 'ProcessID', 'SwapChainAddress', 'TimeInMs', 'MsBetweenPresents', 'MsCPUBusy', 'MsGPUBusy'])
            for n in range(3000):
                writer.writerow(['AION2.exe', 10, '0x1', n * 20, 20, 14, 10])
                writer.writerow(['Other.exe', 15, '0x2', n * 20, 5, 1, 1])
            writer.writerow(['AION2.exe', 10, '0x1', 61000, 'NaN', 14, 10])

    def test_csv_selects_game_stream_trims_and_computes_defined_low(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'trace.csv'
            self.make_csv(path)
            result = analyze(path)
            self.assertAlmostEqual(result['average_fps'], 50)
            self.assertAlmostEqual(result['one_percent_low'], 50)
            self.assertEqual(result['p99_ms'], 20)
            self.assertEqual(result['frames_over_50ms'], 0)
            self.assertEqual(result['process_id'], '10')
            self.assertEqual(result['cpu_busy_ms'], 14)
            self.assertEqual(compare(result, result)['average_fps'], 0)

    def test_invalid_and_short_csv_not_treated_as_zero_fps(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'trace.csv'
            path.write_text('Application,FrameTime\nAION2.exe,20\n', encoding='utf-8')
            with self.assertRaises(SafetyError):
                analyze(path)
            self.make_csv(path)
            with self.assertRaises(SafetyError):
                analyze(path, trim_start=70)
