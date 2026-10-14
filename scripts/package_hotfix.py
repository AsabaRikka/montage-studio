"""Small, explicit-baseline patch; never traverse an installed app's data."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
import zipfile

root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser()
p.add_argument('mode',choices=['prepare','zip'])
p.add_argument('--version',required=True)
p.add_argument('--base',required=True)
p.add_argument('--layout-report',default='')
p.add_argument('--quick-report',default='')
p.add_argument('--naming-report',default='')
args=p.parse_args()
target=root/'release'/('混剪工坊_'+args.version)
app=target/'MontageStudio'
base=root/'release'/('混剪工坊_'+args.base)/'MontageStudio'
dist=root/'dist/MontageStudio'
manifest_path=target/'补丁文件清单.json'
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while block:=f.read(8*1024*1024):h.update(block)
    return h.hexdigest()
started=time.monotonic()
if args.mode=='prepare':
    if target.exists():raise SystemExit('New version directory already exists; refusing overwrite.')
    if (dist/'data').exists():raise SystemExit('Build contains data; refusing package.')
    files=[]
    for source in sorted(dist.rglob('*')):
        if not source.is_file():continue
        relative=source.relative_to(dist)
        if relative.parts[0] not in ('_internal','MontageStudio.exe'):raise SystemExit('Unexpected build file: '+str(relative))
        previous=base/relative
        current_hash=sha(source)
        previous_hash=sha(previous) if previous.is_file() else None
        destination=app/relative;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(previous if current_hash==previous_hash else source,destination)
        files.append(dict(path=relative.as_posix(),sha256=current_hash,base_sha256=previous_hash,changed=current_hash!=previous_hash))
    manifest=dict(version=args.version,base_version=args.base,base_exe_sha256=sha(base/'MontageStudio.exe'),files=files,seconds=round(time.monotonic()-started,2))
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(files=len(files),changed=sum(f['changed'] for f in files),seconds=manifest['seconds']),ensure_ascii=False))
else:
    if (app/'data').exists():raise SystemExit('Release contains data; refusing package.')
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    current_hash=sha(app/'MontageStudio.exe');evidence=target/'验证记录';evidence.mkdir(exist_ok=True)
    reports=[('layout',args.layout_report),('naming',args.naming_report)] if args.naming_report else [('layout',args.layout_report),('quick',args.quick_report)]
    for kind,path in reports:
        report_path=root/path;report=json.loads(report_path.read_text(encoding='utf-8'))
        if not report.get('passed') or report.get('version')!=args.version or report.get('exe_sha256')!=current_hash or any(not c.get('passed') for c in report.get('checks',[])):raise SystemExit('Invalid final EXE report: '+kind)
        shutil.copy2(report_path,evidence/report_path.name)
        for image in report_path.parent.glob('*.png'):shutil.copy2(image,evidence/image.name)
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    (target/'版本.txt').write_text(args.version+'\nGit: '+revision+'\n补丁基线: '+args.base+'\n',encoding='utf-8-sig')
    for source,destination in [('docs/使用说明.md','使用说明.md'),('docs/DELIVERY.md','交付说明.md'),('docs/THIRD_PARTY.md','第三方来源.md'),('LICENSE','LICENSE')]:shutil.copy2(root/source,target/destination)
    instructions=(f'混剪工坊 {args.version} 小更新；只适用于完整 {args.base}。\n'
        '先退出旧软件，备份软件显示的实际 data（包括 cloud）。保留旧版整个目录。\n'
        '可以直接把本补丁的 MontageStudio 文件夹合并到完整旧版的同名文件夹，替换对应程序文件，即升级生效。推荐先保留旧版整个目录副本以便回退。不要删除或替换 data，不要只复制 EXE 到空目录。\n'
        '直接覆盖升级时继续使用原位置的数据；如果另建新版目录，退出后将备份的完整 data（包括 cloud）复制到新版 MontageStudio/data。不要同时运行两版处理同一份数据。\n'
        '该补丁没有在线更新功能，不包含用户数据、公司视频或凭据。其他旧版本请使用完整新版文件夹。\n')
    (target/'先看这里.txt').write_text(instructions,encoding='utf-8-sig')
    patch=root/'release'/f'混剪工坊_{args.version}_升级补丁.zip'
    with zipfile.ZipFile(patch,'w',zipfile.ZIP_DEFLATED,compresslevel=4) as z:
        for entry in manifest['files']:
            if entry['changed']:
                path=app/entry['path']
                if sha(path)!=entry['sha256']:raise SystemExit('Changed patch file no longer matches manifest.')
                z.write(path,'MontageStudio/'+entry['path'])
        for name in ['先看这里.txt','版本.txt','补丁文件清单.json','交付说明.md','使用说明.md']:z.write(target/name,name)
        for path in evidence.rglob('*'):
            if path.is_file():z.write(path,path.relative_to(target))
    with zipfile.ZipFile(patch) as z:
        if z.testzip():raise SystemExit('Patch CRC failed.')
        # Read back every changed program file from the ZIP and bind it to the verified folder.
        for entry in manifest['files']:
            if entry['changed'] and hashlib.sha256(z.read('MontageStudio/'+entry['path'])).hexdigest()!=entry['sha256']:raise SystemExit('Patch read-back failed.')
    source_zip=root/'release'/f'混剪工坊_{args.version}_源码.zip'
    subprocess.run(['git','archive','--format=zip','--prefix=混剪工坊源码/','-o',str(source_zip),'HEAD'],cwd=root,check=True)
    with zipfile.ZipFile(source_zip) as z:
        if z.testzip():raise SystemExit('Source CRC failed.')
    result=dict(version=args.version,git=revision,exe_sha256=current_hash,base_version=args.base,user_data_included=False,full_folder_delivered=True,full_zip_created=False,patch_crc_passed=True,source_crc_passed=True,patch_bytes=patch.stat().st_size,patch_sha256=sha(patch),source_sha256=sha(source_zip),seconds=round(time.monotonic()-started,2))
    (root/'release'/f'交付包校验_{args.version}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
