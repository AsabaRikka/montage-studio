"""Bounded, serial background thumbnail generation with content-keyed caching."""
import os
import queue
import subprocess
import threading
import time
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from .runtime import binary, data_dir


class ThumbnailLoader(QThread):
    ready = Signal(str, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.stop = threading.Event()
        self.requests = queue.Queue()
        self.pending = set()
        self.lock = threading.Lock()
        self.folder = data_dir() / 'thumbnails'
        self.folder.mkdir(parents=True, exist_ok=True)

    def path(self, key):
        return self.folder / (key + '.jpg')

    def submit(self, asset):
        with self.lock:
            if asset['id'] in self.pending:
                return
            self.pending.add(asset['id'])
        self.requests.put(dict(asset))

    def run(self):
        while not self.stop.is_set():
            try:
                asset = self.requests.get(timeout=.15)
            except queue.Empty:
                continue
            key = asset['id']; target = self.path(key)
            temp = target.with_suffix('.tmp.jpg')
            process = None
            try:
                if not target.exists():
                    if self.stop.is_set():
                        break
                    seconds = min(.8, max(0, asset['duration'] * .1))
                    args = [binary('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
                            '-ss', str(seconds), '-threads', '1', '-i', asset['path'],
                            '-vf', 'scale=88:104:force_original_aspect_ratio=decrease,pad=88:104:(ow-iw)/2:(oh-ih)/2:color=0x14213b',
                            '-frames:v', '1', '-threads', '1', str(temp)]
                    flags = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS if os.name == 'nt' else 0
                    process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                               stderr=subprocess.DEVNULL, creationflags=flags)
                    deadline = time.monotonic() + 15
                    while process.poll() is None:
                        if self.stop.wait(.05) or time.monotonic() > deadline:
                            raise RuntimeError('缩略图已停止或超时')
                    if process.returncode or not temp.is_file():
                        raise RuntimeError('无法读取视频画面')
                    os.replace(temp, target)
                if not self.stop.is_set():
                    self.ready.emit(key, str(target), '')
            except Exception as exc:
                if not self.stop.is_set():
                    self.ready.emit(key, '', str(exc))
            finally:
                if process and process.poll() is None:
                    process.kill(); process.wait()
                temp.unlink(missing_ok=True)
                with self.lock:
                    self.pending.discard(key)

    def shutdown(self):
        self.stop.set()
        self.wait()
