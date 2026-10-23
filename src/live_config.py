"""Read-only snapshots of AION 2 config files for live observation."""
from pathlib import Path
import hashlib
from core import Document, FIELDS, SafetyError
from engine import EngineDocument

LIVE_ENGINE_KEYS = (
    'r.ShadowQuality', 'r.ViewDistanceScale', 'r.SkeletalMeshLODBias',
    'r.SSR.Quality', 'r.MotionBlurQuality', 'r.Tonemapper.Sharpen', 't.MaxFPS',
)


def read_snapshot(settings_path: Path, engine_path: Path):
    settings_bytes = settings_path.read_bytes()
    engine_bytes = engine_path.read_bytes()
    settings = Document(settings_bytes)
    engine = EngineDocument(engine_bytes)
    return {
        'settings_hash': hashlib.sha256(settings_bytes).hexdigest(),
        'engine_hash': hashlib.sha256(engine_bytes).hexdigest(),
        'quality': {FIELDS[key]: settings.values[key] for key in FIELDS},
        'engine': engine.read_settings(LIVE_ENGINE_KEYS),
    }


def differences(before, after):
    changes = []
    for group, title in [('quality', 'Игра · '), ('engine', 'Engine.ini · ')]:
        old, new = before.get(group, {}), after.get(group, {})
        for key in sorted(set(old) | set(new)):
            if old.get(key) != new.get(key):
                changes.append(f'{title}{key}: {old.get(key, "—")} → {new.get(key, "—")}')
    for key, title in [('settings_hash', 'GameUserSettings.ini'), ('engine_hash', 'Engine.ini')]:
        if before.get(key) != after.get(key) and not any(title in change for change in changes):
            changes.append(f'{title}: файл изменился, значения отслеживаемых параметров прежние')
    return changes
