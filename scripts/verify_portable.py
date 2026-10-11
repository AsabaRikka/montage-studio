"""Run the released EXE with no Python/FFmpeg on PATH or external model cache."""
from pathlib import Path
import json
import hashlib
import os
import shutil
import subprocess
import sys
import time

exe=Path(sys.argv[1]).resolve()
folder=Path(sys.argv[2]).resolve()
folder.mkdir(parents=True,exist_ok=True)
env=os.environ.copy()
windows_dir=os.environ['SystemRoot']
env['PATH']=os.path.join(windows_dir,'System32')+';'+windows_dir
env['HF_HOME']=str(folder/'empty_hf_cache')
env['HF_HUB_OFFLINE']='1'
env['TRANSFORMERS_OFFLINE']='1'
env['MONTAGE_DATA_DIR']=str(folder/'gui_data')
env.pop('PYTHONPATH',None)
demo=Path(__file__).resolve().parent.parent/'test_results/source_delivery/演示素材'
shutil.copytree(demo,folder/'delivery/演示素材',dirs_exist_ok=True)
checks=[]
exe_sha256=hashlib.sha256(exe.read_bytes()).hexdigest()
for flag,path in [('--self-test',folder/'selftest'),('--delivery-test',folder/'delivery'),('--screenshot',folder/'启动界面.png')]:
    t=time.monotonic()
    print('Running',flag,flush=True)
    result=subprocess.run([str(exe),flag,str(path)],env=env,cwd=exe.parent,timeout=900)
    checks.append(dict(command=flag,exit_code=result.returncode,seconds=round(time.monotonic()-t,2)))
    print(checks[-1],flush=True)
    (folder/'便携验证.json').write_text(json.dumps(dict(passed=len(checks)==3 and all(c['exit_code']==0 for c in checks),checks=checks,exe=str(exe),exe_sha256=exe_sha256,restricted_path=env['PATH'],offline=True,external_cache_empty=True,physical_computers=1),ensure_ascii=False,indent=2),encoding='utf-8')
    if result.returncode:
        sys.exit(result.returncode)
