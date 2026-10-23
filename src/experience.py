"""Captured quality profiles, file verification, one-shot deferred writes and DAT inspection."""
from collections import Counter
from datetime import datetime
import json
import math
from pathlib import Path
import time
import uuid
from core import Document, SafetyError, atomic_write, digest, ensure_closed
from engine import EngineDocument


def device_path(config: Path) -> Path:
    return config.parent.parent.parent / 'PersistentDownloadDir' / 'UserSetting' / 'DeviceSetting_V2.dat'


def stable_read(path: Path, limit=8 * 1024 * 1024):
    before = path.stat()
    if before.st_size > limit:
        raise SafetyError('Размер файла превышает предел безопасного чтения (8 МБ).')
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    after = path.stat()
    if len(data) > limit or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise SafetyError('Файл меняется во время чтения. Повторите после закрытия игры.')
    return data


def inspect_device(path: Path):
    data = stable_read(path)
    known = [(b'PK\x03\x04', 'ZIP'), (b'\x1f\x8b', 'GZIP'), (b'SQLite format 3\0', 'SQLite'),
             (b'GVAS', 'Unreal SaveGame')]
    format_name = next((name for magic, name in known if data.startswith(magic)), 'Неизвестный бинарный формат')
    try:
        text = data.decode('utf-8-sig')
        parsed = json.loads(text)
        if isinstance(parsed, (dict, list)):
            format_name = 'JSON'
    except (UnicodeError, ValueError):
        pass
    counts = Counter(data)
    entropy = -sum(n / len(data) * math.log2(n / len(data)) for n in counts.values()) if data else 0
    return {'size': len(data), 'sha256': digest(data), 'format': format_name,
            'entropy': round(entropy, 3), 'mtime': datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec='seconds')}


class Captures:
    def __init__(self, root):
        self.root = Path(root) / 'captured'
        self.root.mkdir(parents=True, exist_ok=True)

    def records(self):
        result = []
        for path in self.root.glob('*/profile.json'):
            try:
                item = json.loads(path.read_text('utf-8'))
                if item['id'] == path.parent.name:
                    result.append(item)
            except (OSError, ValueError, KeyError):
                continue
        return sorted(result, key=lambda x: x.get('created_ns', 0), reverse=True)

    def capture(self, config, title):
        ensure_closed()
        config = Path(config).resolve(strict=True)
        if config.name != 'GameUserSettings.ini' or not title.strip() or len(title.strip()) > 80:
            raise SafetyError('Укажите название профиля длиной от 1 до 80 символов.')
        paths = [config, config.parent / 'Engine.ini', device_path(config)]
        bundle = {p: stable_read(p) for p in paths if p.is_file()}
        values = Document(bundle[config]).values
        ensure_closed()
        if any(stable_read(p) != data for p, data in bundle.items()):
            raise SafetyError('Конфигурация изменилась во время снимка. Повторите операцию.')
        identity = uuid.uuid4().hex
        folder = self.root / identity
        files = {}
        for path, data in bundle.items():
            atomic_write(folder / path.name, data)
            if digest((folder / path.name).read_bytes()) != digest(data):
                raise SafetyError('Не удалось проверить снимок.')
            files[path.name] = {'sha256': digest(data), 'size': len(data)}
        record = {'id': identity, 'title': title.strip(), 'source': str(config), 'values': values,
                  'files': files, 'created_ns': time.time_ns(),
                  'time': datetime.now().astimezone().isoformat(timespec='seconds')}
        # Manifest is the commit marker: incomplete captures are never listed.
        atomic_write(folder / 'profile.json', json.dumps(record, ensure_ascii=False, indent=2).encode('utf-8'))
        return record

    def load(self, identity):
        if len(identity) != 32 or any(c not in '0123456789abcdef' for c in identity):
            raise SafetyError('Неверный идентификатор профиля.')
        folder = self.root / identity
        item = json.loads((folder / 'profile.json').read_text('utf-8'))
        data = stable_read(folder / 'GameUserSettings.ini')
        if digest(data) != item['files']['GameUserSettings.ini']['sha256']:
            raise SafetyError('Снимок профиля повреждён.')
        # Derive quality from the verified bytes, never trust editable JSON values.
        return Document(data).values.copy()


def verify_record(item):
    path = Path(item['path'])
    raw = stable_read(path)
    expected = item['expected']
    if item['kind'] == 'quality':
        actual = Document(raw).values
    else:
        document = EngineDocument(raw)
        document.patch(expected)  # Reject conflicting overrides outside the managed block.
        actual = dict(line.split('=', 1) for line in document.managed.splitlines()
                      if '=' in line and not line.startswith(';'))
    if item['kind'] == 'engine' and not expected:
        rows = [{'key': 'Блок студии', 'expected': 'Удалён', 'actual': 'Присутствует' if actual else 'Удалён', 'same': not actual}]
    else:
        rows = [{'key': key, 'expected': value, 'actual': actual.get(key),
                 'same': actual.get(key) == value} for key, value in expected.items()]
    return {'path': str(path), 'rows': rows, 'all_same': all(row['same'] for row in rows),
            'file_same': digest(raw) == item['after'], 'time': item['time']}


class Deferred:
    """Memory-only explicit consent, bound path, stable close, single attempt; no startup task."""
    def __init__(self, store, grace=6.0, clock=time.monotonic):
        self.store, self.grace, self.clock = store, grace, clock
        self.job = None
        self.closed_at = None
        self.last_bytes = None
        self.seen_running = False

    def arm(self, path, values, title, kind='quality', running=False):
        if self.job:
            raise SafetyError('Сначала отмените уже отложенное применение.')
        path = Path(path).resolve(strict=True)
        raw = stable_read(path)
        if kind == 'quality' and path.name == 'GameUserSettings.ini':
            Document(raw).patch(values)
        elif kind == 'engine' and path.name.lower() == 'engine.ini':
            EngineDocument(raw).patch(values)
        else:
            raise SafetyError('Неподдерживаемая цель отложенной записи.')
        self.job = {'path': path, 'values': values.copy(), 'title': title, 'kind': kind}
        self.seen_running = running
        self.closed_at = self.last_bytes = None

    def cancel(self):
        self.job = None
        self.closed_at = self.last_bytes = None
        self.seen_running = False

    def tick(self, running):
        if not self.job:
            return None
        if running:
            self.seen_running = True
            self.closed_at = self.last_bytes = None
            return None
        if not self.seen_running:
            return None
        try:
            raw = stable_read(self.job['path'])
            now = self.clock()
            if raw != self.last_bytes or self.closed_at is None:
                self.last_bytes, self.closed_at = raw, now
                return None
            if now - self.closed_at < self.grace:
                return None
            job = self.job
            self.cancel()  # exactly one attempt, even if validation or commit fails
            if job['kind'] == 'quality':
                if Document(raw).values == job['values']:
                    return 'Выбранные настройки уже сохранены в файле. Отложенная задача завершена.'
                self.store.apply(job['path'], raw, job['values'], job['title'] + ' · после выхода')
            else:
                if EngineDocument(raw).patch(job['values']) == raw:
                    return 'Engine.ini уже соответствует отложенным настройкам.'
                self.store.apply_engine(job['path'], raw, job['values'], job['title'] + ' · после выхода')
            return 'Отложенные настройки записаны после закрытия игры. Резервная копия проверена.'
        except Exception:
            self.cancel()
            raise
