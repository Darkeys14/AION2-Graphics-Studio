"""Windows UI construction smoke test using synthetic configs and temporary app data only."""
import sys
from pathlib import Path
import tempfile
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from test_core import fixture
from test_engine import SOURCE
import app
from experience import device_path


with tempfile.TemporaryDirectory() as tmp:
    folder = Path(tmp)
    config = folder / 'Saved_Test' / 'Config' / 'Windows' / 'GameUserSettings.ini'
    config.parent.mkdir(parents=True)
    config.write_bytes(fixture())
    (config.parent / 'Engine.ini').write_bytes(SOURCE)
    dat = device_path(config)
    dat.parent.mkdir(parents=True)
    dat.write_bytes(b'\xe1\x52\x81\x6e' * 40)
    with patch.object(app, 'ROOT', folder / 'studio'), patch.object(app, 'discover', return_value=[config]), \
            patch.object(app, 'scan', return_value={'cpu': ['Тестовый CPU'], 'gpu': [], 'ram_gb': 0}), \
            patch('app.ensure_closed'), patch('pvp_ui.ensure_closed'), patch('features_ui.game_running', return_value=True), \
            patch('experience.ensure_closed'):
        window = app.Studio()
        errors = []
        window.report_callback_exception = lambda *args: errors.append(str(args))
        window.update()
        for page in window.nav:
            window.show(page)
            window.update()
            assert window.body.winfo_children(), page
        assert len(window.nav) == 12
        window.show('Профили из игры')
        window.capture_name.insert(0, 'Проверка профиля')
        window.capture_now()
        record = window.captures.records()[0]
        window.select_capture(record)
        window.choose('PvP')
        for deferred in [False, True]:
            window.preview(deferred=deferred)
            window.update()
            modal = [w for w in window.winfo_children() if isinstance(w, app.ctk.CTkToplevel)][0]
            modal.destroy()
            window.engine_preview(deferred=deferred)
            window.update()
            modal = [w for w in window.winfo_children() if isinstance(w, app.ctk.CTkToplevel)][0]
            modal.destroy()
        window.show('Нагрузка ПК')
        window.monitor_samples.append({'time': '12:00:00', 'running': True, 'gpu_3d': 45,
            'cpu_total': 30, 'cpu_game': 10, 'game_ram_bytes': 1024**3, 'free_ram_kb': 2*1024**2})
        window.render_monitor()
        window.update()
        window.pvp_engine_preview()
        window.update()
        modal = [w for w in window.winfo_children() if isinstance(w, app.ctk.CTkToplevel)][0]
        modal.destroy()
        assert '1.00' in window.monitor_widgets['game_ram'].cget('text')
        assert not errors, errors
        assert config.read_bytes() == fixture()
        assert (config.parent / 'Engine.ini').read_bytes() == SOURCE
        assert dat.read_bytes() == b'\xe1\x52\x81\x6e' * 40
        window.show('Во время игры')
        window.update()
        assert window.live_button.cget('text') == 'Начать наблюдение'
        print('UI OK: 12 pages, captures, live config monitor, 5 preview dialogs, telemetry chart; source files unchanged')
        window.destroy()
