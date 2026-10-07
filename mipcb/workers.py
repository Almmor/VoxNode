"""后台线程工具：把阻塞操作丢进 QThread，结果通过信号回主线程。"""
from __future__ import annotations

from typing import Any, Callable

from PyQt6.QtCore import QObject, QThread, pyqtSignal


class Worker(QThread):
    done = pyqtSignal(object)
    fail = pyqtSignal(str)

    def __init__(self, fn: Callable[..., Any], *args, parent=None, **kwargs):
        super().__init__(parent)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs

    def run(self) -> None:
        try:
            self.done.emit(self.fn(*self.args, **self.kwargs))
        except Exception as e:
            self.fail.emit(f"{e.__class__.__name__}: {e}")


def run_async(parent: QObject, fn: Callable[..., Any], on_done: Callable, on_fail: Callable,
              *args, **kwargs) -> Worker:
    worker = Worker(fn, *args, parent=parent, **kwargs)
    worker.done.connect(on_done)
    worker.fail.connect(on_fail)
    worker.start()
    return worker
