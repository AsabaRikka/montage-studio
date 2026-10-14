"""Create a fresh-PC archive from the audited program manifest, without data."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import zipfile

p = argparse.ArgumentParser()
p.add_argument('--version', required=True)
p.add_argument('--resume-check', action='store_true', help='Recheck an existing unfinished archive without overwriting it.')
args = p.parse_args()
root = Path(__file__).resolve().parent.parent
release = root / 'release'
source = release / ('混剪工坊_' + args.version)
app = source / 'MontageStudio'
archive = release / ('混剪工坊_' + args.version + '_完整便携版.zip')
building = archive.with_suffix('.zip.building')
if archive.exists() or (building.exists() and not args.resume_check):
    raise SystemExit('Refusing to overwrite an existing archive.')
# The delivered folder may now be in use. Read only manifest-listed program
# files; never enumerate, read, copy or remove its data directory.
manifest = json.loads((source / '补丁文件清单.json').read_text(encoding='utf-8'))
assert manifest['version'] == args.version
original = json.loads((release / ('交付包校验_' + args.version + '.json')).read_text(encoding='utf-8'))
entries = {}
for entry in manifest['files']:
    path = Path(entry['path'])
    if path.is_absolute() or '..' in path.parts or path.parts[0] not in ('_internal', 'MontageStudio.exe') or 'data' in path.parts:
        raise SystemExit('Unexpected program path: ' + str(path))
    entries['MontageStudio/' + path.as_posix()] = entry['sha256']

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        while chunk := f.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()

started = time.monotonic()
prefix = source.name + '/'
readme = ('混剪工坊 ' + args.version + ' 完整便携版（新电脑首次使用）\n\n'
    '将压缩包完整解压到一个新的、可写的文件夹，再打开 MontageStudio/MontageStudio.exe。\n'
    '不要在压缩包内直接运行，也不要只复制 EXE。无需安装 Python 或 FFmpeg。\n'
    '本包不包含用户 data、公司视频、登录信息或旧任务。新电脑不要复制原电脑的 data。\n'
    '在新电脑重新导入本机 B 主视频；A 前贴可本机导入或从指定公开库勾选同步。\n'
    '选择该电脑上的保存位置，勾选 A/B 后点击一键拼接并导出，首次建议指定 1 条。\n'
    '如需保留同一电脑的历史，先退出旧版并备份完整实际 data（含 cloud）；另行迁移，素材路径需仍可访问。\n'
    '保留旧版本与数据，不同时运行两版处理同一份数据。\n')
if not args.resume_check:
    print('Creating complete clean archive (no rebuild).', flush=True)
    with zipfile.ZipFile(building, 'x', zipfile.ZIP_DEFLATED, compresslevel=4) as z:
        for name, expected in entries.items():
            path = source / name
            if sha(path) != expected:
                raise SystemExit('Program differs from audited manifest: ' + name)
            z.write(path, prefix + name)
        z.writestr(prefix + '先看这里.txt', readme.encode('utf-8-sig'))
        z.writestr(prefix + '版本.txt', (args.version + '\nProgram Git: ' + original['git'] + '\nWindows x64\n').encode('utf-8-sig'))
        z.writestr(prefix + '程序文件校验.json', json.dumps(entries, ensure_ascii=False, indent=2))
        for name, doc in [('使用说明.md', 'docs/使用说明.md'), ('第三方来源.md', 'docs/THIRD_PARTY.md'), ('LICENSE', 'LICENSE')]:
            z.write(root / doc, prefix + name)
print('Checking CRC and extracting to an isolated fresh folder.', flush=True)
test_root = root / 'test_results'
test_root.mkdir(exist_ok=True)
check = Path(tempfile.mkdtemp(prefix='clean_v110_', dir=test_root))
with zipfile.ZipFile(building) as z:
    assert len(z.namelist()) == len(entries) + 6
    assert all(n.startswith(prefix) and '..' not in Path(n).parts and 'data' not in Path(n).parts for n in z.namelist())
    if z.testzip():
        raise SystemExit('Archive CRC failed.')
    z.extractall(check / 'extracted')
extracted = check / 'extracted' / source.name
for name, expected in entries.items():
    assert sha(extracted / name) == expected, name
assert not (extracted / 'MontageStudio/data').exists()
exe = extracted / 'MontageStudio/MontageStudio.exe'
assert sha(exe) == original['exe_sha256']
env = os.environ.copy()
system_root = env.get('SystemRoot', r'C:\Windows')
env['PATH'] = os.path.join(system_root, 'System32') + ';' + system_root
env.pop('PYTHONPATH', None)
env['MONTAGE_DATA_DIR'] = str(check / 'quick/diagnostic_data')
env['HF_HOME'] = str(check / 'empty_hf_cache')
env['HF_HUB_OFFLINE'] = '1'
env['TRANSFORMERS_OFFLINE'] = '1'
print('Running extracted EXE one-click checks with fresh isolated data.', flush=True)
subprocess.run([str(exe), '--quick-test', str(check / 'quick')], env=env, cwd=exe.parent, check=True, timeout=180)
quick = json.loads((check / 'quick/quick_verification.json').read_text(encoding='utf-8'))
assert quick['passed'] and len(quick['checks']) == 6 and all(c['passed'] for c in quick['checks'])
assert quick['exe_sha256'] == original['exe_sha256'] and quick['version'] == args.version
assert not (extracted / 'MontageStudio/data').exists()
building.rename(archive)
result = dict(version=args.version, program_git=original['git'], exe_sha256=original['exe_sha256'],
    file=archive.name, bytes=archive.stat().st_size, sha256=sha(archive), crc_passed=True,
    program_files_verified=len(entries), user_data_included=False, company_media_included=False,
    credentials_included=False, quick_report=str((check / 'quick/quick_verification.json').relative_to(root)),
    quick_checks=6, quick_seconds=quick['seconds'], restricted_path=True, physical_computers=1,
    seconds=round(time.monotonic()-started, 2))
(release / ('干净完整包校验_' + args.version + '.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False), flush=True)
