"""Read-only Feishu Base library. CLI owns credentials; media remains local."""
from __future__ import annotations
import hashlib
import json
import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

from .core import Cancelled
from .runtime import asset, data_dir, write_json
from .service import scan
from .store import identity

DEFAULT_URL = 'https://my.feishu.cn/wiki/XnEtwZA6GiumPjkzTz2cO8JWnMe?table=tblO61TwuCnAW1mh&view=vewBeeIAM0'
FIELDS = ['描述', '成品文件', '备注', '制作人', '日期', '是否直接可用']
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v'}
READ_SCOPES = 'base:app:read base:table:read base:field:read base:record:read base:view:read wiki:node:read wiki:node:retrieve drive:file:download docs:document.media:download offline_access'


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return default
    except (ValueError, OSError) as exc:
        raise ValueError('云端库本地记录无法读取，请保留文件并检查：'+str(path)) from exc


class FeishuCLI:
    def __init__(self, folder=None, profile=''):
        self.folder = Path(folder or data_dir()/'cloud')
        self.work = self.folder/'work'
        self.work.mkdir(parents=True, exist_ok=True)
        self.profile = profile
        self.executable = asset('bin/lark-cli.exe')

    def call(self, args, stop=None, timeout=120, secret=None, require_json=True):
        if stop and stop.is_set():
            raise Cancelled()
        if not self.executable.is_file():
            raise RuntimeError('缺少飞书连接组件，请重新解压完整软件包。')
        command = [str(self.executable), *args]
        if self.profile:
            command += ['--profile', self.profile]
        env = os.environ.copy()
        env.update(LARKSUITE_CLI_NO_UPDATE_NOTIFIER='1', LARKSUITE_CLI_NO_SKILLS_NOTIFIER='1')
        # Files avoid pipe deadlocks for downloads/status responses. Never log raw output.
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(command, cwd=self.work, env=env, stdout=output, stderr=errors,
                                       stdin=subprocess.PIPE if secret is not None else subprocess.DEVNULL,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            try:
                if secret is not None:
                    process.stdin.write((secret+'\n').encode('utf-8'))
                    process.stdin.close()
                started = time.monotonic()
                while process.poll() is None:
                    if stop and stop.is_set():
                        raise Cancelled()
                    if time.monotonic()-started > timeout:
                        raise TimeoutError('飞书响应超时，可以重新同步；已下载素材保留。')
                    time.sleep(.05)
                output.seek(0); errors.seek(0)
                raw = (errors.read() if process.returncode else output.read()).decode('utf-8-sig', errors='replace')
                try:
                    result = json.loads(raw)
                except ValueError:
                    if not process.returncode and not require_json: return dict(ok=True)
                    raise RuntimeError('飞书连接未返回有效结果，请检查飞书配置和网络。')
                if process.returncode or result.get('ok') is False:
                    error = result.get('error', {})
                    # Do not expose raw errors/URLs/tokens from the CLI to logs or dialogs.
                    if error.get('type') in ('authorization', 'authentication'):
                        raise RuntimeError('飞书授权或访问权限不足，请检查连接、完成授权，并确认账号能下载此表视频。')
                    raise RuntimeError('飞书操作失败，请检查网络、表格访问和下载权限。错误码：'+str(error.get('code', process.returncode)))
                return result
            finally:
                if process.poll() is None:
                    process.terminate()
                    try: process.wait(timeout=5)
                    except subprocess.TimeoutExpired: process.kill(); process.wait()

    def status(self, stop=None):
        result = self.call(['auth', 'status', '--json', '--verify'], stop)
        user = result.get('identities', {}).get('user', {})
        return dict(ready=bool(user.get('verified')), configured=bool(result.get('appId')),
                    name=user.get('userName', ''), state=user.get('status', 'unknown'))


def flatten(value):
    if value is None: return ''
    if isinstance(value, list): return '、'.join(flatten(v) for v in value)
    if isinstance(value, dict): return str(value.get('text', value.get('name', '')))
    return str(value)


def normalize_records(records, target):
    items = []
    for row in records:
        for attachment in row.get('成品文件') or []:
            token = attachment.get('file_token')
            name = attachment.get('name', '')
            if not token or Path(name).suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            record_id = row['record_id']
            key = hashlib.sha256((target['base_token']+'/'+target['table_id']+'/'+record_id+'/'+token).encode()).hexdigest()
            items.append(dict(key=key, record_id=record_id, file_token=token, filename=name,
                              name=flatten(row.get('描述')) or name, size=int(attachment.get('size') or 0),
                              note=flatten(row.get('备注')), creator=flatten(row.get('制作人')),
                              date=flatten(row.get('日期'))[:10], usable=flatten(row.get('是否直接可用'))))
    return items


class CloudLibrary:
    def __init__(self, folder=None):
        self.folder = Path(folder or data_dir()/'cloud')
        self.folder.mkdir(parents=True, exist_ok=True)
        self.config = load_json(self.folder/'config.json', dict(url=DEFAULT_URL, profile=''))
        self.library = load_json(self.folder/'library.json', dict(items=[], cache={}, target={}))

    def cli(self):
        return FeishuCLI(self.folder, self.config.get('profile', ''))

    def save_config(self, url, profile):
        parsed = urlparse(url)
        if parsed.scheme != 'https' or not parsed.hostname or not (parsed.hostname == 'feishu.cn' or parsed.hostname.endswith('.feishu.cn') or parsed.hostname == 'larksuite.com' or parsed.hostname.endswith('.larksuite.com')):
            raise ValueError('请填写有效的飞书多维表格HTTPS链接。')
        self.config = dict(url=url, profile=profile.strip())
        write_json(self.folder/'config.json', self.config)

    def refresh(self, stop=None, notify=lambda _: None):
        cli = self.cli()
        notify(dict(type='log', text='正在读取飞书前贴目录…'))
        resolved = cli.call(['base', '+url-resolve', '--url', self.config['url'], '--as', 'user'], stop)['data']
        if resolved.get('resource_type') != 'bitable' or not resolved.get('table_id'):
            raise ValueError('链接需要指向一张多维表格数据表。')
        target = {k: resolved[k] for k in ('base_token', 'table_id')}
        target.update(view_id=resolved.get('view_id', ''), title=resolved.get('block_name') or resolved.get('title', '飞书前贴库'))
        records = []; offset = 0
        while True:
            filename = 'records-'+uuid.uuid4().hex+'.ndjson'
            path = cli.work/filename
            args = ['base', '+record-list', '--base-token', target['base_token'], '--table-id', target['table_id']]
            if target['view_id']: args += ['--view-id', target['view_id']]
            for field in FIELDS: args += ['--field-id', field]
            args += ['--offset', str(offset), '--limit', '2000', '--format', 'ndjson', '--output', filename, '--as', 'user']
            try:
                result = cli.call(args, stop)
                manifest = result.get('data', result)
                rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
                if len(rows) != manifest.get('records_count'):
                    raise RuntimeError('飞书目录数量核对失败，请重新刷新。')
                records.extend(rows)
                if not manifest.get('has_more'): break
                if not rows: raise RuntimeError('飞书目录分页没有进展，请重新刷新。')
                offset += len(rows)
            finally:
                path.unlink(missing_ok=True)
                path.with_suffix('.manifest.json').unlink(missing_ok=True)
        items = normalize_records(records, target)
        catalog = dict(target=target, source_url=self.config['url'], items=items, cache=self.library.get('cache', {}), records=len(records),
                       refreshed=time.strftime('%Y-%m-%d %H:%M:%S'))
        write_json(self.folder/'library.json', catalog)
        self.library = catalog
        return catalog

    def cached(self, item):
        entry = self.library.get('cache', {}).get(item['key'])
        if not entry: return None
        path = self.folder/entry['relative_path']
        if not path.resolve().is_relative_to(self.folder.resolve()): return None
        if not path.is_file(): return None
        return dict(entry['asset'], path=str(path))

    def sync(self, items, stop=None, notify=lambda _: None):
        cli = self.cli(); target = self.library['target']
        source_url = self.library.get('source_url', self.config['url'])
        assets = []; errors = []; downloaded = 0; reused = 0; cancelled = False
        for index, item in enumerate(items, 1):
            if stop and stop.is_set(): cancelled = True; break
            notify(dict(type='log', text=f'同步云端前贴 {index}/{len(items)}：{item["name"]}'))
            temp = None
            try:
                cached = self.cached(item)
                if cached and identity(cached['path']) == cached['id']:
                    cached['name'] = item['name']+' · '+item['filename']
                    cached['cloud'] = dict(item, source_url=source_url)
                    assets.append(cached); reused += 1; continue
                suffix = Path(item['filename']).suffix.lower()
                relative = Path('files')/item['key']/('video'+suffix)
                final = self.folder/relative; final.parent.mkdir(parents=True, exist_ok=True)
                temp = final.with_name('download-'+uuid.uuid4().hex+suffix)
                # CLI permits relative paths within cwd; place cwd at the cloud folder for media.
                original_work = cli.work; cli.work = self.folder
                try:
                    cli.call(['base', '+record-download-attachment', '--base-token', target['base_token'], '--table-id', target['table_id'],
                              '--record-id', item['record_id'], '--file-token', item['file_token'], '--output', temp.relative_to(self.folder).as_posix(), '--as', 'user'], stop, timeout=900)
                finally: cli.work = original_work
                if item['size'] and temp.stat().st_size != item['size']:
                    raise ValueError('下载大小不符，请重试。')
                result = scan([temp], 'a', stop)
                if not result['assets']: raise ValueError('视频无法读取，未加入前贴。')
                record = result['assets'][0]
                temp.replace(final)
                record.update(path=str(final), name=item['name']+' · '+item['filename'], cloud=dict(item, source_url=source_url))
                self.library.setdefault('cache', {})[item['key']] = dict(relative_path=relative.as_posix(), asset=record)
                write_json(self.folder/'library.json', self.library)
                assets.append(record); downloaded += 1
            except Cancelled:
                cancelled = True; break
            except Exception as exc:
                errors.append(item['name']+'：'+str(exc))
            finally:
                if temp: temp.unlink(missing_ok=True)
        return dict(assets=assets, downloaded=downloaded, reused=reused, errors=errors, cancelled=cancelled)
