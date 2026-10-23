"""PresentMon Present cadence analysis. Does not infer scene or mix processes/swapchains."""
import csv
from collections import defaultdict
import math
from pathlib import Path
import re
import statistics
from core import SafetyError


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (ValueError, TypeError):
        return None


def analyze(path, trim_start=5.0, trim_end=3.0):
    path = Path(path)
    if path.stat().st_size > 100 * 1024 * 1024:
        raise SafetyError('CSV превышает предел 100 МБ.')
    groups = defaultdict(list)
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames or []
        required = {'Application', 'ProcessID', 'SwapChainAddress', 'MsBetweenPresents'}
        if not required <= set(columns):
            raise SafetyError('Нужен CSV PresentMon с MsBetweenPresents, процессом и swapchain.')
        time_key = next((key for key in ['TimeInMs', 'CPUStartTimeInMs', 'CPUStartTime', 'TimeInSeconds'] if key in columns), None)
        if time_key is None:
            raise SafetyError('В CSV нет поддерживаемого времени записи.')
        scale = 1000 if time_key == 'TimeInSeconds' else 1
        for index, row in enumerate(reader):
            if index > 500000:
                raise SafetyError('Слишком много строк в CSV (предел 500 тысяч).')
            if not re.fullmatch(r'aion2(?:[-_.].*)?\.exe', row.get('Application', ''), re.I):
                continue
            stamp, frame = number(row.get(time_key)), number(row.get('MsBetweenPresents'))
            if stamp is None or frame is None or frame <= 0:
                continue
            groups[(row['ProcessID'], row['SwapChainAddress'])].append((stamp * scale, frame, row))
    if not groups:
        raise SafetyError('В CSV нет пригодных кадров AION 2.')
    key, frames = max(groups.items(), key=lambda item: len(item[1]))
    frames.sort(key=lambda item: item[0])
    first, last = frames[0][0], frames[-1][0]
    chosen = [item for item in frames if first + trim_start * 1000 <= item[0] <= last - trim_end * 1000]
    if len(chosen) < 120 or last - first < 20000:
        raise SafetyError('Недостаточно кадров или запись короче 20 секунд. Сделайте замер 60 секунд.')
    durations = sorted(item[1] for item in chosen)
    def percentile(value):
        return durations[min(len(durations) - 1, math.ceil(len(durations) * value) - 1)]
    def mean_column(name):
        values = [number(item[2].get(name)) for item in chosen]
        values = [value for value in values if value is not None]
        return statistics.mean(values) if values else None
    slow = durations[-max(1, math.ceil(len(durations) * .01)):]
    return {'file': path.name, 'process_id': key[0], 'frames': len(chosen),
            'groups': len(groups), 'duration_s': (chosen[-1][0] - chosen[0][0]) / 1000,
            'average_fps': 1000 / statistics.mean(durations),
            'one_percent_low': 1000 / statistics.mean(slow),
            'p95_ms': percentile(.95), 'p99_ms': percentile(.99),
            'frames_over_50ms': sum(value > 50 for value in durations),
            'cpu_busy_ms': mean_column('MsCPUBusy'), 'gpu_busy_ms': mean_column('MsGPUBusy'),
            'trim_start_s': trim_start, 'trim_end_s': trim_end, 'metric': 'MsBetweenPresents'}


def compare(before, after):
    if before['metric'] != after['metric']:
        raise SafetyError('Метрики двух замеров различаются.')
    return {key: (after[key] / before[key] - 1) * 100 for key in ['average_fps', 'one_percent_low']}
