import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core import SafetyError
from updater import REPO, validate_release, version_tuple, expected_hash, check_and_download, installed_folder, launch_installer_after_exit


def release(payload=b'test installer'):
    name = 'AION2-Graphics-Studio-0.4.0-Setup.exe'
    checksum = hashlib.sha256(payload).hexdigest() + '  ' + name + '\n'
    prefix = f'https://github.com/{REPO}/releases/download/v0.4.0/'
    return {'tag_name': 'v0.4.0', 'draft': False, 'prerelease': False, 'assets': [
        {'name': name, 'size': len(payload), 'browser_download_url': prefix + name},
        {'name': 'SHA256SUMS.txt', 'size': len(checksum), 'browser_download_url': prefix + 'SHA256SUMS.txt'}]}, checksum


class UpdaterTests(unittest.TestCase):
    def test_semantic_version_comparison(self):
        self.assertGreater(version_tuple('v0.10.0'), version_tuple('0.9.9'))
        data, _ = release()
        self.assertIsNone(validate_release(data, '0.4.0'))
        self.assertIsNone(validate_release(data, '0.5.0'))
        with self.assertRaises(SafetyError):
            version_tuple('v0.4.0-beta')

    def test_reject_foreign_urls_prereleases_and_ambiguous_assets(self):
        for mutation in ['url', 'draft', 'prerelease', 'duplicate', 'size']:
            data, _ = release()
            if mutation == 'url':
                data['assets'][0]['browser_download_url'] = 'https://example.com/setup.exe'
            elif mutation in ['draft', 'prerelease']:
                data[mutation] = True
            elif mutation == 'duplicate':
                data['assets'].append(data['assets'][0].copy())
            else:
                data['assets'][0]['size'] = 151 * 1024 * 1024
            with self.assertRaises(SafetyError):
                validate_release(data)

    def test_checksum_must_match_exact_filename_once(self):
        data, checksum = release()
        name = data['assets'][0]['name']
        self.assertEqual(expected_hash(checksum.encode(), name), hashlib.sha256(b'test installer').hexdigest())
        for content in [checksum + checksum, checksum.replace(name, '../' + name), 'invalid']:
            with self.assertRaises(SafetyError):
                expected_hash(content.encode(), name)

    def test_download_checks_integrity_and_atomically_publishes(self):
        payload = b'test installer'
        data, checksum = release(payload)
        with tempfile.TemporaryDirectory() as tmp:
            with patch('updater.open_url', side_effect=[io.BytesIO(json.dumps(data).encode()), io.BytesIO(checksum.encode()), io.BytesIO(payload)]):
                result = check_and_download(Path(tmp), '0.3.0')
            self.assertEqual(Path(result['path']).read_bytes(), payload)
            self.assertFalse(list(Path(tmp).rglob('*.part')))

    def test_tampered_payload_is_never_executable_target(self):
        payload = b'test installer'
        data, checksum = release(payload)
        with tempfile.TemporaryDirectory() as tmp:
            with patch('updater.open_url', side_effect=[io.BytesIO(json.dumps(data).encode()), io.BytesIO(checksum.encode()), io.BytesIO(b'evil installer')]):
                with self.assertRaises(SafetyError):
                    check_and_download(Path(tmp), '0.3.0')
            self.assertFalse(list(Path(tmp).rglob('*.exe')))
            self.assertFalse(list(Path(tmp).rglob('*.part')))

    def test_source_mode_never_installs_over_source_tree(self):
        self.assertIsNone(installed_folder())

    def test_installer_helper_uses_literal_environment_paths_and_checks_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / 'Installed app'
            folder.mkdir()
            target = root / 'updates' / '0.4.0' / 'AION2-Graphics-Studio-0.4.0-Setup.exe'
            target.parent.mkdir(parents=True)
            target.write_bytes(b'test installer')
            update = {'path': str(target), 'version': '0.4.0', 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}
            with patch('updater.installed_folder', return_value=folder), patch('updater.subprocess.Popen') as popen:
                launch_installer_after_exit(root, update, folder)
                args, kwargs = popen.call_args
                self.assertEqual(args[0][0], 'powershell.exe')
                self.assertEqual(kwargs['env']['AION2_UPDATE_FOLDER'], str(folder))
                self.assertNotIn(str(folder), args[0][-1])
                target.write_bytes(b'tampered')
                with self.assertRaises(SafetyError):
                    launch_installer_after_exit(root, update, folder)
                self.assertEqual(popen.call_count, 1)

    def test_disabled_auto_update_timer_does_not_start_download(self):
        from updates_ui import Updates
        from unittest.mock import Mock
        instance = Mock()
        instance.update_enabled = False
        Updates.auto_update_check(instance)
        instance.start_update_check.assert_not_called()
