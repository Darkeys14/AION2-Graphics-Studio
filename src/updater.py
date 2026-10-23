"""Fixed-repository GitHub release updater. Download integrity, per-user installer, no elevated helper."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request
from urllib.parse import urlparse
from core import SafetyError, atomic_write
from version import VERSION

REPO = 'Darkeys14/AION2-Graphics-Studio'
LATEST = f'https://api.github.com/repos/{REPO}/releases/latest'
HEADERS = {'Accept': 'application/vnd.github+json', 'User-Agent': 'AION2GraphicsStudio/' + VERSION}


def version_tuple(value):
    if not re.fullmatch(r'v?\d+\.\d+\.\d+', value):
        raise SafetyError('Неподдерживаемый номер версии релиза.')
    return tuple(int(part) for part in value.lstrip('v').split('.'))


def validate_release(release, current=VERSION):
    if release.get('draft') or release.get('prerelease'):
        raise SafetyError('Предварительный или неопубликованный релиз пропущен.')
    tag = release.get('tag_name', '')
    version_tuple(tag)
    if not tag.startswith('v'):
        raise SafetyError('Неподдерживаемый тег релиза.')
    if version_tuple(tag) <= version_tuple(current):
        return None
    name = f'AION2-Graphics-Studio-{tag[1:]}-Setup.exe'
    assets = release.get('assets', [])
    def asset(expected, limit):
        matches = [a for a in assets if a.get('name') == expected]
        if len(matches) != 1:
            raise SafetyError('В релизе нет однозначного установщика или контрольной суммы.')
        result = matches[0]
        url = f'https://github.com/{REPO}/releases/download/{tag}/{expected}'
        if result.get('browser_download_url') != url or not 0 < result.get('size', 0) <= limit:
            raise SafetyError('Источник или размер обновления не прошёл проверку.')
        return result
    setup = asset(name, 150 * 1024 * 1024)
    checksums = asset('SHA256SUMS.txt', 32 * 1024)
    return {'version': tag[1:], 'setup': setup, 'checksums': checksums}


def open_url(url):
    response = urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=15)
    final = urlparse(response.geturl())
    if final.scheme != 'https' or final.hostname not in {
        'github.com', 'api.github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}:
        response.close()
        raise SafetyError('Неожиданный адрес загрузки обновления.')
    return response


def expected_hash(data, name):
    found = []
    for line in data.decode('ascii').splitlines():
        match = re.fullmatch(r'([a-fA-F0-9]{64})\s+\*?([^/\\]+)', line.strip())
        if match and match[2] == name:
            found.append(match[1].lower())
    if len(found) != 1:
        raise SafetyError('Не найдена однозначная контрольная сумма установщика.')
    return found[0]


def check_and_download(root, current=VERSION):
    with open_url(LATEST) as response:
        raw = response.read(256 * 1024 + 1)
    if len(raw) > 256 * 1024:
        raise SafetyError('Слишком большой ответ GitHub.')
    info = validate_release(json.loads(raw), current)
    if info is None:
        return None
    with open_url(info['checksums']['browser_download_url']) as response:
        sums = response.read(32 * 1024 + 1)
    if len(sums) > 32 * 1024:
        raise SafetyError('Файл контрольных сумм превышает допустимый размер.')
    wanted = expected_hash(sums, info['setup']['name'])
    folder = Path(root) / 'updates' / info['version']
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / info['setup']['name']
    temporary = folder / (info['setup']['name'] + '.part')
    started, total, sha = time.monotonic(), 0, hashlib.sha256()
    try:
        with open_url(info['setup']['browser_download_url']) as response, temporary.open('wb') as stream:
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > info['setup']['size'] or time.monotonic() - started > 180:
                    raise SafetyError('Загрузка обновления превысила ограничения.')
                sha.update(chunk)
                stream.write(chunk)
            stream.flush()
            os.fsync(stream.fileno())
        if total != info['setup']['size'] or sha.hexdigest() != wanted:
            raise SafetyError('Контрольная сумма или размер обновления не совпадает. Запуск запрещён.')
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {'version': info['version'], 'path': str(target), 'sha256': wanted}


def installed_folder():
    if getattr(sys, 'frozen', False):
        folder = Path(sys.executable).resolve().parent
        if (folder / 'unins000.exe').is_file():
            return folder
    return None


def launch_installer_after_exit(root, update, folder):
    installer = Path(update['path']).resolve(strict=True)
    expected = Path(root).resolve() / 'updates' / update['version'] / f"AION2-Graphics-Studio-{update['version']}-Setup.exe"
    if installer != expected or hashlib.sha256(installer.read_bytes()).hexdigest() != update['sha256']:
        raise SafetyError('Подготовленный установщик изменился. Обновление заблокировано.')
    if installed_folder() != Path(folder):
        raise SafetyError('Автообновление доступно только установленной версии.')
    # Fixed script plus environment data: paths are never evaluated as commands.
    command = r"""
$ErrorActionPreference='Stop'
$studioState=Join-Path $env:AION2_UPDATE_ROOT 'update-status.json'
try {
  $studioParent=Get-Process -Id ([int]$env:AION2_UPDATE_PARENT) -ErrorAction SilentlyContinue
  if ($studioParent) { $studioParent.WaitForExit() }
  $studioAlgorithm=[System.Security.Cryptography.SHA256]::Create()
  $studioStream=[System.IO.File]::OpenRead($env:AION2_UPDATE_INSTALLER)
  try {
    $studioHash=([System.BitConverter]::ToString($studioAlgorithm.ComputeHash($studioStream))).Replace('-','').ToLowerInvariant()
  } finally {
    $studioStream.Dispose()
    $studioAlgorithm.Dispose()
  }
  if ($studioHash -ne $env:AION2_UPDATE_HASH) { throw 'Installer hash mismatch' }
  $studioArgs=@('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',('/DIR="'+$env:AION2_UPDATE_FOLDER+'"'))
  $studioSetup=Start-Process -FilePath $env:AION2_UPDATE_INSTALLER -ArgumentList $studioArgs -WindowStyle Hidden -Wait -PassThru
  if ($studioSetup.ExitCode -ne 0) { throw ('Installer exit code: '+$studioSetup.ExitCode) }
  @{ok=$true; version=$env:AION2_UPDATE_VERSION} | ConvertTo-Json | Set-Content -LiteralPath $studioState -Encoding UTF8
  Start-Process -FilePath (Join-Path $env:AION2_UPDATE_FOLDER 'AION2GraphicsStudio.exe') -WorkingDirectory $env:AION2_UPDATE_FOLDER -WindowStyle Hidden
} catch {
  @{ok=$false; message=$_.Exception.Message} | ConvertTo-Json | Set-Content -LiteralPath $studioState -Encoding UTF8
}
"""
    environment = os.environ.copy()
    # A parent PowerShell 7 session may export module paths incompatible with Windows PowerShell.
    environment.pop('PSModulePath', None)
    environment.update(AION2_UPDATE_ROOT=str(Path(root).resolve()), AION2_UPDATE_PARENT=str(os.getpid()),
                       AION2_UPDATE_INSTALLER=str(installer), AION2_UPDATE_HASH=update['sha256'],
                       AION2_UPDATE_FOLDER=str(folder), AION2_UPDATE_VERSION=update['version'])
    return subprocess.Popen(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                            env=environment, creationflags=subprocess.CREATE_NO_WINDOW,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
