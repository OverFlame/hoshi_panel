"""后台任务与进度。

导入这类耗时操作先返回 job id，界面轮询进度。任务只活在内存里，重启丢失。
"""

from __future__ import annotations

import secrets
import time
from typing import Any


class JobStore:
    def __init__(self, keep: int = 50) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self.keep = keep

    def create(self, kind: str, total: int = 0) -> dict[str, Any]:
        job_id = secrets.token_hex(6)
        job = {
            "id": job_id,
            "kind": kind,
            "phase": "准备中",
            "done": 0,
            "total": total,
            "message": "",
            "finished": False,
            "error": "",
            "result": None,
            "started": time.time(),
        }
        self._jobs[job_id] = job
        self._trim()
        return job

    def _trim(self) -> None:
        if len(self._jobs) <= self.keep:
            return
        finished = sorted(self._jobs.values(), key=lambda item: item["started"])
        for job in finished[: len(self._jobs) - self.keep]:
            self._jobs.pop(job["id"], None)

    def update(self, job_id: str, **fields: Any) -> None:
        job = self._jobs.get(job_id)
        if job is not None:
            job.update(fields)

    def finish(self, job_id: str, result: Any = None, error: str = "") -> None:
        self.update(job_id, finished=True, result=result, error=error, phase="完成" if not error else "失败")

    def get(self, job_id: str) -> dict[str, Any] | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        payload = dict(job)
        payload["percent"] = int(job["done"] * 100 / job["total"]) if job["total"] else 0
        return payload
