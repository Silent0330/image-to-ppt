"""在背景執行緒執行耗時工作，並以型別化事件回報進度。"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Callable, Union


@dataclass(frozen=True)
class Progress:
    """某個項目（第 ``index``／共 ``total`` 筆）的進度事件，``inner`` 為內容。"""

    index: int
    total: int
    inner: object


@dataclass(frozen=True)
class Message:
    """給 UI 記錄/顯示的文字訊息。"""

    text: str


@dataclass(frozen=True)
class Succeeded:
    result: object


@dataclass(frozen=True)
class Failed:
    message: str


Event = Union[Progress, Message, Succeeded, Failed]


class BackgroundJob:
    """以執行緒執行 ``work(emit)``；事件可透過 :meth:`drain` 非阻塞取出。

    ``work`` 會收到一個 ``emit`` 函式，可用來推送 :class:`Progress`、
    :class:`Message` 等事件。呼叫 :meth:`cancel` 後，``cancelled`` 會變成
    ``True``，讓工作內容自行決定中止時機。
    """

    def __init__(self, work: Callable[[Callable[[Event], None]], object]) -> None:
        self._work = work
        self._queue: "queue.Queue[Event]" = queue.Queue()
        self._cancel = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

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
            self._queue.put(Succeeded(self._work(self._emit)))
        except Exception as exc:  # noqa: BLE001 - 任何失敗都要回報給 UI
            self._queue.put(Failed(str(exc)))

    def _emit(self, event: Event) -> None:
        self._queue.put(event)
