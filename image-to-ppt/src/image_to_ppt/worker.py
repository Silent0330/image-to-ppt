"""在背景執行緒執行耗時工作，並以型別化事件回報進度。"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Callable, Union


@dataclass(frozen=True)
class Progress:
    done: int
    total: int


@dataclass(frozen=True)
class Succeeded:
    result: object


@dataclass(frozen=True)
class Failed:
    message: str


Event = Union[Progress, Succeeded, Failed]


class BackgroundJob:
    """以執行緒執行 ``work(progress)``；事件可透過 :meth:`drain` 非阻塞取出。"""

    def __init__(self, work: Callable[[Callable[[int, int], None]], object]) -> None:
        self._work = work
        self._queue: "queue.Queue[Event]" = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def drain(self) -> list[Event]:
        events: list[Event] = []
        try:
            while True:
                events.append(self._queue.get_nowait())
        except queue.Empty:
            pass
        return events

    def _run(self) -> None:
        try:
            self._queue.put(Succeeded(self._work(self._report)))
        except Exception as exc:  # noqa: BLE001 - 任何失敗都要回報給 UI
            self._queue.put(Failed(str(exc)))

    def _report(self, done: int, total: int) -> None:
        self._queue.put(Progress(done, total))
