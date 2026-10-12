"""Verify default screenshot diagnostics preserve normal session/database files."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
exe = Path(sys.argv[1]).resolve()
folder = Path(sys.argv[2]).resolve()
folder.mkdir(parents=True, exist_ok=True)

def snapshot(path):
    if not path.exists():
        return None
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in path.iterdir() if p.is_file()
            and (p.name == 'session.json' or '.sqlite3' in p.name)}

env = os.environ.copy()
env.pop('MONTAGE_DATA_DIR', None)
checks = []
for name, command, normal_data in [
    ('source', [sys.executable, str(root/'main.py')], root/'data'),
    ('frozen', [str(exe)], exe.parent/'data'),
]:
    before = snapshot(normal_data)
    target = folder/(name+'.png')
    result = subprocess.run(command+['--screenshot', str(target)], cwd=root,
                            env=env, timeout=60)
    assert result.returncode == 0
    assert target.is_file()
    assert (folder/(name+'_diagnostic_data')/'session.json').is_file()
    assert snapshot(normal_data) == before, 'Modified normal data: '+name
    checks.append(dict(mode=name, default_isolation=True, normal_data_unchanged=True))
report = dict(passed=True, checks=checks,
              exe_sha256=hashlib.sha256(exe.read_bytes()).hexdigest())
(folder/'截图隔离验证.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False))
