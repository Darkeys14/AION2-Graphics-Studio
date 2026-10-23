"""Small documented UE CVar allowlist; actual AION 2 rendering effect is unverified."""
import re
from core import SafetyError

START = '; AION2 GRAPHICS STUDIO START'
END = '; AION2 GRAPHICS STUDIO END'
ALLOWED = {
    'r.Tonemapper.Sharpen': {'0', '0.3', '0.5', '0.8', '1'},
    'r.ShadowQuality': {'0', '2', '3', '5'},
    'r.SSR.Quality': {'0', '1', '2', '3'},
    'r.MotionBlurQuality': {'0', '2', '3', '4'},
    'r.DepthOfFieldQuality': {'0', '1', '2'},
    'r.LensFlareQuality': {'0', '1', '2'},
    'r.Streaming.LimitPoolSizeToVRAM': {'1'},
    'r.Streaming.PoolSize': {'1024', '1536', '2048', '3072', '4096', '6144'},
    't.MaxFPS': {'60', '90', '120', '144', '165', '240'},
    'r.MaxAnisotropy': {'4', '8', '16'},
}


class EngineDocument:
    def __init__(self, raw):
        self.raw = raw
        self.encoding = 'utf-8-sig' if raw.startswith(b'\xef\xbb\xbf') else (
            'utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8')
        try:
            self.text = raw.decode(self.encoding)
        except UnicodeError as exc:
            raise SafetyError('Неизвестная кодировка Engine.ini.') from exc
        if '\x00' in self.text or '[Core.System]' not in self.text:
            raise SafetyError('Engine.ini не похож на проверенный файл конфигурации AION 2.')
        self.newline = '\r\n' if '\r\n' in self.text else '\n'
        self.before = self.text
        self.after = ''
        self.managed = ''
        starts, ends = self.text.count(START), self.text.count(END)
        if starts or ends:
            if starts != 1 or ends != 1 or self.text.index(START) > self.text.index(END):
                raise SafetyError('Повреждены маркеры блока оптимизации. Запись запрещена.')
            lines = self.text.splitlines(keepends=True)
            first = next(i for i, line in enumerate(lines) if line.rstrip('\r\n') == START)
            last = next(i for i, line in enumerate(lines) if line.rstrip('\r\n') == END)
            self.before, self.after = ''.join(lines[:first]), ''.join(lines[last + 1:])
            self.managed = ''.join(lines[first:last + 1])
            seen = set()
            for line in lines[first + 1:last]:
                s = line.strip()
                if s in {'', '[SystemSettings]'}:
                    continue
                key, sep, val = s.partition('=')
                if not sep or key not in ALLOWED or val not in ALLOWED[key] or key in seen:
                    raise SafetyError('В блоке студии есть неизвестные строки. Автозамена запрещена.')
                seen.add(key)

    def patch(self, values):
        if not isinstance(values, dict) or any(k not in ALLOWED or str(v) not in ALLOWED[k] for k, v in values.items()):
            raise SafetyError('Неизвестная команда или значение Engine.ini.')
        outside = self.before + self.after
        for key in values:
            if re.search(r'^\s*' + re.escape(key) + r'\s*=', outside, re.M | re.I):
                raise SafetyError('Конфликт: ' + key + ' уже задан вне блока студии. Исходная настройка сохранена.')
        # Never append a duplicate SystemSettings section: UE supports repeated keys,
        # but different INI readers disagree about duplicate sections.
        if values and re.search(r'^\s*\[SystemSettings\]', outside, re.M | re.I):
            raise SafetyError('В Engine.ini уже есть сторонний [SystemSettings]. Автообъединение отключено для сохранности настроек.')
        if values:
            if self.after.strip():
                raise SafetyError('После блока студии есть другие разделы. Автозамена заблокирована.')
            prefix = self.before
            if prefix and not prefix.endswith(('\n', '\r')):
                prefix += self.newline
            if prefix and not prefix.endswith(self.newline * 2):
                prefix += self.newline
            block = self.newline.join([START, '[SystemSettings]',
                                      *[f'{k}={v}' for k, v in values.items()], END, ''])
            result = prefix + block
        else:
            result = self.before + self.after
        if self.encoding == 'utf-16':
            return self.raw[:2] + result.encode('utf-16-le' if self.raw[:2] == b'\xff\xfe' else 'utf-16-be')
        return result.encode(self.encoding)


def recommend(options):
    values = {}
    goal = options.get('goal', 'Баланс')
    if goal == 'PvP' or options.get('fps_drop'):
        values.update({'r.ShadowQuality': '2', 'r.SSR.Quality': '1', 'r.MotionBlurQuality': '0'})
    elif goal == 'Качество':
        values.update({'r.ShadowQuality': '5', 'r.SSR.Quality': '3', 'r.MaxAnisotropy': '16'})
    else:
        values.update({'r.ShadowQuality': '3', 'r.SSR.Quality': '2', 'r.MaxAnisotropy': '8'})
    if options.get('blurred'):
        values['r.Tonemapper.Sharpen'] = '0.5'
    if options.get('streaming'):
        values['r.Streaming.LimitPoolSizeToVRAM'] = '1'
        pool = {'4 ГБ': '1536', '6 ГБ': '2048', '8 ГБ': '3072', '12 ГБ': '4096', '16 ГБ и больше': '6144'}
        if options.get('vram') in pool:
            values['r.Streaming.PoolSize'] = pool[options['vram']]
    for option, key, mapping in [
        ('sharpness', 'r.Tonemapper.Sharpen', {'Мягко': '0.3', 'Чётко': '0.5', 'Очень чётко': '0.8'}),
        ('shadows', 'r.ShadowQuality', {'Низкие': '2', 'Средние': '3', 'Высокие': '5'}),
        ('reflections', 'r.SSR.Quality', {'Низкие': '1', 'Средние': '2', 'Высокие': '3'}),
        ('motion', 'r.MotionBlurQuality', {'Отключить': '0'}),
        ('dof', 'r.DepthOfFieldQuality', {'Отключить': '0'}),
        ('lens', 'r.LensFlareQuality', {'Отключить': '0'}),
    ]:
        if options.get(option) in mapping:
            values[key] = mapping[options[option]]
        elif option in options and options[option] == 'Как в игре':
            values.pop(key, None)
    fps = options.get('fps', 'Как в игре')
    if fps != 'Как в игре':
        values['t.MaxFPS'] = str(fps)
    return values
