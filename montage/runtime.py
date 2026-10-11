from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
APP_DIR = Path(sys.executable).parent if getattr(sys, 'frozen', False) else ROOT


def asset(name: str) -> Path:
    return ROOT / 'assets' / name


def data_dir() -> Path:
    override = os.environ.get('MONTAGE_DATA_DIR')
    path = Path(override) if override else APP_DIR / 'data'
    try:
        path.mkdir(parents=True, exist_ok=True)
        test = path / '.write_test'
        test.write_text('ok')
        test.unlink()
    except OSError:
        path = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'MontageStudio'
        path.mkdir(parents=True, exist_ok=True)
    return path


def binary(name: str) -> str:
    bundled = asset('bin') / (name + '.exe')
    if bundled.is_file():
        return str(bundled)
    found = shutil.which(name)
    if found and not getattr(sys, 'frozen', False):
        return found
    raise RuntimeError(f'缺少视频组件 {name}，请重新解压完整软件包。')


def self_command(*args: str) -> list[str]:
    if getattr(sys, 'frozen', False):
        return [sys.executable, *args]
    return [sys.executable, str(ROOT / 'main.py'), *args]


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, path)
