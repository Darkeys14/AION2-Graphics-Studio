import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core import Document, Store, PRESETS, FIELDS, SafetyError, discover, ensure_closed


def fixture():
    return ('; комментарий\r\n[DefaultScalabilityGroups]\r\nsg.ShadowQuality=2\r\n'
            '[ScalabilityGroups]\r\n' + ''.join(f'{k} = 2 ; keep\r\n' for k in FIELDS) +
            'sg.ResolutionQuality=0\r\n\r\n[Other]\r\nPaths=A\r\nPaths=B\r\nToken=local-only\r\n').encode('utf-8')


class CoreTests(unittest.TestCase):
    def test_patch_preserves_comments_sections_unknown_lines_and_crlf(self):
        source = fixture()
        updated = Document(source).patch(PRESETS['PvP'])
        self.assertIn(b'[DefaultScalabilityGroups]\r\nsg.ShadowQuality=2', updated)
        self.assertIn(b'sg.ResolutionQuality=0\r\n', updated)
        self.assertEqual(updated.split(b'[Other]')[1], source.split(b'[Other]')[1])
        self.assertEqual(Document(updated).values, PRESETS['PvP'])
        self.assertEqual(updated.count(b'; keep'), 13)
        self.assertEqual(updated.count(b'\r\n'), source.count(b'\r\n'))

    def test_encodings(self):
        for enc in ['utf-8-sig', 'utf-16', 'utf-16-be']:
            data = fixture().decode().encode(enc)
            if enc == 'utf-16-be':
                data = b'\xfe\xff' + data
            result = Document(data).patch(dict.fromkeys(FIELDS, 2))
            self.assertEqual(data, result)

    def test_refuses_unknown_or_ambiguous_structure(self):
        for data in [b'[ScalabilityGroups]\nsg.ShadowQuality=2\n',
                     fixture() + b'[ScalabilityGroups]\n',
                     fixture().replace(b'sg.ShadowQuality = 2', b'sg.ShadowQuality = 9'),
                     fixture().replace(b'sg.ShadowQuality = 2', b'sg.ShadowQuality=1\r\nsg.ShadowQuality=2')]:
            with self.assertRaises(SafetyError):
                Document(data)

    def test_cannot_add_arbitrary_settings(self):
        values = PRESETS['PvP'].copy()
        values['r.Unknown'] = 0
        with self.assertRaises(SafetyError):
            Document(fixture()).patch(values)

    @patch('core.ensure_closed')
    def test_apply_and_exact_restore(self, guard):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'GameUserSettings.ini'
            path.write_bytes(fixture())
            store = Store(Path(tmp) / 'data')
            item = store.apply(path, fixture(), PRESETS['PvP'], 'PvP')
            self.assertEqual(Document(path.read_bytes()).values, PRESETS['PvP'])
            store.restore(item['id'], path)
            self.assertEqual(path.read_bytes(), fixture())
            self.assertEqual(len(store.records()), 2)

    @patch('core.ensure_closed')
    def test_conflicting_changes_and_corrupted_backups_are_blocked(self, guard):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'GameUserSettings.ini'
            path.write_bytes(fixture())
            store = Store(Path(tmp) / 'data')
            item = store.apply(path, fixture(), PRESETS['PvP'], 'PvP')
            applied = path.read_bytes()
            changed = applied + b'; new game setting\r\n'
            path.write_bytes(changed)
            with self.assertRaises(SafetyError):
                store.restore(item['id'], path)
            self.assertEqual(path.read_bytes(), changed)
            with self.assertRaises(SafetyError):
                store.apply(path, applied, PRESETS['Баланс'], 'Баланс')
            path.write_bytes(applied)
            (store.backups / (item['id'] + '.bin')).write_bytes(b'corrupt')
            with self.assertRaises(SafetyError):
                store.restore(item['id'], path)
            self.assertEqual(path.read_bytes(), applied)

    @patch('core.processes', return_value=['Aion2-Win64-Shipping.exe'])
    def test_running_game_is_blocked(self, names):
        with self.assertRaises(SafetyError):
            ensure_closed()

    def test_discovery_finds_all_variants(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ['Saved_Steam', 'Saved', 'Saved_KR']:
                path = Path(tmp) / name / 'Config' / 'Windows' / 'GameUserSettings.ini'
                path.parent.mkdir(parents=True)
                path.write_bytes(fixture())
            self.assertEqual(len(discover(Path(tmp))), 3)


if __name__ == '__main__':
    unittest.main()
