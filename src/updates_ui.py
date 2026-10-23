from pathlib import Path
import json
import queue
import threading
import webbrowser
import customtkinter as ctk
from updater import check_and_download, installed_folder, launch_installer_after_exit
from features_ui import text, ACCENT
from version import VERSION


class Updates:
    def updates_init(self, root):
        self.update_root = root
        self.update_busy = False
        self.update_ready = None
        self.update_queue = queue.Queue()
        self.update_message = 'Проверка ещё не выполнялась.'
        self.update_enabled = bool(self.prefs.get('auto_update', True))
        state = Path(root) / 'update-status.json'
        if state.is_file():
            try:
                report = json.loads(state.read_text('utf-8-sig'))
                if report.get('ok'):
                    self.update_message = 'Последнее обновление установлено: ' + report['version']
                else:
                    self.update_message = 'Предыдущее обновление не завершилось: ' + report.get('message', 'неизвестная ошибка')
            except (OSError, ValueError, KeyError):
                pass
        if self.update_enabled and installed_folder():
            self.after(4000, self.auto_update_check)

    def auto_update_check(self):
        if self.update_enabled and installed_folder():
            self.start_update_check()

    def updates_page(self):
        box = self.panel()
        text(box, 'Обновления с GitHub', 23, '#edf3ff', True).pack(anchor='w', padx=20, pady=(20, 8))
        text(box, 'Установленная версия: ' + VERSION + '\nИсточник: Darkeys14/AION2-Graphics-Studio · стабильные релизы', wraplength=720).pack(anchor='w', padx=20, pady=(0, 16))
        toggle = ctk.CTkSwitch(box, text='Проверять и загружать обновления автоматически', command=self.toggle_updates)
        toggle.select() if self.update_enabled else toggle.deselect()
        toggle.pack(anchor='w', padx=20, pady=(0, 16))
        text(box, 'В установленной версии обновление загружается в фоне и устанавливается\nпри закрытии студии, затем приложение запускается снова. Отложенные\nзадачи для игры не прерываются автоматически. Python не требуется.\nРежим исходников и portable не обновляет свои файлы автоматически.', wraplength=720).pack(anchor='w', padx=20, pady=(0, 16))
        text(box, self.update_message, color='#a7b2ff', wraplength=720).pack(anchor='w', padx=20, pady=(0, 16))
        ctk.CTkButton(box, text='Проверяем и скачиваем…' if self.update_busy else 'Проверить сейчас',
                      state='disabled' if self.update_busy else 'normal', command=self.start_update_check,
                      fg_color=ACCENT).pack(anchor='w', padx=20, pady=(0, 18))
        if self.update_ready:
            if installed_folder():
                ctk.CTkButton(box, text='Установить и перезапустить', command=self.install_update_now,
                              fg_color=ACCENT).pack(anchor='w', padx=20, pady=(0, 18))
            else:
                text(box, 'Установщик загружен. Установите приложение через релиз GitHub,\nчтобы включить автоматическую установку будущих обновлений.', wraplength=720).pack(anchor='w', padx=20, pady=(0, 18))
        ctk.CTkButton(box, text='Открыть страницу релизов', fg_color='#26334c',
                      command=lambda: webbrowser.open('https://github.com/Darkeys14/AION2-Graphics-Studio/releases/latest')).pack(anchor='w', padx=20, pady=(0, 20))
        text(self.body, 'SHA-256 проверяет целостность загрузки. Он не заменяет подпись издателя.\nПри ошибке сети или проверки текущая версия продолжит работать.\nИгровые конфиги, профили и резервные копии обновление не удаляет.', 12, wraplength=720).pack(anchor='w', padx=6, pady=12)

    def toggle_updates(self):
        self.update_enabled = not self.update_enabled
        self.prefs['auto_update'] = self.update_enabled
        self.persist()
        if self.update_enabled and installed_folder():
            self.start_update_check()

    def start_update_check(self):
        if self.update_busy:
            return
        self.update_busy = True
        self.update_message = 'Проверяем последний стабильный релиз и загружаем обновление, если оно есть…'
        def worker():
            try:
                self.update_queue.put((True, check_and_download(self.update_root)))
            except Exception as exc:
                self.update_queue.put((False, str(exc)))
        threading.Thread(target=worker, daemon=True).start()
        self.after(200, self.consume_update)
        if self.page == 'Обновления':
            self.show(self.page)

    def consume_update(self):
        try:
            ok, result = self.update_queue.get_nowait()
        except queue.Empty:
            self.after(200, self.consume_update)
            return
        self.update_busy = False
        if ok:
            self.update_ready = result
            self.update_message = ('Версия ' + result['version'] + ' загружена. SHA-256 проверен.' if result else
                                   'Установлена актуальная стабильная версия.')
        else:
            self.update_message = 'Обновление не выполнено: ' + result
        if self.page == 'Обновления':
            self.show(self.page)
        if self.update_enabled and installed_folder():
            self.after(4 * 60 * 60 * 1000, self.auto_update_check)

    def schedule_ready_update(self):
        if not self.update_ready or not installed_folder():
            return False
        launch_installer_after_exit(self.update_root, self.update_ready, installed_folder())
        return True

    def install_update_now(self):
        if self.deferred.job:
            self.notify('Сначала выполните или отмените отложенную задачу для игры.', True)
            return
        try:
            if self.schedule_ready_update():
                self.destroy()
        except Exception as exc:
            self.update_message = 'Не удалось запустить обновление: ' + str(exc)
            self.show('Обновления')
