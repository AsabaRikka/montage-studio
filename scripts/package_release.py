"""Prepare portable folder or create CRC-checked delivery ZIPs."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile

root=Path(__file__).resolve().parent.parent
release=root/'release'
package=release/'混剪工坊_1.0'

if sys.argv[1]=='prepare':
    app=package/'MontageStudio'
    if (app/'data').exists():
        raise SystemExit('Refusing to overwrite a distribution with user data.')
    shutil.copytree(root/'dist/MontageStudio',app,dirs_exist_ok=True)
    for src,dst in [('docs/使用说明.md','使用说明.md'),('LICENSE','LICENSE'),('docs/THIRD_PARTY.md','第三方来源.md'),('docs/ASSETS_MANIFEST.json','资源校验清单.json')]:
        shutil.copy2(root/src,package/dst)
    shutil.copy2(Path(sys.base_prefix)/'LICENSE.txt',package/'Python-LICENSE.txt')
    (package/'先看这里.txt').write_text('混剪工坊 1.0\n\n打开 MontageStudio 文件夹，双击 MontageStudio.exe。\n无需安装 Python 或其他组件。\n复制给同事时请复制整个文件夹，不要只复制 EXE。\n第一次建议用演示素材试做一条，然后校正字幕、试听声音。\n详细操作见使用说明.md，源码见同目录发布的源码 ZIP。\n',encoding='utf-8-sig')
    shutil.copytree(root/'test_results/source_delivery/演示素材',package/'演示素材',dirs_exist_ok=True)
    shutil.copy2(root/'test_results/演示成片.mp4',package/'演示成片.mp4')
    print(package)
elif sys.argv[1]=='zip':
    evidence=package/'验证记录'
    evidence.mkdir(parents=True,exist_ok=True)
    items={'test_results/source_selftest/自检报告.json':'源码媒体自检.json',
        'test_results/source_delivery/扩展报告.json':'源码扩展验证.json',
        'test_results/stress/1000条报告.json':'1000条短片压力验证.json',
        'test_results/portable_final/便携验证.json':'便携验证.json',
        'test_results/portable_final/selftest/自检报告.json':'便携媒体自检.json',
        'test_results/portable_final/delivery/扩展报告.json':'便携扩展验证.json',
        'docs/DELIVERY.md':'交付说明.md',
        'test_results/portable_final/delivery/gui/播放器实际视频帧.png':'实际解码帧.png',
        'test_results/portable_final/delivery/gui/导出完成.png':'便携导出完成.png'}
    portable=json.loads((root/'test_results/portable_final/便携验证.json').read_text(encoding='utf-8'))
    if not portable.get('passed') or len(portable.get('checks',[]))!=3:
        raise SystemExit('Portable validation must finish successfully before packaging.')
    if hashlib.sha256((package/'MontageStudio/MontageStudio.exe').read_bytes()).hexdigest()!=portable.get('exe_sha256'):
        raise SystemExit('Portable validation does not match the release executable.')
    if (package/'MontageStudio/data').exists():
        raise SystemExit('Distribution contains user data; do not include it in the release.')
    for src,dst in items.items():shutil.copy2(root/src,evidence/dst)
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    (package/'版本.txt').write_text('1.0.0\nGit: '+revision+'\nWindows x64; Python 3.14.4 / PySide6 6.11.0\n',encoding='utf-8-sig')
    binary_zip=release/'混剪工坊_1.0_完整便携版.zip'
    with zipfile.ZipFile(binary_zip,'w',zipfile.ZIP_DEFLATED,compresslevel=4) as z:
        for p in sorted(package.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(release))
    source_zip=release/'混剪工坊_1.0_源码.zip'
    subprocess.run(['git','archive','--format=zip','--prefix=混剪工坊源码/','-o',str(source_zip),'HEAD'],cwd=root,check=True)
    report={'git':revision,'archives':[]}
    for p in [binary_zip,source_zip]:
        with zipfile.ZipFile(p) as z:
            bad=z.testzip()
            if bad:raise RuntimeError('CRC failed: '+bad)
            files=len(z.infolist())
        h=hashlib.sha256()
        with p.open('rb') as f:
            while block:=f.read(8*1024*1024):h.update(block)
        report['archives'].append(dict(file=p.name,bytes=p.stat().st_size,files=files,crc_passed=True,sha256=h.hexdigest()))
        print(report['archives'][-1],flush=True)
    (release/'交付包校验.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
else:
    raise SystemExit('Expected prepare or zip')
