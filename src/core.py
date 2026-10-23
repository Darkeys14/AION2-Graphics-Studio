"""Conservative, byte-preserving adapter for locally verified AION 2 INI groups."""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import uuid
import time
from datetime import datetime, timezone

FIELDS = {
    'sg.ViewDistanceQuality': 'Дальность прорисовки',
    'sg.AntiAliasingQuality': 'Сглаживание',
    'sg.ShadowQuality': 'Тени',
    'sg.GlobalIlluminationQuality': 'Глобальное освещение',
    'sg.ReflectionQuality': 'Отражения',
    'sg.PostProcessQuality': 'Постобработка',
    'sg.TextureQuality': 'Текстуры',
    'sg.EffectsQuality': 'Эффекты',
    'sg.FoliageQuality': 'Растительность',
    'sg.ShadingQuality': 'Затенение',
    'sg.CloudQuality': 'Облака',
    'sg.MassiveGameQuality': 'Массовые сражения',
    'sg.ModelQuality': 'Модели',
}
PRESETS = {
    'PvP': dict(zip(FIELDS, [2, 2, 0, 0, 0, 1, 2, 1, 0, 1, 0, 0, 1])),
    'Баланс': dict(zip(FIELDS, [2, 2, 2, 1, 1, 2, 2, 2, 1, 2, 1, 1, 2])),
    'Ультра': dict.fromkeys(FIELDS, 3),
}


class SafetyError(Exception):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.studio-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def processes() -> list[str]:
    """Enumerate process names only. Never open a game process or read its memory."""
    class ENTRY(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
                    ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_size_t),
                    ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
                    ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', wintypes.LONG),
                    ('dwFlags', wintypes.DWORD), ('szExeFile', wintypes.WCHAR * 260)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ENTRY)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ENTRY)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateToolhelp32Snapshot(2, 0)
    if handle == ctypes.c_void_p(-1).value:
        raise SafetyError('Не удалось проверить процессы. Запись заблокирована.')
    try:
        item = ENTRY()
        item.dwSize = ctypes.sizeof(item)
        if not kernel.Process32FirstW(handle, ctypes.byref(item)):
            raise SafetyError('Не удалось получить список процессов.')
        names = []
        while True:
            names.append(item.szExeFile)
            if not kernel.Process32NextW(handle, ctypes.byref(item)):
                if ctypes.get_last_error() != 18:  # ERROR_NO_MORE_FILES
                    raise SafetyError('Проверка процессов прервана. Запись заблокирована.')
                break
        return names
    finally:
        kernel.CloseHandle(handle)


def game_running():
    return any(re.match(r'^aion(?:2)?(?:[-_.].*)?\.exe$', name, re.I) for name in processes())


def ensure_closed():
    if game_running():
        raise SafetyError('Закройте AION 2 перед изменением или откатом настроек.')


def discover(root: Path | None = None) -> list[Path]:
    root = root or Path(os.environ['LOCALAPPDATA']) / 'AION2'
    return sorted(root.glob('Saved*/Config/Windows/GameUserSettings.ini'))


class Document:
    def __init__(self, raw: bytes):
        self.raw = raw
        self.encoding = 'utf-8-sig' if raw.startswith(b'\xef\xbb\xbf') else (
            'utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8')
        try:
            self.text = raw.decode(self.encoding)
        except UnicodeError as exc:
            raise SafetyError('Неизвестная кодировка: изменение запрещено.') from exc
        self.lines = self.text.splitlines(keepends=True)
        self.values, self.locations = {}, {}
        section = ''
        groups = 0
        for idx, line in enumerate(self.lines):
            m = re.match(r'^\s*\[([^\]]+)\]\s*(?:[;#].*)?$', line.strip())
            if m:
                section = m[1]
                groups += section == 'ScalabilityGroups'
            if section != 'ScalabilityGroups':
                continue
            m = re.match(r'^(\s*)(sg\.\w+)(\s*=\s*)([0-9]+)(\s*(?:[;#].*)?)(\r?\n)?$', line)
            if m and m[2] in FIELDS:
                key, val = m[2], int(m[4])
                if key in self.values or not 0 <= val <= 4:
                    raise SafetyError('Неоднозначные или неизвестные значения качества.')
                self.values[key] = val
                self.locations[key] = (idx, m)
        if groups != 1 or set(self.values) != set(FIELDS):
            raise SafetyError('Структура не совпадает с проверенным форматом AION 2. Запись запрещена.')

    def patch(self, values: dict[str, int]) -> bytes:
        if set(values) != set(FIELDS) or any(type(v) is not int or not 0 <= v <= 3 for v in values.values()):
            raise SafetyError('Допустимы только 13 проверенных параметров качества от 0 до 3.')
        lines = self.lines.copy()
        for key, value in values.items():
            idx, m = self.locations[key]
            lines[idx] = ''.join([m[1], m[2], m[3], str(value), m[5] or '', m[6] or ''])
        # Preserve original UTF-16 endianness and BOM.
        encoding = self.encoding
        if encoding == 'utf-16':
            return self.raw[:2] + ''.join(lines).encode('utf-16-le' if self.raw[:2] == b'\xff\xfe' else 'utf-16-be')
        return ''.join(lines).encode(encoding)


class Store:
    def __init__(self, root: Path):
        self.root = root
        self.backups = root / 'backups'
        self.backups.mkdir(parents=True, exist_ok=True)

    def records(self):
        result = []
        for path in sorted(self.backups.glob('*.json'), reverse=True):
            try:
                item = json.loads(path.read_text('utf-8'))
                if item.get('id') == path.stem:
                    result.append(item)
            except (ValueError, OSError):
                continue
        return sorted(result, key=lambda item: item.get('created_ns', 0), reverse=True)

    def snapshot(self, path: Path, before: bytes, after: bytes, label: str):
        identity = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:10]
        item = {'id': identity, 'path': str(path.resolve()), 'before': digest(before),
                'after': digest(after), 'label': label,
                'time': datetime.now().astimezone().isoformat(timespec='seconds'),
                'created_ns': time.time_ns(), 'status': 'snapshot'}
        atomic_write(self.backups / (identity + '.bin'), before)
        if digest((self.backups / (identity + '.bin')).read_bytes()) != item['before']:
            raise SafetyError('Проверка резервной копии не пройдена.')
        atomic_write(self.backups / (identity + '.json'), json.dumps(item, ensure_ascii=False, indent=2).encode('utf-8'))
        return item

    def apply(self, path: Path, expected: bytes, values: dict, label: str):
        ensure_closed()
        path = path.resolve(strict=True)
        if path.name != 'GameUserSettings.ini':
            raise SafetyError('Разрешён только GameUserSettings.ini.')
        before = path.read_bytes()
        if before != expected:
            raise SafetyError('Файл изменился после просмотра. Обновите данные и повторите.')
        after = Document(before).patch(values)
        return self._commit(path, before, after, label)

    def apply_engine(self, path: Path, expected: bytes, values: dict, label: str, merge=False):
        from engine import EngineDocument
        ensure_closed()
        path = path.resolve(strict=True)
        if path.name.lower() != 'engine.ini':
            raise SafetyError('Разрешён только Engine.ini.')
        before = path.read_bytes()
        if before != expected:
            raise SafetyError('Engine.ini изменился после просмотра. Сформируйте изменения повторно.')
        after = EngineDocument(before).patch(values, merge=merge)
        receipt = {'kind': 'engine-merged', 'expected': values.copy()} if merge else None
        return self._commit(path, before, after, label, receipt)

    def _commit(self, path, before, after, label, receipt=None):
        if before == after:
            raise SafetyError('Изменений нет: выбранные значения уже записаны.')
        item = self.snapshot(path, before, after, label)
        ensure_closed()
        if path.read_bytes() != before:
            raise SafetyError('Файл изменился во время операции. Запись отменена.')
        atomic_write(path, after)
        if path.read_bytes() != after:
            raise SafetyError('Проверка записи не пройдена. Резервная копия сохранена.')
        self._receipt(item, path, after, receipt)
        return item

    def _receipt(self, item, path, data, override=None):
        if override:
            expected, kind = override['expected'], override['kind']
        elif path.name.lower() == 'gameusersettings.ini':
            expected = Document(data).values
            kind = 'quality'
        else:
            from engine import EngineDocument
            document = EngineDocument(data)
            expected = dict(line.split('=', 1) for line in document.managed.splitlines()
                            if '=' in line and not line.startswith(';'))
            kind = 'engine'
        item.update(status='applied', expected=expected, kind=kind, applied_ns=time.time_ns())
        try:
            atomic_write(self.backups / (item['id'] + '.json'),
                         json.dumps(item, ensure_ascii=False, indent=2).encode('utf-8'))
        except OSError as exc:
            raise SafetyError('Файл записан, но журнал проверки не сохранён. Резервная копия осталась на диске.') from exc

    def restore(self, identity: str, selected: Path):
        ensure_closed()
        if not re.fullmatch(r'\d{8}T\d{6}-[a-f0-9]{10}', identity):
            raise SafetyError('Неверный идентификатор копии.')
        item = json.loads((self.backups / (identity + '.json')).read_text('utf-8'))
        path = selected.resolve(strict=True)
        if str(path) != item['path']:
            raise SafetyError('Копия относится к другому файлу. Выберите исходную конфигурацию.')
        data = (self.backups / (identity + '.bin')).read_bytes()
        if digest(data) != item['before']:
            raise SafetyError('Копия повреждена. Восстановление запрещено.')
        current = path.read_bytes()
        if digest(current) != item['after']:
            raise SafetyError('После этой копии файл изменялся. Полный откат мог бы стереть новые настройки; операция заблокирована.')
        receipt = self.snapshot(path, current, data, 'Перед откатом')
        ensure_closed()
        if path.read_bytes() != current:
            raise SafetyError('Файл изменился во время отката. Операция отменена.')
        atomic_write(path, data)
        if path.read_bytes() != data:
            raise SafetyError('Не удалось подтвердить восстановление.')
        override = None
        if item.get('kind') == 'engine-merged':
            from engine import EngineDocument
            old = EngineDocument(data).read_settings(item['expected'])
            override = {'kind': 'engine-merged', 'expected': {key: old.get(key) for key in item['expected']}}
        self._receipt(receipt, path, data, override)
