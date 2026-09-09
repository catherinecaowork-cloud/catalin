"""事件广播。

P0 是内网单机，订阅者与缓冲放进程内存即可，不引 Redis。
将来要多副本时，只需替换本模块的实现——会话与令牌都没放内存，认证不受影响。
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any


class EventHub:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)
        # 有新任务入队时唤醒正在长轮询的 Worker，避免白等一个轮询周期
        self._job_signal = asyncio.Event()

    def subscribe(self, run_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1000)
        self._subscribers[run_id].add(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        subscribers = self._subscribers.get(run_id)
        if not subscribers:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(run_id, None)

    def publish(self, run_id: str, payload: dict[str, Any]) -> None:
        for queue in list(self._subscribers.get(run_id, ())):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                # 慢订阅者不能拖住执行侧；它重连后会从快照补齐
                self.unsubscribe(run_id, queue)

    def notify_new_job(self) -> None:
        self._job_signal.set()

    async def wait_for_job(self, timeout: float) -> None:
        try:
            await asyncio.wait_for(self._job_signal.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return
        finally:
            self._job_signal.clear()


hub = EventHub()
