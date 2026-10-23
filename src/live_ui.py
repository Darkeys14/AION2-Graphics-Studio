import queue
import threading
import time
from collections import deque
import customtkinter as ctk
from live_config import read_snapshot, differences
from features_ui import text, ACCENT, PANEL


class LiveWatch:
    def live_init(self):
        self.live_active = False
        self.live_busy = False
        self.live_queue = queue.Queue()
        self.live_previous = None
        self.live_events = deque(maxlen=25)

    def live_page(self):
        box = self.panel()
        text(box, 'Наблюдение за настройками во время игры', 21, '#edf3ff', True).pack(anchor='w', padx=20, pady=(20, 8))
        text(box, 'Студия только читает GameUserSettings.ini и Engine.ini. Обновление — раз в 2,5 секунды.\nПоказываются значения в файлах; это не доказывает, что движок уже применил их.\nДля немедленного эффекта меняйте графику в меню самой игры. Запись во время игры отключена.', wraplength=720).pack(anchor='w', padx=20, pady=(0, 16))
        self.live_button = ctk.CTkButton(box, text='Остановить наблюдение' if self.live_active else 'Начать наблюдение',
                                         command=self.toggle_live, fg_color=ACCENT)
        self.live_button.pack(anchor='w', padx=20, pady=(0, 16))
        self.live_state = text(box, 'Наблюдение остановлено', 14, '#a7b2ff')
        self.live_state.pack(anchor='w', padx=20, pady=(0, 12))
        self.live_values = ctk.CTkTextbox(box, height=270, fg_color=PANEL, font=('Segoe UI', 13), wrap='word')
        self.live_values.pack(fill='x', padx=20, pady=(0, 16))
        self.live_events_box = ctk.CTkTextbox(box, height=190, fg_color=PANEL, font=('Segoe UI', 12), wrap='word')
        self.live_events_box.pack(fill='x', padx=20, pady=(0, 20))
        self.render_live()

    def toggle_live(self):
        self.live_active = not self.live_active
        if self.live_active:
            self.live_previous = None
            self.live_state_text = 'Считываю конфиги…'
            self.live_poll()
        else:
            self.live_state_text = 'Наблюдение остановлено'
        self.show('Во время игры')

    def live_poll(self):
        if not self.live_active or self.live_busy:
            return
        self.live_busy = True
        settings_path = self.path
        engine_path = settings_path.parent / 'Engine.ini' if settings_path else None

        def worker():
            try:
                if not settings_path or not engine_path:
                    raise ValueError('Сначала выберите конфигурацию AION 2 в разделе «Обнаружение игры».')
                value = read_snapshot(settings_path, engine_path)
                self.live_queue.put((True, value))
            except Exception as exc:
                self.live_queue.put((False, str(exc)))
        threading.Thread(target=worker, daemon=True).start()
        self.after(150, self.consume_live)

    def consume_live(self):
        try:
            ok, value = self.live_queue.get_nowait()
        except queue.Empty:
            if self.live_active:
                self.after(100, self.consume_live)
            return
        self.live_busy = False
        if ok:
            if self.live_previous is not None:
                for change in differences(self.live_previous, value):
                    self.live_events.appendleft(time.strftime('%H:%M:%S') + ' · ' + change)
            self.live_previous = value
            self.live_state_text = 'Файлы прочитаны · ' + time.strftime('%H:%M:%S')
            if not self.live_events:
                self.live_events.appendleft('Изменений после запуска наблюдения пока нет.')
        else:
            self.live_state_text = 'Не удалось прочитать файлы · ' + value
        if self.page == 'Во время игры':
            self.render_live()
        if self.live_active:
            self.after(2500, self.live_poll)

    def render_live(self):
        if hasattr(self, 'live_button') and self.live_button.winfo_exists():
            self.live_button.configure(text='Остановить наблюдение' if self.live_active else 'Начать наблюдение')
        if not hasattr(self, 'live_state') or not self.live_state.winfo_exists():
            return
        self.live_state.configure(text=getattr(self, 'live_state_text', 'Наблюдение остановлено'))
        self.live_values.configure(state='normal')
        self.live_values.delete('1.0', 'end')
        if self.live_previous:
            lines = ['Качество игры'] + [f'  {key}: {value}' for key, value in self.live_previous['quality'].items()]
            lines += ['', 'Отслеживаемые параметры Engine.ini']
            lines += [f'  {key}: {self.live_previous["engine"].get(key, "не задано")}'
                      for key in ('r.ShadowQuality', 'r.ViewDistanceScale', 'r.SkeletalMeshLODBias',
                                  'r.SSR.Quality', 'r.MotionBlurQuality', 'r.Tonemapper.Sharpen', 't.MaxFPS')]
            self.live_values.insert('1.0', '\n'.join(lines))
        else:
            self.live_values.insert('1.0', 'Ожидание корректного снимка конфигов…')
        self.live_values.configure(state='disabled')
        self.live_events_box.configure(state='normal')
        self.live_events_box.delete('1.0', 'end')
        self.live_events_box.insert('1.0', 'Изменения\n' + '\n'.join(self.live_events))
        self.live_events_box.configure(state='disabled')
