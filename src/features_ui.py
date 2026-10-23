from pathlib import Path
from collections import deque
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from core import FIELDS, game_running
from experience import Captures, Deferred, device_path, inspect_device, verify_record
from telemetry import sample

PANEL, MUTED, ACCENT = '#111827', '#93a4bf', '#5e75fa'


def text(parent, value, size=13, color=MUTED, bold=False, **kwargs):
    return ctk.CTkLabel(parent, text=value, text_color=color, justify='left',
                        font=ctk.CTkFont(family='Segoe UI', size=size, weight='bold' if bold else 'normal'), **kwargs)


class Features:
    def features_init(self, root):
        self.captures = Captures(root)
        self.deferred = Deferred(self.store)
        self.previous_running = None
        self.verify_due = None
        self.monitor_active = False
        self.monitor_busy = False
        self.monitor_queue = queue.Queue()
        self.monitor_samples = deque(maxlen=60)
        self.monitor_widgets = {}
        self.monitor_error = None
        self.device_report = None
        self.verified_report = []

    def begin_services(self):
        self.after(2000, self.poll_game)
        self.protocol('WM_DELETE_WINDOW', self.close_studio)

    def close_studio(self):
        if self.deferred.job and not messagebox.askyesno('Отложенная задача',
                'Закрыть студию и отменить отложенное применение? Для выполнения студия должна оставаться открытой.', parent=self):
            return
        self.deferred.cancel()
        if self.update_enabled and self.update_ready:
            try:
                self.schedule_ready_update()
            except Exception as exc:
                self.notify('Не удалось запустить обновление: ' + str(exc), True)
                self.update_ready = None
                return
        self.destroy()

    def poll_game(self):
        had_pending = self.deferred.job is not None
        try:
            running = game_running()
            if self.previous_running is True and not running:
                self.verify_due = time.monotonic() + 8
            self.previous_running = running
            result = self.deferred.tick(running)
            if result:
                if self.path:
                    self.load()
                self.notify(result)
                self.verify_due = time.monotonic() + 1
            if self.verify_due is not None and time.monotonic() >= self.verify_due and not running:
                self.verify_due = None
                self.collect_verification()
                if self.page == 'Проверка настроек':
                    self.show(self.page)
                elif self.verified_report:
                    matches = all(item.get('all_same', False) for item in self.verified_report)
                    self.notify('Игра закрыта: записанные параметры сохранились.' if matches else
                                'После выхода есть изменения настроек. Откройте «Проверка настроек».', not matches)
        except Exception as exc:
            # An unknown process state must never count as a closed game.
            if had_pending:
                self.deferred.cancel()
                self.notify('Отложенная запись отменена: ' + str(exc), True)
            self.previous_running = None
        finally:
            if self.winfo_exists():
                self.after(2000, self.poll_game)

    def queue_quality(self, window, path, expected, values, title):
        self.queue_write(window, path, values, title, 'quality')

    def queue_engine(self, window, path, expected, values, remove):
        self.queue_write(window, path, values, 'Engine.ini · удаление блока' if remove else 'Engine.ini · оптимизация', 'engine')

    def queue_write(self, window, path, values, title, kind):
        try:
            self.deferred.arm(path, values, title, kind, running=game_running())
            self.notify('Отложено: «' + title + '». Запись после выхода из игры; оставьте студию открытой.')
        except Exception as exc:
            self.notify(str(exc), True)
        finally:
            window.destroy()

    def cancel_deferred(self):
        self.deferred.cancel()
        self.notify('Отложенное применение отменено.')
        self.show('Проверка настроек')

    def collect_verification(self):
        latest = {}
        for record in self.store.records():
            if record.get('status') != 'applied' or 'expected' not in record:
                continue
            if not self.path or Path(record['path']).parent != self.path.parent:
                continue
            old = latest.get(record['path'])
            if old is None or record['applied_ns'] > old['applied_ns']:
                latest[record['path']] = record
        self.verified_report = []
        for item in latest.values():
            try:
                self.verified_report.append(verify_record(item))
            except Exception as exc:
                self.verified_report.append({'path': item['path'], 'error': str(exc), 'all_same': False})

    def verification_page(self):
        self.collect_verification()
        box = self.panel()
        text(box, 'Сохранила ли игра записанные настройки?', 21, '#edf3ff', True).pack(anchor='w', padx=20, pady=(20, 8))
        text(box, 'Сравниваем значения в файлах с последней успешной записью студии.\nПосле выхода из игры проверка запускается автоматически. Это проверка\nфайлов, а не подтверждение визуального эффекта или работы DLSS.', wraplength=720).pack(anchor='w', padx=20, pady=(0, 18))
        ctk.CTkButton(box, text='Проверить сейчас', command=lambda: self.show('Проверка настроек'), fg_color=ACCENT).pack(anchor='w', padx=20, pady=(0, 20))
        pending = self.panel()
        if self.deferred.job:
            job = self.deferred.job
            text(pending, 'Отложено: ' + job['title'], 16, '#ffbc83', True).pack(anchor='w', padx=20, pady=(17, 8))
            text(pending, 'Ждём закрытия игры и 6 секунд неизменности файла.\nПри повторном запуске игры ожидание начнётся заново.\nСтудия должна оставаться открытой; после её перезапуска задача не возобновляется.').pack(anchor='w', padx=20, pady=(0, 12))
            ctk.CTkButton(pending, text='Отменить отложенную запись', command=self.cancel_deferred,
                          fg_color='#26334c').pack(anchor='w', padx=20, pady=(0, 18))
        else:
            text(pending, 'Отложенных задач нет. Кнопка «После выхода» внизу подготовит профиль\nдля следующего закрытия игры. Можно также отложить Engine.ini на его вкладке.').pack(anchor='w', padx=20, pady=18)
        if not self.verified_report:
            text(self.body, 'Пока нет записей с данными для сравнения.\nПримените настройки в новой версии студии.', wraplength=720).pack(anchor='w', padx=6, pady=18)
        for item in self.verified_report:
            box = self.panel()
            text(box, Path(item['path']).name, 18, '#edf3ff', True).pack(anchor='w', padx=20, pady=(17, 8))
            if 'error' in item:
                text(box, item['error'], color='#ffbc83', wraplength=700).pack(anchor='w', padx=20, pady=(0, 18))
                continue
            title = 'Все контролируемые параметры сохранились' if item['all_same'] else 'Есть отличия от записи студии'
            text(box, title, 14, '#8de0be' if item['all_same'] else '#ffbc83', True).pack(anchor='w', padx=20, pady=8)
            if not item['file_same']:
                text(box, 'Общее содержимое файла изменилось: это может затрагивать и посторонние строки.', wraplength=700).pack(anchor='w', padx=20, pady=8)
            for row in item['rows']:
                key = FIELDS.get(row['key'], row['key'])
                value = row['actual'] if row['actual'] is not None else 'строка отсутствует'
                expected_value = row['expected'] if row['expected'] is not None else 'строка отсутствует'
                text(box, f"{'✓' if row['same'] else '≠'} {key}: ожидалось {expected_value} · сейчас {value}",
                     12, '#93a4bf' if row['same'] else '#ffbc83', wraplength=700).pack(anchor='w', padx=20, pady=4)
            text(box, 'Последняя запись: ' + item['time'], 11).pack(anchor='w', padx=20, pady=(12, 17))

    def captures_page(self):
        box = self.panel()
        text(box, 'Профиль из реальных настроек игры', 21, '#edf3ff', True).pack(anchor='w', padx=20, pady=(20, 8))
        text(box, 'Настройте графику в меню AION 2 и нормально закройте игру.\nСтудия сохранит 13 групп качества и локальные снимки сопутствующих файлов.\nПри выборе профиля применяются только группы качества: Engine.ini и DAT\nсохраняются для сравнения и автоматически не восстанавливаются.', wraplength=720).pack(anchor='w', padx=20, pady=(0, 18))
        self.capture_name = ctk.CTkEntry(box, placeholder_text='Название, например «Мои настройки для данжей»', height=38)
        self.capture_name.pack(fill='x', padx=20, pady=(0, 12))
        ctk.CTkButton(box, text='Сохранить настройки из игры', command=self.capture_now,
                      fg_color=ACCENT, height=38).pack(anchor='w', padx=20, pady=(0, 20))
        for record in self.captures.records():
            box = self.panel()
            text(box, record['title'], 18, '#edf3ff', True).pack(anchor='w', padx=20, pady=(17, 8))
            text(box, record['time'] + '\nСнимки: ' + ', '.join(record['files']), 12, wraplength=700).pack(anchor='w', padx=20, pady=(0, 12))
            ctk.CTkButton(box, text='Подготовить этот профиль', fg_color='#26334c',
                          command=lambda r=record: self.select_capture(r)).pack(anchor='w', padx=20, pady=(0, 17))

    def capture_now(self):
        try:
            if not self.path:
                raise ValueError('Сначала выберите конфигурацию игры.')
            self.captures.capture(self.path, self.capture_name.get())
            self.show('Профили из игры')
            self.notify('Профиль и локальные снимки сохранены. Файлы игры не изменялись.')
        except Exception as exc:
            self.notify(str(exc), True)

    def select_capture(self, record):
        try:
            self.values = self.captures.load(record['id'])
            self.selected = record['title']
            self.show('Ручные настройки')
            self.notify('Профиль из игры подготовлен. Снимки DAT и Engine.ini не восстанавливались.')
        except Exception as exc:
            self.notify(str(exc), True)

    def device_page(self):
        box = self.panel()
        text(box, 'DeviceSetting_V2.dat', 24, '#edf3ff', True).pack(anchor='w', padx=20, pady=(20, 8))
        text(box, 'Локальный файл пользовательских настроек. По наблюдению игрока на Inven,\nего перенос сохраняет игровые настройки и расположение HUD. Официальной\nсхемы формата не найдено. Содержимое не расшифровывается и не редактируется.', wraplength=720).pack(anchor='w', padx=20, pady=(0, 18))
        if not self.path:
            text(box, 'Сначала выберите конфигурацию игры.').pack(anchor='w', padx=20, pady=18)
            return
        path = device_path(self.path)
        text(box, str(path), 11, wraplength=700).pack(anchor='w', padx=20, pady=(0, 14))
        try:
            report = inspect_device(path)
            text(box, f"Размер: {report['size']:,} байт\nРаспознанный формат: {report['format']}\nИзменён: {report['mtime']}\nЭнтропия: {report['entropy']:.3f} бит/байт", wraplength=700).pack(anchor='w', padx=20, pady=(0, 12))
            text(box, 'SHA-256: ' + report['sha256'], 11, wraplength=700).pack(anchor='w', padx=20, pady=(0, 14))
            latest = next((r for r in self.captures.records() if r['source'] == str(self.path.resolve()) and path.name in r['files']), None)
            if latest:
                same = latest['files'][path.name]['sha256'] == report['sha256']
                text(box, 'Совпадает с последним сохранённым снимком' if same else 'Отличается от последнего сохранённого снимка',
                     color='#8de0be' if same else '#ffbc83').pack(anchor='w', padx=20, pady=(0, 14))
            text(box, 'Энтропия и размер не доказывают шифрование или конкретный алгоритм.\nКопии остаются на этом компьютере и не отправляются на GitHub.', 12, wraplength=700).pack(anchor='w', padx=20, pady=(0, 18))
        except Exception as exc:
            text(box, str(exc), color='#ffbc83', wraplength=700).pack(anchor='w', padx=20, pady=14)
        ctk.CTkButton(box, text='Обновить анализ', command=lambda: self.show('Файл настроек DAT'), fg_color=ACCENT).pack(anchor='w', padx=20, pady=(0, 18))
        ctk.CTkButton(box, text='Создать локальный снимок', command=lambda: self.show('Профили из игры'),
                      fg_color='#26334c').pack(anchor='w', padx=20, pady=(0, 18))

    def monitor_page(self):
        box = self.panel()
        text(box, 'Нагрузка без вмешательства в игру', 21, '#edf3ff', True).pack(anchor='w', padx=20, pady=(20, 8))
        text(box, 'Используем счётчики Windows, без оверлея, хуков и чтения памяти игры.\nИнтервал — не чаще 5 секунд. Недоступные показатели не подменяются нулями.\nFPS и время кадра здесь не измеряются.', wraplength=720).pack(anchor='w', padx=20, pady=(0, 18))
        self.monitor_button = ctk.CTkButton(box, text='Остановить наблюдение' if self.monitor_active else 'Начать наблюдение',
                                          command=self.toggle_monitor, fg_color=ACCENT)
        self.monitor_button.pack(anchor='w', padx=20, pady=(0, 18))
        self.monitor_widgets = {}
        for key, title in [('cpu_total', 'Процессор · весь компьютер'), ('cpu_game', 'Процессор · процессы игры'),
                           ('gpu_3d', 'Игра · самый занятый 3D-движок GPU'), ('game_ram', 'ОЗУ · процессы игры'),
                           ('free_ram', 'Свободная ОЗУ Windows'), ('state', 'Состояние')]:
            row = self.panel()
            text(row, title, 13, '#edf3ff').pack(side='left', padx=18, pady=14)
            value = text(row, 'Нет замеров', 14, '#a7b2ff')
            value.pack(side='right', padx=18, pady=14)
            self.monitor_widgets[key] = value
        self.monitor_canvas = tk.Canvas(self.body, height=170, bg=PANEL, highlightthickness=0)
        self.monitor_canvas.pack(fill='x', padx=3, pady=12)
        self.monitor_canvas.bind('<Configure>', lambda event: self.draw_monitor())
        text(self.body, 'История GPU 3D (синий) и CPU компьютера (зелёный), последние 60 замеров.\nПробелы означают отсутствие данных. Замеры не являются бенчмарком.', 12, wraplength=720).pack(anchor='w', padx=6, pady=10)
        self.render_monitor()

    def toggle_monitor(self):
        self.monitor_active = not self.monitor_active
        if self.monitor_active:
            self.monitor_error = None
            self.start_sample()
        self.show('Нагрузка ПК')

    def start_sample(self):
        if not self.monitor_active or self.monitor_busy:
            return
        self.monitor_busy = True
        def worker():
            try:
                self.monitor_queue.put((True, sample()))
            except Exception as exc:
                self.monitor_queue.put((False, str(exc)))
        threading.Thread(target=worker, daemon=True).start()
        self.after(200, self.consume_sample)

    def consume_sample(self):
        try:
            ok, value = self.monitor_queue.get_nowait()
        except queue.Empty:
            self.after(200, self.consume_sample)
            return
        self.monitor_busy = False
        if ok:
            self.monitor_samples.append(value)
            self.monitor_error = None
        else:
            self.monitor_error = value
            self.monitor_samples.append({'time': time.strftime('%H:%M:%S')})
        if self.page == 'Нагрузка ПК':
            self.render_monitor()
        if self.monitor_active:
            self.after(5000, self.start_sample)

    def render_monitor(self):
        if not self.monitor_samples:
            return
        data = self.monitor_samples[-1]
        def pct(key):
            return f"{data[key]:.0f} %" if data.get(key) is not None else 'Недоступно'
        values = {key: pct(key) for key in ['gpu_3d', 'cpu_total', 'cpu_game']}
        values['game_ram'] = f"{float(data['game_ram_bytes'] or 0) / 1024**3:.2f} ГБ" if 'game_ram_bytes' in data else 'Недоступно'
        values['free_ram'] = f"{float(data['free_ram_kb']) / 1024**2:.2f} ГБ" if data.get('free_ram_kb') is not None else 'Недоступно'
        values['state'] = self.monitor_error or (('Игра запущена' if data.get('running') else 'Игра не запущена') + ' · ' + data['time'])
        if not self.monitor_active:
            values['state'] = 'Наблюдение остановлено · ' + data['time']
        for key, value in values.items():
            widget = self.monitor_widgets.get(key)
            if widget and widget.winfo_exists():
                widget.configure(text=value)
        self.draw_monitor()

    def draw_monitor(self):
        canvas = getattr(self, 'monitor_canvas', None)
        if not canvas or not canvas.winfo_exists():
            return
        canvas.delete('all')
        width = max(100, canvas.winfo_width())
        for value in [0, 50, 100]:
            y = 145 - value * 1.2
            canvas.create_line(35, y, width - 10, y, fill='#26334c')
            canvas.create_text(18, y, text=str(value), fill=MUTED, font=('Segoe UI', 9))
        for key, color in [('gpu_3d', '#8396ff'), ('cpu_total', '#79d7c8')]:
            previous = None
            for index, data in enumerate(self.monitor_samples):
                value = data.get(key)
                if value is None:
                    previous = None
                    continue
                point = (35 + index / 59 * (width - 50), 145 - value * 1.2)
                if previous:
                    canvas.create_line(*previous, *point, fill=color, width=2)
                else:
                    canvas.create_oval(point[0] - 2, point[1] - 2, point[0] + 2, point[1] + 2, fill=color, outline='')
                previous = point
