import json
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core import Store, PRESETS, Document, SafetyError
from engine import recommend
from experience import Captures, Deferred, device_path, inspect_device, verify_record
from test_core import fixture
from test_engine import SOURCE


class ExperienceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = self.root / 'AION2' / 'Saved_Steam' / 'Config' / 'Windows' / 'GameUserSettings.ini'
        self.config.parent.mkdir(parents=True)
        self.config.write_bytes(fixture())
        self.engine = self.config.parent / 'Engine.ini'
        self.engine.write_bytes(SOURCE)
        self.device = device_path(self.config)
        self.device.parent.mkdir(parents=True)
        self.device.write_bytes(b'\xe1\x52\x81\x6e' * 40)
        self.store = Store(self.root / 'studio')

    def tearDown(self):
        self.temp.cleanup()

    @patch('experience.ensure_closed')
    def test_capture_preserves_all_source_files_and_loads_verified_values(self, guard):
        captures = Captures(self.root / 'studio')
        item = captures.capture(self.config, 'Данжи')
        self.assertEqual(set(item['files']), {'GameUserSettings.ini', 'Engine.ini', 'DeviceSetting_V2.dat'})
        self.assertEqual(self.config.read_bytes(), fixture())
        self.assertEqual(self.device.read_bytes(), b'\xe1\x52\x81\x6e' * 40)
        self.assertEqual(captures.load(item['id']), Document(fixture()).values)
        path = captures.root / item['id'] / 'profile.json'
        record = json.loads(path.read_text('utf-8'))
        record['values'] = PRESETS['PvP']
        path.write_text(json.dumps(record), encoding='utf-8')
        self.assertEqual(captures.load(item['id']), Document(fixture()).values)
        (path.parent / 'GameUserSettings.ini').write_bytes(b'broken')
        with self.assertRaises(SafetyError):
            captures.load(item['id'])

    @patch('experience.ensure_closed', side_effect=SafetyError('running'))
    def test_capture_blocks_running_game(self, guard):
        with self.assertRaises(SafetyError):
            Captures(self.root / 'studio').capture(self.config, 'Test')

    @patch('core.ensure_closed')
    def test_verification_distinguishes_quality_and_unrelated_changes(self, guard):
        item = self.store.apply(self.config, fixture(), PRESETS['PvP'], 'PvP')
        self.assertTrue(verify_record(item)['all_same'])
        data = self.config.read_bytes()
        self.config.write_bytes(data + b'; unrelated change\r\n')
        report = verify_record(item)
        self.assertTrue(report['all_same'])
        self.assertFalse(report['file_same'])
        self.config.write_bytes(self.config.read_bytes().replace(b'sg.ShadowQuality = 0', b'sg.ShadowQuality = 2'))
        self.assertFalse(verify_record(item)['all_same'])
        self.assertEqual(item['status'], 'applied')

    @patch('core.ensure_closed')
    def test_verification_engine_and_restore_receipt(self, guard):
        item = self.store.apply_engine(self.engine, SOURCE, recommend({'goal': 'PvP'}), 'Engine')
        self.assertTrue(verify_record(item)['all_same'])
        self.store.restore(item['id'], self.engine)
        newest = max(self.store.records(), key=lambda r: r.get('applied_ns', 0))
        self.assertTrue(verify_record(newest)['all_same'])
        self.assertEqual(newest['expected'], {})

    @patch('core.ensure_closed')
    def test_deferred_waits_for_exit_stability_restarts_timer_and_preserves_new_lines(self, guard):
        now = [0.0]
        pending = Deferred(self.store, clock=lambda: now[0])
        pending.arm(self.config, PRESETS['PvP'], 'PvP', running=True)
        pending.tick(True)
        self.assertEqual(self.config.read_bytes(), fixture())
        pending.tick(False)
        now[0] = 5
        pending.tick(False)
        self.assertIsNotNone(pending.job)
        self.config.write_bytes(fixture() + b'; saved on game exit\r\n')
        pending.tick(False)
        now[0] = 10
        pending.tick(False)
        self.assertIsNotNone(pending.job)
        pending.tick(True)
        now[0] = 20
        pending.tick(False)
        now[0] = 27
        result = pending.tick(False)
        self.assertIn('записаны', result)
        self.assertIsNone(pending.job)
        self.assertIn(b'; saved on game exit', self.config.read_bytes())
        self.assertEqual(Document(self.config.read_bytes()).values, PRESETS['PvP'])
        pending.tick(False)
        self.assertEqual(len(self.store.records()), 1)

    @patch('core.ensure_closed')
    def test_deferred_cancel_and_error_are_one_shot(self, guard):
        now = [0.0]
        pending = Deferred(self.store, clock=lambda: now[0])
        pending.arm(self.config, PRESETS['PvP'], 'PvP', running=True)
        pending.cancel()
        self.assertIsNone(pending.tick(False))
        pending.arm(self.config, PRESETS['PvP'], 'PvP', running=True)
        pending.tick(False)
        now[0] = 8
        with patch.object(self.store, 'apply', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                pending.tick(False)
        self.assertIsNone(pending.job)
        self.assertEqual(self.config.read_bytes(), fixture())

    @patch('core.ensure_closed')
    def test_deferred_engine_conflict_never_overwrites_foreign_settings(self, guard):
        now = [0.0]
        pending = Deferred(self.store, clock=lambda: now[0])
        pending.arm(self.engine, recommend({'goal': 'PvP'}), 'Engine', 'engine', True)
        conflicting = SOURCE + b'\r\n[SystemSettings]\r\nr.ShadowQuality=5\r\n'
        self.engine.write_bytes(conflicting)
        pending.tick(False)
        now[0] = 8
        with self.assertRaises(SafetyError):
            pending.tick(False)
        self.assertIsNone(pending.job)
        self.assertEqual(self.engine.read_bytes(), conflicting)

    def test_deferred_requires_observed_game_session(self):
        pending = Deferred(self.store, clock=lambda: 100)
        pending.arm(self.config, PRESETS['PvP'], 'PvP', running=False)
        pending.tick(False)
        pending.tick(False)
        self.assertIsNotNone(pending.job)
        self.assertEqual(self.config.read_bytes(), fixture())

    def test_device_analysis_is_read_only_and_does_not_guess_cipher(self):
        before = self.device.read_bytes()
        result = inspect_device(self.device)
        self.assertEqual(result['size'], len(before))
        self.assertEqual(result['format'], 'Неизвестный бинарный формат')
        self.assertEqual(self.device.read_bytes(), before)
        self.assertNotIn('content', result)

    def test_device_size_limit(self):
        with self.device.open('wb') as stream:
            stream.truncate(8 * 1024 * 1024 + 1)
        with self.assertRaises(SafetyError):
            inspect_device(self.device)
