import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from live_config import read_snapshot, differences
from engine import EngineDocument
from test_core import fixture
from test_engine import SOURCE


class LiveConfigTests(unittest.TestCase):
    def test_snapshot_is_read_only_and_reports_changed_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            game = folder / 'GameUserSettings.ini'
            engine = folder / 'Engine.ini'
            game.write_bytes(fixture())
            initial_engine = EngineDocument(SOURCE).patch({'r.ShadowQuality': '2'})
            engine.write_bytes(initial_engine)
            original = game.read_bytes(), engine.read_bytes()
            before = read_snapshot(game, engine)
            changed = initial_engine.replace(b'r.ShadowQuality=2', b'r.ShadowQuality=0')
            engine.write_bytes(changed)
            after = read_snapshot(game, engine)
            self.assertTrue(any('r.ShadowQuality: 2 → 0' in item for item in differences(before, after)))
            self.assertEqual(game.read_bytes(), original[0])
            self.assertEqual(engine.read_bytes(), changed)

    def test_reports_file_change_without_target_key_change(self):
        before = {'quality': {}, 'engine': {}, 'settings_hash': 'a', 'engine_hash': 'x'}
        after = {'quality': {}, 'engine': {}, 'settings_hash': 'a', 'engine_hash': 'y'}
        self.assertEqual(differences(before, after), ['Engine.ini: файл изменился, значения отслеживаемых параметров прежние'])


if __name__ == '__main__':
    unittest.main()
