import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core import Store, SafetyError
from engine import EngineDocument, recommend, START, END

SOURCE = b'[Core.System]\r\nPaths=A\r\nPaths=B\r\n\r\n[/Script/Engine.RendererSettings]\r\nr.ngx.dlss.enable=1\r\nr.fidelityfx.fsr.enabled=0\r\n'


class EngineTests(unittest.TestCase):
    def test_managed_block_preserves_base_and_dlss(self):
        result = EngineDocument(SOURCE).patch(recommend({'goal': 'PvP'}))
        self.assertTrue(result.startswith(SOURCE))
        self.assertIn(b'r.ngx.dlss.enable=1\r\n', result)
        self.assertEqual(result.count(START.encode()), 1)
        updated = EngineDocument(result).patch(recommend({'goal': 'Качество'}))
        self.assertEqual(updated.count(START.encode()), 1)
        self.assertEqual(updated.count(END.encode()), 1)
        self.assertIn(b'r.ShadowQuality=5', updated)
        removed = EngineDocument(updated).patch({})
        self.assertNotIn(START.encode(), removed)
        self.assertTrue(removed.startswith(SOURCE))

    def test_conflicts_unknown_commands_and_tampering_rejected(self):
        examples = [SOURCE + b'\r\n[SystemSettings]\r\nr.ShadowQuality=5\r\n',
                    SOURCE + b'\r\n' + START.encode() + b'\r\n',
                    EngineDocument(SOURCE).patch({'r.ShadowQuality': '2'}).replace(b'r.ShadowQuality=2', b'r.Unknown=2')]
        for source in examples:
            with self.assertRaises(SafetyError):
                EngineDocument(source).patch({'r.ShadowQuality': '3'})
        with self.assertRaises(SafetyError):
            EngineDocument(SOURCE).patch({'r.RayTracing': '0'})

    def test_unknown_vram_never_guesses_pool(self):
        values = recommend({'streaming': True, 'vram': 'Не определена'})
        self.assertNotIn('r.Streaming.PoolSize', values)
        self.assertEqual(values['r.Streaming.LimitPoolSizeToVRAM'], '1')
        known = recommend({'streaming': True, 'vram': '8 ГБ'})
        self.assertEqual(known['r.Streaming.PoolSize'], '3072')
        self.assertNotIn('r.ScreenPercentage', known)

    def test_manual_preserve_overrides_goal(self):
        values = recommend({'goal': 'PvP', 'shadows': 'Как в игре', 'motion': 'Как в игре', 'fps': '90'})
        self.assertNotIn('r.ShadowQuality', values)
        self.assertNotIn('r.MotionBlurQuality', values)
        self.assertEqual(values['t.MaxFPS'], '90')

    @patch('core.ensure_closed')
    def test_engine_transaction_and_exact_rollback(self, guard):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'Engine.ini'
            path.write_bytes(SOURCE)
            store = Store(Path(tmp) / 'data')
            record = store.apply_engine(path, SOURCE, recommend({'goal': 'PvP'}), 'Engine')
            store.restore(record['id'], path)
            self.assertEqual(path.read_bytes(), SOURCE)

    @patch('core.ensure_closed')
    def test_backup_failure_prevents_write(self, guard):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'Engine.ini'
            path.write_bytes(SOURCE)
            store = Store(Path(tmp) / 'data')
            with patch.object(store, 'snapshot', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    store.apply_engine(path, SOURCE, recommend({'goal': 'Баланс'}), 'Engine')
            self.assertEqual(path.read_bytes(), SOURCE)
