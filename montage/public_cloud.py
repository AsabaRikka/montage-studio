"""Anonymous read-only access to a public Feishu Base view.

Fresh anonymous cookies and page-issued metadata stay in memory. No CLI,
personal cookies, application secret, browser or login is used.
"""
import base64
import gzip
import http.cookiejar
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from .core import Cancelled


class PublicAccessError(RuntimeError):
    pass


def safe_host(url):
    try:
        p = urllib.parse.urlparse(url)
        host = (p.hostname or '').lower()
        return p.scheme == 'https' and not p.username and not p.password and p.port in (None, 443) and any(
            host == domain or host.endswith('.' + domain) for domain in ('feishu.cn', 'feishucdn.com'))
    except ValueError:
        return False


class PublicRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not safe_host(newurl):
            raise PublicAccessError('公开库重定向到不支持的地址，已停止访问。')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def decode_part(value):
    if isinstance(value, dict):
        return value
    try:
        if len(value) > 64 * 1024 * 1024:
            raise ValueError('too large')
        with gzip.GzipFile(fileobj=io.BytesIO(base64.b64decode(value, validate=True))) as stream:
            raw = stream.read(64 * 1024 * 1024 + 1)
        if len(raw) > 64 * 1024 * 1024:
            raise ValueError('too large')
        return json.loads(raw)
    except (ValueError, TypeError, OSError) as exc:
        raise PublicAccessError('飞书公开目录格式已变化，未覆盖本地目录。') from exc


def public_rows(table, view_id):
    """Accept only a complete server-selected view; never return a partial catalog."""
    if table.get('currentView') != view_id or view_id not in table.get('viewMap', {}):
        raise PublicAccessError('公开库返回的视图不匹配，未读取其他视图。')
    groups = table.get('groupList', [])
    ids = list(dict.fromkeys(rid for group in groups for rid in group.get('recordIDList', [])))
    records = table.get('recordMap', {})
    count = table.get('recordCount')
    if table.get('recordPage') or table.get('deniedRecords') or not isinstance(count, int) or count != len(ids) or any(rid not in records for rid in ids):
        raise PublicAccessError('公开视图目录未完整返回（可能记录过多或存在访问限制），本地目录保留。请使用较小的公开视图。')
    fields = table.get('fieldMap', {})
    wanted = {'描述', '成品文件', '备注', '制作人', '日期', '是否直接可用'}
    projected = {fid: field for fid, field in fields.items() if field.get('name') in wanted}
    finished = next((fid for fid, field in projected.items() if field['name'] == '成品文件'), None)
    if not finished:
        raise PublicAccessError('此公开视图没有可读取的“成品文件”字段。')
    def text(value, field):
        if value is None:
            return ''
        if field.get('type') in (3, 4):
            options = {o['id']: o['name'] for o in field.get('property', {}).get('options', [])}
            return '、'.join(options.get(v, '') for v in (value if isinstance(value, list) else [value]))
        if field.get('type') == 5 and isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000).strftime('%Y-%m-%d')
        if isinstance(value, list):
            return ''.join(v.get('text', v.get('name', '')) if isinstance(v, dict) else str(v) for v in value)
        return str(value)
    rows = []
    for rid in ids:
        record = records[rid]
        row = dict(record_id=rid)
        for fid, field in projected.items():
            value = record.get(fid, {}).get('value')
            if fid == finished:
                row[field['name']] = [dict(file_token=a.get('attachmentToken', a.get('id')), name=a.get('name', ''), size=a.get('size', 0)) for a in (value or [])]
            else:
                row[field['name']] = text(value, field)
        rows.append(row)
    return rows, finished


class PublicFeishu:
    def __init__(self, url, stop=None):
        p = urllib.parse.urlparse(url)
        parts = p.path.strip('/').split('/')
        q = urllib.parse.parse_qs(p.query)
        if not safe_host(url) or not (p.hostname == 'feishu.cn' or (p.hostname or '').endswith('.feishu.cn')) or len(parts) != 2 or parts[0] not in ('wiki', 'base') or not q.get('table') or not q.get('view'):
            raise PublicAccessError('公开库需填写包含 table 和 view 的飞书表格或知识库链接。')
        self.url = url
        self.origin = 'https://' + p.hostname
        self.host_type = 'Wiki' if parts[0] == 'wiki' else 'Bitable'
        self.host_token = parts[1]
        self.table_id = q['table'][0]
        self.view_id = q['view'][0]
        if not all(re.fullmatch(r'[A-Za-z0-9]+', value) for value in (self.host_token, self.table_id, self.view_id)):
            raise PublicAccessError('公开库链接中的表格或视图编号无效。')
        self.stop = stop
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(PublicRedirect(), urllib.request.HTTPCookieProcessor(self.cookies))
        self.headers = {'User-Agent': 'Mozilla/5.0', 'Referer': url}
        self.target = None
        self.ready_at = 0

    def cancelled(self):
        if self.stop and self.stop.is_set():
            raise Cancelled()

    def open(self, url, timeout=30):
        self.cancelled()
        if not safe_host(url):
            raise PublicAccessError('不支持的公开库地址。')
        try:
            return self.opener.open(urllib.request.Request(url, headers=self.headers), timeout=timeout)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise PublicAccessError('公开库或附件不允许匿名访问，请检查互联网分享和下载权限；已有缓存保留。') from None
            raise PublicAccessError('公开库请求失败（HTTP ' + str(exc.code) + '），请稍后重试。') from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise PublicAccessError('公开库网络连接失败或超时，已有缓存保留。') from None

    def prepare(self):
        # Drop expired page-issued metadata and establish a fresh anonymous session.
        self.headers = {'User-Agent': 'Mozilla/5.0', 'Referer': self.url}
        with self.open(self.url) as response:
            html = self.read(response, 4 * 1024 * 1024).decode('utf-8', errors='replace')
        try:
            marker = 'window.metaCache = Object('
            meta = json.JSONDecoder().raw_decode(html.split(marker, 1)[1])[0]
            candidates = {k: v['encrypted'] for k, v in meta.items() if isinstance(v, dict) and v.get('encrypted')}
            if len(candidates) != 1:
                raise ValueError('ambiguous')
            base = next(iter(candidates))
        except (ValueError, IndexError, KeyError, TypeError):
            raise PublicAccessError('没有取得公开库访问许可，请检查链接是否允许互联网用户查看；无需填写应用密钥。') from None
        self.headers.update({'ccm-meta': json.dumps(candidates), 'docs-host-id': self.host_token,
                             'docs-host-type': self.host_type, 'x-csrftoken': next((c.value for c in self.cookies if c.name == 'swp_csrf_token'), '')})
        query = urllib.parse.urlencode(dict(tableID=self.table_id, viewID=self.view_id, recordLimit=2000, ondemandLimit=2000,
            needBase='true', viewLazyLoad='true', ondemandVer=2, openType=0, noMissCS='true', optimizationFlag=1, removeFmlExtra='true'))
        with self.open(self.origin + '/space/api/v1/bitable/' + base + '/clientvars?' + query) as response:
            try:
                result = json.loads(self.read(response, 64 * 1024 * 1024))
            except ValueError:
                raise PublicAccessError('公开库返回了登录页或异常内容，本地目录保留。') from None
        if not isinstance(result, dict) or result.get('code') != 0:
            raise PublicAccessError('飞书拒绝匿名读取此公开视图，请检查分享范围和访问限制。')
        data = result.get('data')
        if not isinstance(data, dict) or 'table' not in data:
            raise PublicAccessError('公开库目录格式已变化，本地目录保留。')
        table = decode_part(data['table'])
        if table.get('meta', {}).get('id') != self.table_id:
            raise PublicAccessError('公开库返回的表格不匹配，已停止读取。')
        rows, field_id = public_rows(table, self.view_id)
        self.target = dict(base_token=base, table_id=self.table_id, view_id=self.view_id,
                           title='公开前贴库', attachment_field=field_id, rev=table['meta'].get('rev', 0))
        self.rows = rows
        self.anonymous = any(c.name == 'is_anonymous_session' and c.value.lower() in ('1', 'true') for c in self.cookies)
        self.ready_at = time.monotonic()
        return rows, self.target

    def read(self, response, size):
        self.cancelled()
        try:
            return response.read(size)
        except (OSError, TimeoutError, EOFError) as exc:
            raise PublicAccessError('公开库传输中断，请重试；已有下载保留。') from None

    def download(self, item, target, path):
        if self.target is None or time.monotonic() - self.ready_at > 300:
            self.prepare()
        if any(self.target[k] != target[k] for k in ('base_token', 'table_id', 'view_id')):
            raise PublicAccessError('公开库已变化，请刷新目录后重新勾选。')
        rid, token = item['record_id'], item['file_token']
        if not any(r['record_id'] == rid and any(a['file_token'] == token for a in r.get('成品文件', [])) for r in self.rows):
            raise PublicAccessError('此视频已移出公开视图，请刷新目录。')
        extra = dict(bitablePerm=dict(tableId=self.table_id, rev=self.target['rev'],
                     attachments={self.target['attachment_field']: {rid: [token]}}))
        query = urllib.parse.urlencode(dict(extra=json.dumps(extra, separators=(',', ':')), mount_node_token=target['base_token'], mount_point='bitable'))
        url = 'https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/all/' + urllib.parse.quote(token, safe='') + '/?' + query
        with self.open(url, timeout=45) as response:
            if response.getcode() != 200 or 'text/html' in response.headers.get('Content-Type', '') or 'application/json' in response.headers.get('Content-Type', ''):
                raise PublicAccessError('附件下载返回了登录页或错误内容，未保存为视频。')
            with path.open('wb') as stream:
                while True:
                    self.cancelled()
                    block = self.read(response, 256 * 1024)
                    if not block:
                        break
                    stream.write(block)
