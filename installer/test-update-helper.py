"""Runner-only integration harness for the actual post-exit updater helper."""
from pathlib import Path
import hashlib
import shutil
import sys
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from updater import launch_installer_after_exit
from version import VERSION

root, folder, setup = (Path(value).resolve() for value in sys.argv[1:4])
target = root / 'updates' / VERSION / f'AION2-Graphics-Studio-{VERSION}-Setup.exe'
target.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(setup, target)
state = root / 'update-status.json'
if state.exists():
    state.unlink()
update = {'version': VERSION, 'path': str(target), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}
# This harness runs from Python sources; simulate only installed-folder detection.
# The production helper, checksum verification, waiting, installer and restart are real.
with patch('updater.installed_folder', return_value=folder):
    launch_installer_after_exit(root, update, folder)
