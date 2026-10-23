from __future__ import annotations
import json
import os
import sys
from pathlib import Path
import tkinter as tk
import threading
import queue
from tkinter import filedialog, messagebox
import customtkinter as ctk
from core import Document, Store, FIELDS, PRESETS, discover, ensure_closed, atomic_write
from engine import EngineDocument, recommend
from hardware import scan
from features_ui import Features
from updates_ui import Updates
from version import VERSION
from pvp_ui import Pvp
from live_ui import LiveWatch

ctk.set_appearance_mode('dark')
ctk.set_default_color_theme('blue')
BG, PANEL, CARD = '#0b101b', '#111827', '#182235'
TEXT, MUTED, ACCENT = '#edf3ff', '#93a4bf', '#5e75fa'
LEVELS = ['Низкое', 'Среднее', 'Высокое', 'Максимальное']
ROOT = Path(os.environ['LOCALAPPDATA']) / 'AION2GraphicsStudio'


def label(parent, text, size=14, color=TEXT, bold=False, **kw):
    return ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(family='Segoe UI', size=size,
                         weight='bold' if bold else 'normal'), text_color=color, **kw)


class Studio(LiveWatch, Pvp, Updates, Features, ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title('AION 2 Graphics Studio')
        icon = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / 'assets' / 'app.ico'
        if icon.is_file():
            self.iconbitmap(str(icon))
        self.geometry('1220x840')
        self.minsize(1120, 740)
        self.configure(fg_color=BG)
        self.store = Store(ROOT)
        self.path = None
        self.raw = None
        self.values = PRESETS['Баланс'].copy()
        self.selected = 'Баланс'
        self.page = 'Профили'
        self.controls = {}
        self.hardware = None
        self.hardware_queue = queue.Queue()
        self.scanning = False
        self.opt = {'goal': 'Баланс', 'vram': 'Не определена', 'fps': 'Как в игре'}
        self.config_file = ROOT / 'studio.json'
        try:
            self.prefs = json.loads(self.config_file.read_text('utf-8'))
        except (OSError, ValueError):
            self.prefs = {}
        self.features_init(ROOT)
        self.pvp_init()
        self.live_init()
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color=PANEL)
        self.sidebar.grid(row=0, column=0, sticky='nsew')
        self.sidebar.grid_propagate(False)
        label(self.sidebar, 'AION 2', 32, bold=True).pack(anchor='w', padx=25, pady=(22, 0))
        label(self.sidebar, 'ГРАФИЧЕСКАЯ СТУДИЯ · ' + VERSION, 10, MUTED).pack(anchor='w', padx=27, pady=(0, 16))
        self.nav = {}
        navigation = ctk.CTkScrollableFrame(self.sidebar, fg_color='transparent', corner_radius=0)
        navigation.pack(fill='both', expand=True, padx=5, pady=(0, 10))
        for title in ['Профили', 'Ручные настройки', 'Оптимизация', 'PvP · расширенный', 'Профили из игры',
                      'Во время игры', 'Проверка настроек', 'Нагрузка ПК', 'Резервные копии', 'Файл настроек DAT', 'Обнаружение игры', 'Обновления']:
            button = ctk.CTkButton(navigation, text=title, anchor='w', height=40, corner_radius=10,
                                  fg_color='transparent', hover_color=CARD,
                                  font=('Segoe UI', 14), command=lambda t=title: self.show(t))
            button.pack(fill='x', padx=4, pady=3)
            self.nav[title] = button
        hardware = ctk.CTkFrame(self.sidebar, fg_color=CARD, corner_radius=12)
        hardware.pack(side='bottom', fill='x', padx=16, pady=(0, 16))
        label(hardware, 'ВАШ КОМПЬЮТЕР', 10, MUTED).pack(anchor='w', padx=14, pady=(15, 6))
        self.hardware_label = label(hardware, 'Определяем оборудование…', 12, MUTED,
                                    wraplength=160, justify='left')
        self.hardware_label.pack(anchor='w', padx=14, pady=(2, 15))
        main = ctk.CTkFrame(self, fg_color='transparent')
        main.grid(row=0, column=1, sticky='nsew', padx=30, pady=26)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=1)
        self.heading = label(main, 'Профили графики', 29, bold=True)
        self.heading.grid(row=0, column=0, sticky='w')
        self.subtitle = label(main, 'Выберите характер игры. Детали остаются под вашим контролем.', 13, MUTED)
        self.subtitle.grid(row=1, column=0, sticky='w', pady=(5, 22))
        self.body = ctk.CTkScrollableFrame(main, fg_color='transparent', corner_radius=0)
        self.body.grid(row=2, column=0, sticky='nsew')
        footer = ctk.CTkFrame(main, fg_color=PANEL, corner_radius=12)
        footer.grid(row=3, column=0, sticky='ew', pady=(18, 0))
        self.status = label(footer, 'Проверка конфигурации…', 12, MUTED, wraplength=320, justify='left')
        self.status.pack(side='left', padx=18, pady=15)
        ctk.CTkButton(footer, text='Просмотр изменений', width=185, height=40,
                      fg_color=ACCENT, hover_color='#4b60da', command=self.preview).pack(side='right', padx=14, pady=14)
        ctk.CTkButton(footer, text='После выхода', width=120, height=40, fg_color='#26334c',
                      command=lambda: self.preview(deferred=True)).pack(side='right', padx=4, pady=14)
        self.updates_init(ROOT)
        self.detect(initial=True)
        self.scan_hardware()
        self.begin_services()

    def scan_hardware(self):
        if self.scanning:
            return
        self.scanning = True
        self.hardware_label.configure(text='Определяем оборудование…')
        def worker():
            try:
                self.hardware_queue.put((True, scan()))
            except Exception as exc:
                self.hardware_queue.put((False, str(exc)))
        threading.Thread(target=worker, daemon=True).start()
        self.after(150, self.hardware_result)

    def hardware_result(self):
        try:
            ok, result = self.hardware_queue.get_nowait()
        except queue.Empty:
            self.after(150, self.hardware_result)
            return
        self.scanning = False
        self.hardware = result if ok else None
        if ok:
            gpu = '\n'.join(g['name'] for g in result['gpu']) or 'Видеокарта не определена'
            cpu = '\n'.join(result['cpu']) or 'Процессор не определён'
            ram = f"ОЗУ: {result['ram_gb']:g} ГБ" if result['ram_gb'] else 'ОЗУ не определена'
            self.hardware_label.configure(text=gpu + '\n\n' + cpu + '\n\n' + ram)
            dedicated = [g['vram_gb'] for g in result['gpu'] if g['vram_gb']]
            if dedicated and self.opt['vram'] == 'Не определена':
                memory = max(dedicated)
                self.opt['vram'] = next((f'{n} ГБ' for n in [4, 6, 8, 12] if abs(memory - n) < 0.6),
                                        '16 ГБ и больше' if memory >= 16 else 'Не определена')
        else:
            self.hardware_label.configure(text='Не удалось определить\nоборудование Windows')
        if self.page in ['Оптимизация', 'Обнаружение игры']:
            self.show(self.page)

    def notify(self, text, error=False):
        self.status.configure(text=text, text_color='#ffbc83' if error else '#8de0be')

    def persist(self):
        atomic_write(self.config_file, json.dumps(self.prefs, ensure_ascii=False, indent=2).encode('utf-8'))

    def detect(self, initial=False):
        self.candidates = discover()
        preferred = self.prefs.get('path')
        if preferred and Path(preferred).is_file():
            self.path = Path(preferred)
        elif len(self.candidates) == 1:
            self.path = self.candidates[0]
        elif len(self.candidates) > 1:
            self.path = None
        if self.path:
            self.load()
        else:
            self.notify('Выберите конфигурацию: найдено несколько вариантов.' if self.candidates else
                        'Конфигурация не найдена. Укажите файл в разделе обнаружения.', True)
        self.show(self.page)

    def load(self):
        try:
            cancelled = bool(self.deferred.job and self.deferred.job['path'].parent != self.path.resolve().parent)
            if cancelled:
                self.deferred.cancel()
            raw = self.path.read_bytes()
            doc = Document(raw)
            self.raw = raw
            self.disk_values = doc.values
            self.notify('Конфигурация изменена: отложенная запись отменена.' if cancelled else
                        'Конфигурация обнаружена · 13 параметров проверены', cancelled)
            self.prefs['path'] = str(self.path)
            self.persist()
        except Exception as exc:
            self.raw = None
            self.notify(str(exc), True)

    def show(self, page):
        self.page = page
        for title, button in self.nav.items():
            button.configure(fg_color='#243252' if title == page else 'transparent',
                             text_color=TEXT if title == page else MUTED)
        for child in self.body.winfo_children():
            child.destroy()
        self.controls = {}
        self.heading.configure(text={'Профили': 'Профили графики'}.get(page, page))
        self.subtitle.configure(text={
            'Профили': 'Выберите характер игры. Детали остаются под вашим контролем.',
            'Ручные настройки': 'Только параметры, найденные в реальной конфигурации AION 2.',
            'Оптимизация': 'Подберите параметры — приложение само подготовит и запишет Engine.ini.',
            'Профили из игры': 'Сохранённые настройки из вашего клиента AION 2.',
            'Проверка настроек': 'Сравнение файлов и управление отложенной записью.',
            'Нагрузка ПК': 'Наблюдение через системные счётчики Windows.',
            'Файл настроек DAT': 'Анализ локального файла без изменения его содержимого.',
            'Обновления': 'Стабильные версии из официального репозитория приложения.',
            'PvP · расширенный': 'Приоритет производительности в сценах с большим числом игроков.',
            'Во время игры': 'Только наблюдение за файлами настроек; без записи и управления процессом.',
            'Резервные копии': 'Каждая запись начинается с проверенной копии исходного файла.',
            'Обнаружение игры': 'Локальная конфигурация, состояние игры и границы поддержки.',
        }[page])
        {'Профили': self.profiles, 'Ручные настройки': self.manual,
         'Оптимизация': self.optimization,
         'Профили из игры': self.captures_page, 'Проверка настроек': self.verification_page,
         'Нагрузка ПК': self.monitor_page, 'Файл настроек DAT': self.device_page,
         'Обновления': self.updates_page,
         'PvP · расширенный': self.pvp_page,
         'Во время игры': self.live_page,
         'Резервные копии': self.history, 'Обнаружение игры': self.diagnostics}[page]()

    def panel(self):
        box = ctk.CTkFrame(self.body, fg_color=PANEL, corner_radius=15)
        box.pack(fill='x', pady=(0, 14), padx=2)
        return box

    def profiles(self):
        hero = self.panel()
        label(hero, 'ВАША ИГРА. ВАШ БАЛАНС.', 11, '#a2b0ff', bold=True).pack(anchor='w', padx=24, pady=(22, 5))
        label(hero, 'Больше контроля над каждым кадром', 23, bold=True).pack(anchor='w', padx=24)
        label(hero, 'Профиль подготовит настройки. Применение — только по вашему нажатию.',
              13, MUTED).pack(anchor='w', padx=24, pady=(9, 23))
        cards = ctk.CTkFrame(self.body, fg_color='transparent')
        cards.pack(fill='x', pady=(0, 16))
        cards.grid_columnconfigure((0, 1, 2), weight=1, uniform='cards')
        specs = [('PvP', 'ПРИОРИТЕТ ОТКЛИКА', 'Меньше теней и эффектов.\nДля насыщенных сражений.', '#79d7c8'),
                 ('Баланс', 'НА КАЖДЫЙ ДЕНЬ', 'Качество и умеренная нагрузка.\nНачальная точка для настройки.', '#a7b2ff'),
                 ('Ультра', 'ПРИОРИТЕТ КАРТИНКИ', 'Максимум в пределах MVP.\nНагрузка и FPS зависят от сцены.', '#e3b87a')]
        for idx, (name, tag, desc, color) in enumerate(specs):
            active = self.selected == name
            card = ctk.CTkFrame(cards, fg_color=CARD if active else PANEL, corner_radius=15,
                               border_width=2 if active else 1, border_color=ACCENT if active else '#253047')
            card.grid(row=0, column=idx, sticky='nsew', padx=5)
            label(card, tag, 10, color, bold=True).pack(anchor='w', padx=18, pady=(22, 10))
            label(card, name, 28, bold=True).pack(anchor='w', padx=18)
            label(card, desc, 12, MUTED, justify='left').pack(anchor='w', padx=18, pady=(12, 24))
            ctk.CTkButton(card, text='Выбран' if active else 'Выбрать профиль', height=37,
                          fg_color=ACCENT if active else '#26334c', hover_color='#3e5079',
                          command=lambda n=name: self.choose(n)).pack(fill='x', padx=17, pady=(0, 19))
        box = self.panel()
        label(box, 'Подготовлен: ' + self.selected, 17, bold=True).pack(anchor='w', padx=22, pady=(18, 7))
        label(box, 'Профиль ещё не применён к игре. Вы можете изменить каждый параметр вручную.',
              12, MUTED).pack(anchor='w', padx=22, pady=(0, 14))
        ctk.CTkButton(box, text='Настроить вручную  →', fg_color='#26334c', height=35,
                      command=lambda: self.show('Ручные настройки')).pack(anchor='w', padx=22, pady=(0, 19))
        label(self.body, 'Изменения требуют закрытой игры и последующего запуска.\nПрофили — отправная точка; прирост FPS не измерен и не обещается.',
              12, MUTED, justify='left').pack(anchor='w', padx=7, pady=8)

    def choose(self, name):
        self.values = PRESETS[name].copy()
        self.selected = name
        self.show('Профили')
        self.notify('Профиль «' + name + '» подготовлен. Для записи откройте просмотр изменений.')

    def manual(self):
        toolbar = self.panel()
        label(toolbar, 'Подготовлен: ' + self.selected, 15, bold=True).pack(side='left', padx=18, pady=14)
        ctk.CTkButton(toolbar, text='Взять из файла', fg_color='#26334c', command=self.from_disk).pack(side='right', padx=15)
        saved = self.prefs.get('manual')
        if saved:
            ctk.CTkButton(toolbar, text='Мой профиль', fg_color='#26334c', width=120,
                          command=self.recall).pack(side='right', padx=5)
        for key, title in FIELDS.items():
            row = ctk.CTkFrame(self.body, fg_color=PANEL, corner_radius=10)
            row.pack(fill='x', pady=4, padx=2)
            label(row, title, 14).pack(side='left', padx=18, pady=15)
            value = self.values[key]
            options = LEVELS + (['Особое (4)'] if value == 4 else [])
            menu = ctk.CTkOptionMenu(row, values=options, width=190, fg_color='#26334c',
                                    button_color='#344363', button_hover_color='#465b86',
                                    command=lambda v, k=key: self.edit(k, v))
            menu.set(LEVELS[value] if value < 4 else 'Особое (4)')
            menu.pack(side='right', padx=16, pady=8)
            self.controls[key] = menu
        ctk.CTkButton(self.body, text='Сохранить мой профиль', height=38,
                      fg_color=ACCENT, command=self.save_manual).pack(anchor='w', padx=4, pady=18)

    def edit(self, key, value):
        self.values[key] = LEVELS.index(value) if value in LEVELS else 4
        self.selected = 'Вручную'
        self.notify('Ручные изменения подготовлены. Они ещё не записаны в игру.')

    def from_disk(self):
        if self.path:
            self.load()
        if self.raw:
            self.values = Document(self.raw).values.copy()
            self.selected = 'Из файла'
            self.show('Ручные настройки')

    def save_manual(self):
        try:
            Document(self.raw).patch(self.values) if self.raw else self.validate_values()
            self.prefs['manual'] = self.values.copy()
            self.persist()
            self.notify('Мой профиль сохранён в приложении.')
        except Exception as exc:
            self.notify(str(exc), True)

    def validate_values(self):
        if set(self.values) != set(FIELDS) or any(type(v) is not int or not 0 <= v <= 3 for v in self.values.values()):
            raise ValueError('Для записи выберите качество от низкого до максимального.')

    def recall(self):
        self.values = self.prefs['manual'].copy()
        self.selected = 'Мой профиль'
        self.show('Ручные настройки')

    def preview(self, deferred=False):
        try:
            if not self.path or self.raw is None:
                raise ValueError('Сначала выберите поддерживаемый GameUserSettings.ini в разделе обнаружения.')
            if not deferred:
                ensure_closed()
            if self.path.read_bytes() != self.raw:
                self.load()
                raise ValueError('Файл изменился. Данные обновлены; откройте просмотр повторно.')
            doc = Document(self.raw)
            doc.patch(self.values)
            changes = [(k, doc.values[k], v) for k, v in self.values.items() if doc.values[k] != v]
            if not changes:
                raise ValueError('Изменений нет: в файле уже записаны выбранные значения.')
            win = ctk.CTkToplevel(self)
            win.title('Просмотр изменений')
            win.geometry('660x650')
            win.minsize(600, 540)
            win.configure(fg_color=BG)
            win.transient(self)
            label(win, 'Применить после выхода' if deferred else 'Готово к применению', 24, bold=True).pack(anchor='w', padx=25, pady=(25, 7))
            label(win, 'Профиль: ' + self.selected + ' · ' + str(len(changes)) + ' изменений', 13, MUTED).pack(anchor='w', padx=25)
            scroll = ctk.CTkScrollableFrame(win, fg_color=PANEL)
            scroll.pack(fill='both', expand=True, padx=25, pady=20)
            for key, old, new in changes:
                a = LEVELS[old] if old < 4 else 'Особое (4)'
                label(scroll, f'{FIELDS[key]}: {a} → {LEVELS[new]}', 13, anchor='w').pack(fill='x', padx=12, pady=9)
            label(win, 'После закрытия игры будут изменены только выбранные группы качества.\nСтудия должна оставаться открытой. Копия создаётся перед записью.' if deferred else
                       'Будет создана резервная копия с проверкой целостности.\nПосле записи запустите игру и проверьте результат.',
                  12, MUTED, justify='left').pack(anchor='w', padx=25, pady=(0, 12))
            expected, values, path, title = self.raw, self.values.copy(), self.path, self.selected
            action = self.queue_quality if deferred else self.apply
            ctk.CTkButton(win, text='Отложить до закрытия игры' if deferred else 'Создать копию и применить', height=42, fg_color=ACCENT,
                          command=lambda: action(win, path, expected, values, title)).pack(fill='x', padx=25, pady=(0, 22))
            self.after(150, lambda: win.grab_set() if win.winfo_exists() else None)
        except Exception as exc:
            self.notify(str(exc), True)

    def apply(self, window, path, expected, values, title):
        try:
            self.store.apply(path, expected, values, title)
            window.destroy()
            self.load()
            self.notify('Настройки записаны, копия проверена. Запустите игру для проверки результата.')
        except Exception as exc:
            window.destroy()
            self.notify(str(exc), True)

    def history(self):
        items = self.store.records()
        if not items:
            box = self.panel()
            label(box, 'Здесь появится история изменений', 21, bold=True).pack(anchor='w', padx=24, pady=(28, 12))
            label(box, 'При первом применении приложение сохранит исходный файл.\nКопии хранятся локально, отдельно от игры.',
                  13, MUTED, justify='left').pack(anchor='w', padx=24, pady=(0, 28))
        for item in items:
            box = self.panel()
            label(box, item['label'], 17, bold=True).pack(anchor='w', padx=20, pady=(16, 5))
            label(box, item['time'], 12, MUTED).pack(anchor='w', padx=20)
            label(box, item['path'], 11, MUTED, wraplength=710, justify='left').pack(anchor='w', padx=20, pady=8)
            ctk.CTkButton(box, text='Восстановить', width=150, fg_color='#26334c',
                          command=lambda i=item: self.restore(i)).pack(anchor='w', padx=20, pady=(3, 17))
        label(self.body, 'Откат блокируется, если игра или другая программа уже изменила файл.\nПеред восстановлением сохраняется дополнительная копия.',
              12, MUTED, justify='left').pack(anchor='w', padx=7, pady=12)

    def restore(self, item):
        if not self.path:
            self.notify('Сначала выберите исходный файл конфигурации.', True)
            return
        if not messagebox.askyesno('Восстановление', 'Вернуть файл в состояние до изменения «' + item['label'] + '»?\nТекущий файл также будет сохранён.', parent=self):
            return
        try:
            basename = Path(item['path']).name
            if basename.lower() not in {'engine.ini', 'gameusersettings.ini'}:
                raise ValueError('Неподдерживаемая резервная копия.')
            self.store.restore(item['id'], self.path.parent / basename)
            self.load()
            self.show('Резервные копии')
            self.notify('Исходный файл восстановлен и проверен.')
        except Exception as exc:
            self.notify(str(exc), True)

    def browse(self):
        path = filedialog.askopenfilename(title='Выберите GameUserSettings.ini',
                                         initialdir=str(Path(os.environ['LOCALAPPDATA']) / 'AION2'),
                                         filetypes=[('Настройки игры', 'GameUserSettings.ini')])
        if path:
            self.path = Path(path)
            self.load()
            self.show('Обнаружение игры')

    def select_candidate(self, value):
        self.path = next(p for p in self.candidates if str(p) == value)
        self.load()
        self.show('Обнаружение игры')

    def diagnostics(self):
        hardware = self.panel()
        label(hardware, 'Оборудование · данные Windows', 18, bold=True).pack(anchor='w', padx=22, pady=(20, 10))
        if self.hardware:
            info = self.hardware
            gpu = '\n'.join(g['name'] + (f" · {g['vram_gb']:g} ГБ видеопамяти" if g['vram_gb'] else ' · видеопамять не определена') for g in info['gpu'])
            text = '\n'.join(info['cpu']) + '\n' + gpu + (f"\nУстановленная ОЗУ: {info['ram_gb']:g} ГБ" if info['ram_gb'] else '\nОЗУ не определена')
        else:
            text = 'Определяем оборудование…' if self.scanning else 'Сведения недоступны. Можно повторить сканирование.'
        label(hardware, text, 13, MUTED, justify='left', wraplength=700).pack(anchor='w', padx=22, pady=(0, 12))
        ctk.CTkButton(hardware, text='Сканировать ПК', fg_color='#26334c', command=self.scan_hardware).pack(anchor='w', padx=22, pady=(0, 18))
        box = self.panel()
        label(box, 'Конфигурация AION 2', 19, bold=True).pack(anchor='w', padx=22, pady=(20, 10))
        label(box, str(self.path) if self.path else 'Файл не выбран', 12, MUTED,
              wraplength=700, justify='left').pack(anchor='w', padx=22, pady=5)
        label(box, 'Формат проверен: 13 групп качества' if self.raw else 'Запись недоступна: формат не подтверждён',
              13, '#8de0be' if self.raw else '#ffbc83').pack(anchor='w', padx=22, pady=8)
        if len(self.candidates) > 1:
            menu = ctk.CTkOptionMenu(box, values=[str(p) for p in self.candidates],
                                    command=self.select_candidate, width=650)
            menu.set(str(self.path) if self.path else 'Выберите версию игры')
            menu.pack(anchor='w', padx=22, pady=8)
        tools = ctk.CTkFrame(box, fg_color='transparent')
        tools.pack(anchor='w', padx=22, pady=(12, 20))
        ctk.CTkButton(tools, text='Выбрать файл', command=self.browse, fg_color=ACCENT).pack(side='left', padx=(0, 12))
        ctk.CTkButton(tools, text='Проверить снова', command=self.detect, fg_color='#26334c').pack(side='left')
        box = self.panel()
        try:
            ensure_closed()
            process_text = 'Игра не обнаружена среди запущенных процессов'
        except Exception as exc:
            process_text = str(exc)
        label(box, 'Состояние игры', 18, bold=True).pack(anchor='w', padx=22, pady=(20, 8))
        label(box, process_text, 13, MUTED, wraplength=700).pack(anchor='w', padx=22, pady=(0, 20))
        box = self.panel()
        label(box, 'Что поддерживает эта версия', 18, bold=True).pack(anchor='w', padx=22, pady=(20, 10))
        label(box, '• 13 существующих строк раздела ScalabilityGroups.\n• Качество 0–3; «Ультра» использует уровень 3.\n• Отдельный генератор Engine.ini на вкладке «Оптимизация».\n• Проверенные копии и откат с защитой от конфликтов.\n• Обычное окно: без горячих клавиш и перехвата мыши.\n\nDLSS, генерация кадров и DeviceSetting_V2.dat не изменяются.\nИгра может перезаписать INI: влияние необходимо проверить после запуска.\nПриложение не читает память игры и не взаимодействует с античитом.',
              13, MUTED, justify='left', wraplength=720).pack(anchor='w', padx=22, pady=(0, 23))

    def optimization(self):
        box = self.panel()
        label(box, 'Оптимизация без ручного редактирования', 22, bold=True).pack(anchor='w', padx=22, pady=(20, 8))
        label(box, 'Выберите цель и симптомы. Студия сформирует собственный блок Engine.ini,\nсохранит исходный файл и применит изменения после просмотра.',
              13, MUTED, justify='left').pack(anchor='w', padx=22, pady=(0, 17))
        if self.hardware:
            gpu = ' / '.join(g['name'] for g in self.hardware['gpu']) or 'Не определена'
        else:
            gpu = 'Определяется…' if self.scanning else 'Не определена'
        label(box, 'Видеокарта: ' + gpu, 13, '#a7b2ff', wraplength=700, justify='left').pack(anchor='w', padx=22, pady=(0, 18))
        self.option_row('Цель', 'goal', ['Баланс', 'PvP', 'Качество'])
        problems = self.panel()
        label(problems, 'Что хочется исправить?', 17, bold=True).pack(anchor='w', padx=20, pady=(17, 10))
        for key, title in [('fps_drop', 'Просадки FPS — снизить тени и отражения'),
                           ('blurred', 'Размытая картинка — добавить резкость'),
                           ('streaming', 'Поздняя загрузка текстур — настроить пул памяти')]:
            var = tk.BooleanVar(value=self.opt.get(key, False))
            check = ctk.CTkCheckBox(problems, text=title, variable=var, font=('Segoe UI', 13),
                                   command=lambda k=key, v=var: self.opt.update({k: v.get()}))
            check.pack(anchor='w', padx=20, pady=(0, 15))
        self.option_row('Видеопамять · можно уточнить вручную', 'vram',
                        ['Не определена', '4 ГБ', '6 ГБ', '8 ГБ', '12 ГБ', '16 ГБ и больше'])
        label(self.body, 'Пул памяти меняется только при выборе проблемы загрузки текстур.\nЕсли видеопамять неизвестна, размер пула не задаётся.',
              12, MUTED, justify='left').pack(anchor='w', padx=6, pady=(0, 15))
        self.option_row('Резкость', 'sharpness', ['Автоматически', 'Как в игре', 'Мягко', 'Чётко', 'Очень чётко'])
        self.option_row('Тени', 'shadows', ['Автоматически', 'Как в игре', 'Низкие', 'Средние', 'Высокие'])
        self.option_row('Экранные отражения', 'reflections', ['Автоматически', 'Как в игре', 'Низкие', 'Средние', 'Высокие'])
        self.option_row('Размытие в движении', 'motion', ['Автоматически', 'Как в игре', 'Отключить'])
        self.option_row('Глубина резкости', 'dof', ['Как в игре', 'Отключить'])
        self.option_row('Блики объектива', 'lens', ['Как в игре', 'Отключить'])
        self.option_row('Ограничение кадров', 'fps', ['Как в игре', '60', '90', '120', '144', '165', '240'])
        box = self.panel()
        label(box, 'Экспериментальные параметры движка', 16, '#ffbc83', bold=True).pack(anchor='w', padx=20, pady=(17, 8))
        label(box, 'Команды описаны в документации Unreal Engine. Их применение именно\nэтой сборкой AION 2 и прирост FPS не проверены. Изменения действуют\nпосле запуска игры. DLSS, RHI и генерация кадров не форсируются.\nСторонние блоки настроек автоматически не перезаписываются.',
              12, MUTED, justify='left').pack(anchor='w', padx=20, pady=(0, 18))
        ctk.CTkButton(self.body, text='Сформировать и применить Engine.ini', height=44, fg_color=ACCENT,
                      command=self.engine_preview).pack(fill='x', padx=4, pady=12)
        ctk.CTkButton(self.body, text='Отложить Engine.ini до закрытия игры', height=38, fg_color='#26334c',
                      command=lambda: self.engine_preview(deferred=True)).pack(fill='x', padx=4, pady=(0, 12))
        ctk.CTkButton(self.body, text='Удалить только блок оптимизации студии', height=38, fg_color='#26334c',
                      command=lambda: self.engine_preview(remove=True)).pack(fill='x', padx=4, pady=(0, 15))

    def option_row(self, title, key, choices):
        row = self.panel()
        label(row, title, 13).pack(side='left', padx=18, pady=16)
        menu = ctk.CTkOptionMenu(row, values=choices, width=200, fg_color='#26334c',
                                button_color='#344363', command=lambda v: self.opt.update({key: v}))
        menu.set(self.opt.get(key, choices[0]))
        menu.pack(side='right', padx=16, pady=10)

    def engine_preview(self, remove=False, deferred=False):
        try:
            if not self.path or self.raw is None:
                raise ValueError('Сначала выберите проверенную конфигурацию игры.')
            if not deferred:
                ensure_closed()
            path = self.path.parent / 'Engine.ini'
            expected = path.read_bytes()
            document = EngineDocument(expected)
            values = {} if remove else recommend(self.opt)
            if not values and not remove:
                raise ValueError('Сейчас выбрано сохранение игровых настроек. Выберите цель PvP/Качество, проблему или конкретный параметр.')
            updated = document.patch(values)
            if updated == expected:
                raise ValueError('Engine.ini уже соответствует выбранным настройкам.')
            win = ctk.CTkToplevel(self)
            win.title('Оптимизация Engine.ini')
            win.geometry('690x610')
            win.configure(fg_color=BG)
            win.transient(self)
            label(win, 'Удаление блока студии' if remove else 'Параметры Engine.ini', 24, bold=True).pack(anchor='w', padx=25, pady=(24, 8))
            label(win, str(path), 11, MUTED, wraplength=630, justify='left').pack(anchor='w', padx=25)
            text = ctk.CTkTextbox(win, font=('Consolas', 14), fg_color=PANEL)
            text.pack(fill='both', expand=True, padx=25, pady=18)
            text.insert('1.0', 'Будет удалён только блок AION2 GRAPHICS STUDIO.\nОстальной файл будет сохранён.' if remove else
                        '[SystemSettings]\n' + '\n'.join(f'{k}={v}' for k, v in values.items()))
            text.configure(state='disabled')
            label(win, 'Запись после закрытия игры и паузы на сохранение.\nОставьте студию открытой; исходный файл будет сохранён перед записью.' if deferred else
                       'Исходный файл будет сохранён и проверен.\nРезультат в игре требует проверки после запуска.',
                  12, MUTED, justify='left').pack(anchor='w', padx=25, pady=(0, 15))
            action = self.queue_engine if deferred else self.engine_apply
            ctk.CTkButton(win, text='Отложить до закрытия игры' if deferred else 'Создать копию и применить', height=42, fg_color=ACCENT,
                          command=lambda: action(win, path, expected, values, remove)).pack(fill='x', padx=25, pady=(0, 23))
            self.after(150, lambda: win.grab_set() if win.winfo_exists() else None)
        except Exception as exc:
            self.notify(str(exc), True)

    def engine_apply(self, win, path, expected, values, remove):
        try:
            self.store.apply_engine(path, expected, values, 'Engine.ini · удаление блока' if remove else 'Engine.ini · оптимизация')
            win.destroy()
            self.notify('Engine.ini сохранён, резервная копия проверена. Проверьте результат после запуска игры.')
        except Exception as exc:
            win.destroy()
            self.notify(str(exc), True)


if __name__ == '__main__':
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    ctypes.set_last_error(0)
    mutex = kernel.CreateMutexW(None, False, 'Local\\AION2GraphicsStudio')
    already_open = ctypes.get_last_error() == 183
    if already_open:
        messagebox.showinfo('AION 2 Graphics Studio', 'Приложение уже открыто. Переключитесь в его окно.')
    elif mutex:
        try:
            Studio().mainloop()
        finally:
            kernel.CloseHandle(mutex)
    else:
        messagebox.showerror('AION 2 Graphics Studio', 'Не удалось безопасно запустить единственный экземпляр приложения.')
