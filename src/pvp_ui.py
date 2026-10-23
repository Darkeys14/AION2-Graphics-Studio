import tkinter as tk
from tkinter import filedialog
import customtkinter as ctk
from core import ensure_closed, game_running
from engine import EngineDocument
from pvp import quality_profile, renderer_profile, tested_city_profile
from benchmarks import analyze, compare
from features_ui import text, PANEL, ACCENT


class Pvp:
    def pvp_init(self):
        self.pvp_lumen = True
        self.pvp_unlimited = True
        self.bench_before = self.bench_after = None

    def pvp_page(self):
        box = self.panel()
        text(box, 'Приоритет — массовые сцены и FPS', 22, '#edf3ff', True).pack(anchor='w', padx=20, pady=(20, 8))
        text(box, 'Настройка в два этапа: сначала группы качества, затем расширенные команды\nEngine.ini. У каждого файла — собственная проверенная копия и откат.\nРезультат оценивайте в одной и той же сцене по CSV PresentMon.', wraplength=720).pack(anchor='w', padx=20, pady=(0, 18))
        text(box, '1. Графический профиль для массовых сцен', 17, '#edf3ff', True).pack(anchor='w', padx=20, pady=(0, 8))
        text(box, 'Массовые сражения — 0; дальность и модели — 1.\nТени, освещение, отражения, растительность и постобработка — низкие.\nТекстуры и сглаживание — 2; эффекты — 1. Применение требует проверки в игре.', wraplength=720).pack(anchor='w', padx=20, pady=(0, 16))
        ctk.CTkButton(box, text='Подготовить профиль PvP · массовые сцены', fg_color=ACCENT,
                      command=self.prepare_pvp).pack(anchor='w', padx=20, pady=(0, 20))
        box = self.panel()
        text(box, '2. Расширенный рендер · экспериментально', 17, '#ffbc83', True).pack(anchor='w', padx=20, pady=(20, 8))
        text(box, 'Точечно меняет выбранные строки существующего SystemSettings.\nСохраняет прочие параметры, комментарии, DLSS/FSR и другие разделы.\nОсвещение, тени и отражения изменятся. Действие команд в AION 2\nне подтверждено для всех сборок; проверить видимость нужно в самой игре.', wraplength=720).pack(anchor='w', padx=20, pady=(0, 16))
        text(box, 'Набор из повторных городских замеров: тени 0, дальность 0,7, LOD моделей +1. Эффект предварительный и зависит от сцены.', 13, '#a7b2ff', wraplength=720).pack(anchor='w', padx=20, pady=(0, 10))
        ctk.CTkButton(box, text='Просмотр и применение набора для города', fg_color=ACCENT,
                      command=lambda: self.pvp_engine_preview(tested=True)).pack(anchor='w', padx=20, pady=(0, 16))
        for attr, title in [('pvp_lumen', 'Отключить Lumen GI и отражения · возможна смена освещения'),
                            ('pvp_unlimited', 'Снять только лимит t.MaxFPS · нагрузка может вырасти')]:
            var = tk.BooleanVar(value=getattr(self, attr))
            ctk.CTkCheckBox(box, text=title, variable=var, font=('Segoe UI', 12),
                           command=lambda a=attr, v=var: setattr(self, a, v.get())).pack(anchor='w', padx=20, pady=(0, 16))
        ctk.CTkButton(box, text='Просмотр точечных изменений Engine.ini', fg_color=ACCENT,
                      command=self.pvp_engine_preview).pack(anchor='w', padx=20, pady=(0, 12))
        ctk.CTkButton(box, text='Отложить этот этап до закрытия игры', fg_color='#26334c',
                      command=lambda: self.pvp_engine_preview(deferred=True)).pack(anchor='w', padx=20, pady=(0, 20))
        box = self.panel()
        text(box, 'Сравнение реальных замеров', 19, '#edf3ff', True).pack(anchor='w', padx=20, pady=(20, 8))
        text(box, 'Импорт CSV PresentMon с MsBetweenPresents. Выбирается основной\nпроцесс и swapchain AION 2; первые 5 и последние 3 секунды исключаются.\nЧастота Present не разделяет обычные и сгенерированные кадры.\n1% low = 1000 / среднее время самого медленного 1% кадров.', wraplength=720).pack(anchor='w', padx=20, pady=(0, 16))
        ctk.CTkButton(box, text='Загрузить замер «До»', fg_color='#26334c',
                      command=lambda: self.import_benchmark('before')).pack(anchor='w', padx=20, pady=(0, 10))
        ctk.CTkButton(box, text='Загрузить замер «После»', fg_color='#26334c',
                      command=lambda: self.import_benchmark('after')).pack(anchor='w', padx=20, pady=(0, 16))
        for name, report in [('До', self.bench_before), ('После', self.bench_after)]:
            if report:
                text(box, f"{name}: {report['average_fps']:.1f} FPS · 1% low {report['one_percent_low']:.1f}\nP99 {report['p99_ms']:.1f} мс · кадров >50 мс: {report['frames_over_50ms']}\n{report['file']} · {report['duration_s']:.1f} с", 13, '#a7b2ff', wraplength=720).pack(anchor='w', padx=20, pady=(0, 16))
        if self.bench_before and self.bench_after:
            result = compare(self.bench_before, self.bench_after)
            text(box, f"Разница: средний FPS {result['average_fps']:+.1f}% · 1% low {result['one_percent_low']:+.1f}%\nСравнение корректно только при сопоставимых сценах, числе игроков и действиях.", 13, '#8de0be', wraplength=720).pack(anchor='w', padx=20, pady=(0, 20))

    def prepare_pvp(self):
        self.values = quality_profile()
        self.selected = 'PvP · массовые сцены'
        self.show('Ручные настройки')
        self.notify('Профиль подготовлен. Для записи откройте просмотр изменений.')

    def import_benchmark(self, slot):
        path = filedialog.askopenfilename(title='CSV PresentMon · ' + slot, filetypes=[('Замеры PresentMon', '*.csv')])
        if path:
            try:
                setattr(self, 'bench_' + slot, analyze(path))
                self.show('PvP · расширенный')
            except Exception as exc:
                self.notify(str(exc), True)

    def pvp_engine_preview(self, deferred=False, tested=False):
        try:
            if not self.path or self.raw is None:
                raise ValueError('Сначала выберите проверенную конфигурацию игры.')
            if not deferred:
                ensure_closed()
            path = self.path.parent / 'Engine.ini'
            expected = path.read_bytes()
            doc = EngineDocument(expected)
            values = tested_city_profile() if tested else renderer_profile(self.pvp_lumen, self.pvp_unlimited)
            updated = doc.patch(values, merge=True)
            if updated == expected:
                raise ValueError('Эти параметры уже записаны в Engine.ini.')
            current = doc.read_settings(values)
            win = ctk.CTkToplevel(self)
            label = 'набор для города' if tested else 'точечное изменение'
            win.title('PvP · Engine.ini · ' + label)
            win.geometry('740x660')
            win.configure(fg_color='#0b101b')
            win.transient(self)
            text(win, 'Просмотр изменений', 23, '#edf3ff', True).pack(anchor='w', padx=24, pady=(22, 10))
            area = ctk.CTkTextbox(win, font=('Consolas', 13), fg_color=PANEL)
            area.pack(fill='both', expand=True, padx=24, pady=10)
            area.insert('1.0', '\n'.join(f"{key}: {current.get(key, 'не задано')} → {value}" for key, value in values.items()))
            area.configure(state='disabled')
            text(win, 'Будет изменён существующий SystemSettings, без создания дубликата.\nНеизвестные строки сохранятся. Копия создаётся перед записью.\n' + ('Оставьте студию открытой до завершения игры.' if deferred else 'Применение команд движком нужно проверить после запуска.'), wraplength=690).pack(anchor='w', padx=24, pady=14)
            ctk.CTkButton(win, text='Отложить до выхода' if deferred else 'Создать копию и применить', height=40,
                          fg_color=ACCENT, command=lambda: self.commit_pvp_engine(win, path, expected, values, deferred, tested)).pack(fill='x', padx=24, pady=(0, 22))
            self.after(150, lambda: win.grab_set() if win.winfo_exists() else None)
        except Exception as exc:
            self.notify(str(exc), True)

    def commit_pvp_engine(self, window, path, expected, values, deferred, tested=False):
        label = 'PvP · проверенный набор для города' if tested else 'PvP · расширенный рендер'
        if deferred:
            self.queue_write(window, path, values, label, 'engine-merged')
            return
        try:
            self.store.apply_engine(path, expected, values, label, merge=True)
            self.notify('Расширенные параметры записаны. Копия проверена; результат оцените в игре.')
        except Exception as exc:
            self.notify(str(exc), True)
        finally:
            window.destroy()
