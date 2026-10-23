$ErrorActionPreference = 'Stop'
$studioSetup = (Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot '..\release') -Filter '*-Setup.exe' | Select-Object -First 1).FullName
if (-not $studioSetup) { throw 'Установщик не найден' }
$studioInstallDir = Join-Path $env:RUNNER_TEMP 'AION2GraphicsStudio-InstallTest'
$studioData = Join-Path $env:LOCALAPPDATA 'AION2GraphicsStudio'
New-Item -ItemType Directory -Force -Path $studioData | Out-Null
$studioSentinel = Join-Path $studioData 'installer-test-preserve.txt'
Set-Content -LiteralPath $studioSentinel -Value 'preserve backups on uninstall' -Encoding utf8
$studioInstall = Start-Process -FilePath $studioSetup -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/DIR=`"$studioInstallDir`"") -WindowStyle Hidden -Wait -PassThru
if ($studioInstall.ExitCode -ne 0) { throw "Установка завершилась с кодом $($studioInstall.ExitCode)" }
$studioExe = Join-Path $studioInstallDir 'AION2GraphicsStudio.exe'
if (-not (Test-Path -LiteralPath $studioExe)) { throw 'Приложение не установлено' }
$studioExpectedHash = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot '..\dist\AION2GraphicsStudio\AION2GraphicsStudio.exe')).Hash
if ((Get-FileHash -LiteralPath $studioExe).Hash -ne $studioExpectedHash) { throw 'Установленный файл не совпадает со сборкой' }
$studioApp = Start-Process -FilePath $studioExe -WorkingDirectory $studioInstallDir -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 8
$studioApp.Refresh()
if ($studioApp.HasExited) { throw 'Установленное приложение завершилось при запуске' }
Stop-Process -Id $studioApp.Id
python (Join-Path $PSScriptRoot 'test-update-helper.py') $studioData $studioInstallDir $studioSetup
if ($LASTEXITCODE -ne 0) { throw 'Не удалось запустить тест помощника обновления' }
$studioUpdateState=Join-Path $studioData 'update-status.json'
$studioUpdateDeadline=(Get-Date).AddSeconds(90)
while (-not (Test-Path -LiteralPath $studioUpdateState)) {
    if ((Get-Date) -gt $studioUpdateDeadline) { throw 'Помощник обновления не завершил установку' }
    Start-Sleep -Seconds 2
}
$studioUpdateReport=Get-Content -LiteralPath $studioUpdateState -Raw | ConvertFrom-Json
if (-not $studioUpdateReport.ok) { throw "Ошибка автообновления: $($studioUpdateReport.message)" }
Start-Sleep -Seconds 4
$studioRestarted=@(Get-Process -Name AION2GraphicsStudio -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $studioExe })
if (-not $studioRestarted.Count) { throw 'После обновления приложение не запустилось' }
if (-not (Test-Path -LiteralPath $studioSentinel)) { throw 'Обновление затронуло пользовательские данные' }
$studioRestarted | Stop-Process
$studioUninstaller = Join-Path $studioInstallDir 'unins000.exe'
$studioUninstall = Start-Process -FilePath $studioUninstaller -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') -WindowStyle Hidden -Wait -PassThru
if ($studioUninstall.ExitCode -ne 0) { throw "Удаление завершилось с кодом $($studioUninstall.ExitCode)" }
if (Test-Path -LiteralPath $studioExe) { throw 'Приложение осталось после удаления' }
if (-not (Test-Path -LiteralPath $studioSentinel)) { throw 'Удаление затронуло пользовательские данные' }
Write-Output 'Установка, запуск, помощник автообновления, перезапуск, удаление и сохранность данных проверены.'
