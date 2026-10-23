# Установщик Windows

`setup.iss` собирает установщик для текущего пользователя без прав администратора. Требуется Inno Setup 6.6+ и готовая папка `dist/AION2GraphicsStudio` после выполнения `build.ps1`.

```powershell
ISCC.exe installer/setup.iss
```

Результат: `release/AION2-Graphics-Studio-0.2.0-Setup.exe`.

`test-install.ps1` предназначен для изолированного Windows runner: проверяет установку в RUNNER_TEMP, совпадение хеша исполняемого файла, запуск приложения, удаление и сохранность пользовательских данных. На личном компьютере этот тест автоматически запускать не нужно.

Workflow Windows installer and release выполняет сборку, проверки и публикацию в GitHub Releases. Его также можно запустить вручную через Actions → Windows installer and release → Run workflow. При уже существующем релизе повторная публикация этого же тега остановится с ошибкой, не заменяя существующие файлы.

Удаление через Windows не затрагивает `%LOCALAPPDATA%/AION2GraphicsStudio` и файлы игры.
