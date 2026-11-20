"""内存与 CPU 采样。

统一入口 sample()，结果缓存几秒，避免每次请求都重算 CPU（百分比必须两次采样）。
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

import psutil

CACHE_SECONDS = 3.0


@dataclass
class Metrics:
    ts: float = 0.0
    host: dict[str, Any] = field(default_factory=dict)
    panel: dict[str, Any] = field(default_factory=dict)
    instances: dict[str, dict[str, Any]] = field(default_factory=dict)


class MetricsSampler:
    def __init__(self, cache_seconds: float = CACHE_SECONDS) -> None:
        self.cache_seconds = cache_seconds
        self._cached: Metrics | None = None
        self._panel = psutil.Process(os.getpid())
        self._panel.cpu_percent(None)
        psutil.cpu_percent(None)

    def sample(self, processes: dict[str, int] | None = None) -> Metrics:
        processes = processes or {}
        now = time.time()
        cached = self._cached
        if cached and now - cached.ts < self.cache_seconds and set(cached.instances) == set(processes):
            return cached

        memory = psutil.virtual_memory()
        metrics = Metrics(ts=now)
        metrics.host = {
            "total_mb": round(memory.total / (1 << 20)),
            "used_mb": round((memory.total - memory.available) / (1 << 20)),
            "percent": round(memory.percent, 1),
            "cpu_percent": round(psutil.cpu_percent(None), 1),
            "cores": psutil.cpu_count(logical=True) or 0,
        }

        try:
            metrics.panel = {
                "rss_mb": round(self._panel.memory_info().rss / (1 << 20), 1),
                "cpu_percent": round(self._panel.cpu_percent(None), 1),
                "threads": self._panel.num_threads(),
            }
        except psutil.Error:
            metrics.panel = {"rss_mb": 0, "cpu_percent": 0, "threads": 0}

        for instance_id, pid in processes.items():
            if not pid:
                continue
            try:
                proc = psutil.Process(pid)
                memory_info = proc.memory_info()
                metrics.instances[instance_id] = {
                    "rss_mb": round(memory_info.rss / (1 << 20), 1),
                    "cpu_percent": round(proc.cpu_percent(None), 1),
                    "threads": proc.num_threads(),
                }
            except psutil.Error:
                continue

        self._cached = metrics
        return metrics

    def to_dict(self, processes: dict[str, int] | None = None) -> dict[str, Any]:
        metrics = self.sample(processes)
        return {
            "host": metrics.host,
            "panel": metrics.panel,
            "instances": metrics.instances,
            "age_s": round(time.time() - metrics.ts, 1),
        }
