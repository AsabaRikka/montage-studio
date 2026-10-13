"""Small helpers for the default one-click workflow and disposable caches."""
import os
import shutil
from pathlib import Path

CACHE_NAMES = ('cache', 'previews', 'frame_previews')
MAX_BATCH = 100000


def available_count(intros, mains, excluded=()):
    a, b = set(intros), set(mains)
    return len(a) * len(b) - sum(x in a and y in b for x, y in set(excluded))


def directory_size(path):
    path = Path(path)
    if path.is_symlink() or path.is_junction():
        return 0
    total = 0
    for root, dirs, files in os.walk(path, followlinks=False):
        dirs[:] = [d for d in dirs if not Path(root, d).is_symlink() and not Path(root, d).is_junction()]
        for name in files:
            p = Path(root, name)
            try:
                if not p.is_symlink():
                    total += p.stat().st_size
            except OSError:
                pass  # A background preview may have just removed this file.
    return total


def cache_sizes(folder):
    folder = Path(folder)
    return dict(processing=sum(directory_size(folder / n) for n in CACHE_NAMES),
                cloud=directory_size(folder / 'cloud'), thumbnails=directory_size(folder / 'thumbnails'))


def clear_processing_cache(folder):
    folder = Path(folder).resolve()
    for name in CACHE_NAMES:
        target = folder / name
        if target.is_symlink() or target.is_junction():
            raise ValueError('缓存目录是链接，请先检查数据目录：' + name)
        if not target.resolve().is_relative_to(folder):
            raise ValueError('缓存目录超出数据目录。')
        if target.exists():
            shutil.rmtree(target)


def human_size(size):
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size < 1024 or unit == 'TB':
            return f'{size:.1f} {unit}'
        size /= 1024
