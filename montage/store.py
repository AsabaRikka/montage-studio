from __future__ import annotations
import hashlib
import json
import sqlite3
import time
import uuid
from pathlib import Path
from .runtime import data_dir
from .naming import output_names


def identity(path):
    """Content hash survives renames/moves; re-encoded files count as new content."""
    h = hashlib.sha256()
    with open(path, 'rb') as source:
        for block in iter(lambda: source.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


class Store:
    def __init__(self, folder=None):
        self.folder = Path(folder) if folder else data_dir()
        self.folder.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.folder/'history.sqlite3', timeout=30)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS batches(id TEXT PRIMARY KEY, game TEXT NOT NULL, created REAL, settings TEXT, assets TEXT, name TEXT);
        CREATE TABLE IF NOT EXISTS jobs(batch TEXT, number INTEGER, a TEXT, b TEXT, settings TEXT, status TEXT, output TEXT, error TEXT, PRIMARY KEY(batch,number));
        CREATE TABLE IF NOT EXISTS history(game TEXT, a TEXT, b TEXT, batch TEXT, number INTEGER, output TEXT, completed REAL, PRIMARY KEY(game,a,b));
        CREATE TABLE IF NOT EXISTS reservations(game TEXT, a TEXT, b TEXT, batch TEXT, PRIMARY KEY(game,a,b));
        ''')
        self.db.commit()

    def close(self):
        self.db.close()

    def excluded(self, game):
        return set(self.db.execute('SELECT a,b FROM history WHERE game=? UNION SELECT a,b FROM reservations WHERE game=?', (game, game)))

    def create(self, game, assets, pairs, settings, per_job, name=''):
        if not game.strip():
            raise ValueError('请填写游戏名称，用于分组历史。')
        game = game.strip()
        if not pairs or len(pairs) != len(per_job) or len(set(pairs)) != len(pairs):
            raise ValueError('任务计划为空、设置数量不符或存在重复配对。')
        if any(a not in assets or b not in assets for a, b in pairs):
            raise ValueError('任务包含未知素材。')
        bid = uuid.uuid4().hex
        created = time.time()
        names = output_names(assets, pairs, settings['naming_rule']) if 'naming_rule' in settings else None
        try:
            self.db.execute('BEGIN IMMEDIATE')
            if set(pairs) & self.excluded(game):
                raise ValueError('配对已被历史或另一个任务使用，请重新生成计划。')
            self.db.execute('INSERT INTO batches VALUES(?,?,?,?,?,?)', (bid, game, created, json.dumps(settings, ensure_ascii=False), json.dumps(assets, ensure_ascii=False), name))
            for number, ((a, b), custom) in enumerate(zip(pairs, per_job), 1):
                custom = dict(custom)
                if names is not None: custom['output_name'] = names[number-1]
                self.db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)', (bid, number, a, b, json.dumps(custom, ensure_ascii=False), 'pending', '', ''))
                self.db.execute('INSERT INTO reservations VALUES(?,?,?,?)', (game, a, b, bid))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return bid

    def batch(self, bid):
        row = self.db.execute('SELECT id,game,created,settings,assets,name FROM batches WHERE id=?', (bid,)).fetchone()
        if not row:
            raise ValueError('任务不存在。')
        return dict(id=row[0], game=row[1], created=row[2], settings=json.loads(row[3]), assets=json.loads(row[4]), name=row[5])

    def jobs(self, bid):
        return [dict(number=r[0], a=r[1], b=r[2], settings=json.loads(r[3]), status=r[4], output=r[5], error=r[6]) for r in self.db.execute('SELECT number,a,b,settings,status,output,error FROM jobs WHERE batch=? ORDER BY number', (bid,))]

    def batches(self):
        return list(self.db.execute('SELECT b.id,b.game,b.created,b.name,COUNT(j.number),SUM(j.status="complete") FROM batches b LEFT JOIN jobs j ON j.batch=b.id GROUP BY b.id ORDER BY b.created DESC'))

    def update(self, bid, number, status, output='', error=''):
        if status not in ('pending', 'running', 'complete', 'failed', 'cancelled'):
            raise ValueError('未知任务状态。')
        with self.db:
            row = self.db.execute('SELECT status FROM jobs WHERE batch=? AND number=?', (bid, number)).fetchone()
            if not row or row[0] == 'cancelled':
                raise ValueError('任务已放弃或不存在。')
            if row[0] == 'complete':
                raise ValueError('已完成的成片不能重新写入任务状态。')
            self.db.execute('UPDATE jobs SET status=?,output=?,error=? WHERE batch=? AND number=?', (status, output, error, bid, number))
            if status == 'complete':
                game = self.batch(bid)['game']
                job = self.db.execute('SELECT a,b FROM jobs WHERE batch=? AND number=?', (bid, number)).fetchone()
                self.db.execute('INSERT OR IGNORE INTO history VALUES(?,?,?,?,?,?,?)', (game, *job, bid, number, output, time.time()))
                self.db.execute('DELETE FROM reservations WHERE game=? AND a=? AND b=? AND batch=?', (game, *job, bid))

    def abandon(self, bid):
        with self.db:
            self.db.execute('DELETE FROM reservations WHERE batch=?', (bid,))
            self.db.execute('UPDATE jobs SET status="cancelled" WHERE batch=? AND status!="complete"', (bid,))

    def backup(self, path):
        if Path(path).resolve() == (self.folder/'history.sqlite3').resolve():
            raise ValueError('请将备份保存到不同文件。')
        target = sqlite3.connect(path)
        try:
            self.db.backup(target)
        finally:
            target.close()

    def restore(self, path):
        if Path(path).resolve() == (self.folder/'history.sqlite3').resolve():
            raise ValueError('请选择独立备份文件。')
        source = sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True)
        try:
            for table in ('batches', 'jobs', 'history', 'reservations'):
                source.execute(f'SELECT * FROM {table} LIMIT 1')
            if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('备份数据库损坏。')
            self.backup(self.folder/f'before_restore_{int(time.time())}.sqlite3')
            source.backup(self.db)
        finally:
            source.close()

    def history(self, game=''):
        return list(self.db.execute('SELECT game,a,b,completed,output FROM history WHERE (?="" OR game=?) ORDER BY completed DESC', (game, game)))

    def delete_history(self, game, a, b):
        """Remove one history index entry while preserving its output and task."""
        return self.delete_histories([(game,a,b)])

    def delete_histories(self, records):
        """Delete selected keys atomically; never alter reservations or jobs."""
        with self.db:
            return sum(self.db.execute('DELETE FROM history WHERE game=? AND a=? AND b=?', record).rowcount for record in set(records))

    def relocate(self, bid, key, path):
        if identity(path) != key:
            raise ValueError('替换文件内容不同，请选回原素材。')
        batch = self.batch(bid)
        batch['assets'][key]['path'] = str(Path(path).resolve())
        with self.db:
            self.db.execute('UPDATE batches SET assets=? WHERE id=?', (json.dumps(batch['assets'], ensure_ascii=False), bid))
