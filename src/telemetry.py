"""Low-rate Windows counters; no injection, hooks, driver installation or game memory reads."""
import json
import subprocess
from datetime import datetime


def sample():
    command = r"""
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
$games=@(Get-CimInstance Win32_Process -Filter "Name='AION2.exe' OR Name='Aion2-Win64-Shipping.exe' OR Name='Aion2-Win64-Test.exe'")
$ids=@($games | ForEach-Object { [int]$_.ProcessId })
$os=Get-CimInstance Win32_OperatingSystem
$gpu=$null
$cpu=$null
$gameCpu=$null
try {
  $engines=@(Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine -ErrorAction Stop | Where-Object {
    $_.Name -match '^pid_(\d+)_.*engtype_3D$' -and $ids -contains [int]$Matches[1]
  })
  if ($engines.Count) { $gpu=($engines | Measure-Object UtilizationPercentage -Maximum).Maximum }
} catch {}
try {
  $cpu=(Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor -Filter "Name='_Total'" -ErrorAction Stop).PercentProcessorTime
  $logical=(Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors
  $perf=@(Get-CimInstance Win32_PerfFormattedData_PerfProc_Process -ErrorAction Stop | Where-Object { $ids -contains [int]$_.IDProcess })
  if ($perf.Count -and $logical -gt 0) { $gameCpu=($perf | Measure-Object PercentProcessorTime -Sum).Sum / $logical }
} catch {}
$working=($games | Measure-Object WorkingSetSize -Sum).Sum
@{running=($games.Count -gt 0); game_ram_bytes=$working; free_ram_kb=$os.FreePhysicalMemory; total_ram_kb=$os.TotalVisibleMemorySize; gpu_3d=$gpu; cpu_total=$cpu; cpu_game=$gameCpu} | ConvertTo-Json -Compress
"""
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                            capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError('Счётчики Windows сейчас недоступны.')
    data = json.loads(result.stdout.decode('utf-8-sig'))
    data['time'] = datetime.now().astimezone().strftime('%H:%M:%S')
    for key in ['gpu_3d', 'cpu_total', 'cpu_game']:
        if data.get(key) is not None:
            data[key] = max(0.0, min(100.0, float(data[key])))
    return data
