"""Read actual Windows hardware without administrator rights or network access."""
import json
import subprocess
import winreg


def vram_from_registry(name):
    base = r'SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}'
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as key:
            for index in range(winreg.QueryInfoKey(key)[0]):
                child = winreg.EnumKey(key, index)
                try:
                    with winreg.OpenKey(key, child) as adapter:
                        desc = winreg.QueryValueEx(adapter, 'DriverDesc')[0]
                        if desc.casefold() != name.casefold():
                            continue
                        memory = winreg.QueryValueEx(adapter, 'HardwareInformation.qwMemorySize')[0]
                        if isinstance(memory, bytes):
                            memory = int.from_bytes(memory, 'little')
                        if int(memory) > 0:
                            return round(int(memory) / (1024 ** 3), 1)
                except OSError:
                    continue
    except OSError:
        pass
    return None


def scan():
    command = """
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
$cpus=@(Get-CimInstance Win32_Processor | ForEach-Object { $_.Name.Trim() })
$gpus=@(Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name.Trim() })
$memory=(Get-CimInstance Win32_PhysicalMemory | Measure-Object -Property Capacity -Sum).Sum
@{cpu=$cpus; gpu=$gpus; ram_bytes=$memory} | ConvertTo-Json -Compress
"""
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                            capture_output=True, timeout=25, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError('Windows не предоставила сведения об оборудовании.')
    info = json.loads(result.stdout.decode('utf-8-sig'))
    return {'cpu': info.get('cpu') or [], 'gpu': [
        {'name': name, 'vram_gb': vram_from_registry(name)} for name in info.get('gpu', [])],
            'ram_gb': round(float(info.get('ram_bytes') or 0) / 1024 ** 3, 1)}
