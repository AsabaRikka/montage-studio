"""Run the release using a COPY of previous synthetic test data, never user data."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys

root=Path(__file__).resolve().parent.parent
exe=Path(sys.argv[1]).resolve()
folder=Path(sys.argv[2]).resolve()
source=root/'test_results/portable_v101/delivery-test_data'
target=folder/'migrated_synthetic_data'
if target.exists():
    raise SystemExit('Use a new validation destination, preserving earlier evidence.')
folder.mkdir(parents=True,exist_ok=True)

def database(folder):
    result={}
    for p in sorted(folder.glob('*.sqlite3')):
        connection=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True)
        try:
            tables=connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
            result[p.name]={name:connection.execute('SELECT * FROM "'+name.replace('"','""')+'" ORDER BY rowid').fetchall() for (name,) in tables}
        finally:connection.close()
    return result

before_session=json.loads((source/'session.json').read_text(encoding='utf-8'))
before_db=database(source)
source_hash=hashlib.sha256((source/'session.json').read_bytes()).hexdigest()
shutil.copytree(source,target)
env=os.environ.copy();windows=os.environ['SystemRoot'];env['PATH']=windows+'/System32;'+windows
env['MONTAGE_DATA_DIR']=str(target);env['HF_HUB_OFFLINE']='1';env['TRANSFORMERS_OFFLINE']='1'
result=subprocess.run([str(exe),'--screenshot',str(folder/'旧版数据新版界面.png')],env=env,cwd=exe.parent,timeout=60)
assert result.returncode==0
after_session=json.loads((target/'session.json').read_text(encoding='utf-8'))
for key,value in before_session.items():
    assert after_session[key]==value, 'Changed existing session field: '+key
assert after_session.get('ui_theme')=='light'
after_db=database(target)
assert before_db==after_db,'Changed task/history records'
assert hashlib.sha256((source/'session.json').read_bytes()).hexdigest()==source_hash,'Changed source test data'
assert database(source)==before_db,'Changed source test databases'
import pefile
pe=pefile.PE(str(exe))
resource_types=[e.id for e in pe.DIRECTORY_ENTRY_RESOURCE.entries]
assert 3 in resource_types and 14 in resource_types,'Missing EXE icon or group icon'
pe.close()
report=dict(passed=True,source='1.0.1 synthetic delivery-test data only',copy_only=True,
    exe_sha256=hashlib.sha256(exe.read_bytes()).hexdigest(),
    session_fields_preserved=list(before_session),theme_default='light',database_records_preserved=True,
    database_rows={db:{table:len(rows) for table,rows in tables.items()} for db,tables in before_db.items()},
    source_unchanged=True,exe_icon=True,second_physical_pc=False)
(folder/'升级与图标验证.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
