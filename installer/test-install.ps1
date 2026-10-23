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
$studioUninstaller = Join-Path $studioInstallDir 'unins000.exe'
$studioUninstall = Start-Process -FilePath $studioUninstaller -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') -WindowStyle Hidden -Wait -PassThru
if ($studioUninstall.ExitCode -ne 0) { throw "Удаление завершилось с кодом $($studioUninstall.ExitCode)" }
if (Test-Path -LiteralPath $studioExe) { throw 'Приложение осталось после удаления' }
if (-not (Test-Path -LiteralPath $studioSentinel)) { throw 'Удаление затронуло пользовательские данные' }
Write-Output 'Установка, запуск, удаление и сохранность пользовательских данных проверены.'
