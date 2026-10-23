$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Не удалось установить зависимости' }
python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Проверки не пройдены' }
python tests/smoke_ui.py
if ($LASTEXITCODE -ne 0) { throw 'Проверка интерфейса не пройдена' }
python -m PyInstaller --noconfirm --clean --windowed --onedir --collect-all customtkinter --icon assets/app.ico --add-data 'assets/app.ico;assets' --name AION2GraphicsStudio --distpath dist --workpath build src/app.py
if ($LASTEXITCODE -ne 0) { throw 'Ошибка сборки' }
