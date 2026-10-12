"""Prepare portable folder or create CRC-checked delivery ZIPs."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
import argparse

root=Path(__file__).resolve().parent.parent
release=root/'release'
parser=argparse.ArgumentParser()
parser.add_argument('mode',choices=['prepare','zip'])
parser.add_argument('--version',default='1.0.7')
parser.add_argument('--verification',default='test_results/portable_v107')
parser.add_argument('--upgrade-verification',default='test_results/upgrade_v107')
parser.add_argument('--isolation-verification',default='test_results/screenshot_v107')
parser.add_argument('--cloud-verification',default='test_results/cloud_v107_portable')
parser.add_argument('--cloud-baseline-version',default='',help='Reuse historical cloud evidence only when cloud modules are unchanged; no current EXE claim.')
parser.add_argument('--player-verification',default='test_results/player_v107_portable')
parser.add_argument('--subtitle-verification',default='test_results/subtitle_v107_portable')
parser.add_argument('--history-verification',default='test_results/history_v107_portable_final')
parser.add_argument('--sound-verification',default='test_results/sound_v107_portable')
args=parser.parse_args()
sys.path.insert(0,str(root))
from montage import __version__
if args.version != __version__:raise SystemExit('Release version must match source version.')
package=release/('混剪工坊_'+args.version)
verification=root/args.verification
upgrade_verification=root/args.upgrade_verification
isolation_verification=root/args.isolation_verification
cloud_verification=root/args.cloud_verification
player_verification=root/args.player_verification
history_verification=root/args.history_verification
subtitle_verification=root/args.subtitle_verification
sound_verification=root/args.sound_verification

if args.mode=='prepare':
    app=package/'MontageStudio'
    if (app/'data').exists():
        raise SystemExit('Refusing to overwrite a distribution with user data.')
    shutil.copytree(root/'dist/MontageStudio',app,dirs_exist_ok=True)
    for src,dst in [('docs/使用说明.md','使用说明.md'),('LICENSE','LICENSE'),('docs/THIRD_PARTY.md','第三方来源.md'),('docs/ASSETS_MANIFEST.json','资源校验清单.json')]:
        shutil.copy2(root/src,package/dst)
    shutil.copy2(Path(sys.base_prefix)/'LICENSE.txt',package/'Python-LICENSE.txt')
    (package/'先看这里.txt').write_text('混剪工坊 '+args.version+'\n\n打开 MontageStudio 文件夹，双击 MontageStudio.exe。\n无需安装 Python 或其他组件。\n复制给同事时请复制整个文件夹，不要只复制 EXE。\n升级时先退出旧版，备份后复制旧版 MontageStudio/data 到新版同一位置，保留任务与历史。\n第一次建议用演示素材试做一条，然后校正字幕、试听声音。\n详细操作见使用说明.md，源码见同目录发布的源码 ZIP。\n',encoding='utf-8-sig')
    shutil.copytree(root/'test_results/source_delivery/演示素材',package/'演示素材',dirs_exist_ok=True)
    shutil.copy2(root/'test_results/演示成片.mp4',package/'演示成片.mp4')
    print(package)
elif args.mode=='zip':
    evidence=package/'验证记录'
    evidence.mkdir(parents=True,exist_ok=True)
    items={root/'test_results/source_selftest/自检报告.json':'1.0.0基线_源码媒体自检.json',
        root/'test_results/source_delivery/扩展报告.json':'1.0.0基线_源码扩展验证.json',
        root/'test_results/stress/1000条报告.json':'1.0.0基线_1000条短片压力验证.json',
        verification/'便携验证.json':'便携验证.json',
        verification/'selftest/自检报告.json':'便携媒体自检.json',
        verification/'delivery/扩展报告.json':'便携扩展验证.json',
        verification/'ui/界面改进验证.json':'界面改进验证.json',
        upgrade_verification/'升级与图标验证.json':'升级与图标验证.json',
        isolation_verification/'截图隔离验证.json':'截图隔离验证.json',
        cloud_verification/'云端库验证.json':('历史基线_'+args.cloud_baseline_version+'_云端库验证.json' if args.cloud_baseline_version else '云端库验证.json'),
        player_verification/'播放器验证.json':'播放器验证.json',
        player_verification/'浅色进度条.png':'播放器浅色进度条.png',
        player_verification/'深色进度条.png':'播放器深色进度条.png',
        player_verification/'实际解码帧.png':'播放器实际解码帧.png',
        history_verification/'历史记录验证.json':'历史记录验证.json',
        history_verification/'历史双击实际解码帧.png':'历史双击实际解码帧.png',
        history_verification/'历史页浅色.png':'历史页浅色.png',
        history_verification/'历史页深色.png':'历史页深色.png',
        sound_verification/'声音试听验证.json':'声音试听验证.json',
        sound_verification/'声音设置浅色.png':'声音设置浅色.png',
        sound_verification/'声音设置深色.png':'声音设置深色.png',
        sound_verification/'试听实际解码帧.png':'试听实际解码帧.png',
        sound_verification/'试听进度条.png':'试听进度条.png',
        subtitle_verification/'字幕进度条验证.json':'字幕进度条验证.json',
        subtitle_verification/'字幕进度条浅色.png':'字幕进度条浅色.png',
        subtitle_verification/'字幕进度条深色.png':'字幕进度条深色.png',
        subtitle_verification/'修改字幕后实际帧.png':'修改字幕后实际帧.png',
        root/'docs/DELIVERY.md':'交付说明.md',
        verification/'delivery/gui/播放器实际视频帧.png':'实际解码帧.png',
        verification/'delivery/gui/导出完成.png':'便携导出完成.png'}
    for name in ['缩略图与多选.png','批量设置.png','滚轮安全设置页.png','深色界面.png','网格_1040.png','500项网格.png','空库引导.png','缩略图失败提示.png']:items[verification/'ui'/name]=name
    portable=json.loads((verification/'便携验证.json').read_text(encoding='utf-8'))
    expected={'--self-test','--delivery-test','--screenshot','--ui-test'}
    if not portable.get('passed') or len(portable.get('checks',[]))!=4 or {c['command'] for c in portable['checks']}!=expected or any(c['exit_code'] for c in portable['checks']):
        raise SystemExit('Portable validation must finish successfully before packaging.')
    if hashlib.sha256((package/'MontageStudio/MontageStudio.exe').read_bytes()).hexdigest()!=portable.get('exe_sha256'):
        raise SystemExit('Portable validation does not match the release executable.')
    upgrade=json.loads((upgrade_verification/'升级与图标验证.json').read_text(encoding='utf-8'))
    if not upgrade.get('passed') or upgrade.get('exe_sha256')!=portable.get('exe_sha256'):
        raise SystemExit('Upgrade/icon validation does not match the release executable.')
    isolation=json.loads((isolation_verification/'截图隔离验证.json').read_text(encoding='utf-8'))
    if not isolation.get('passed') or isolation.get('exe_sha256')!=portable.get('exe_sha256'):
        raise SystemExit('Screenshot isolation validation does not match the release executable.')
    cloud=json.loads((cloud_verification/'云端库验证.json').read_text(encoding='utf-8'))
    cloud_hash=portable['exe_sha256']
    if args.cloud_baseline_version:
        baseline=json.loads((release/('交付包校验_'+args.cloud_baseline_version+'.json')).read_text(encoding='utf-8'))
        cloud_hash=baseline['exe_sha256']
        for path in ('montage/cloud.py','montage/cloud_ui.py','montage/media.py','montage/service.py','montage/runtime.py','montage/thumbnails.py','MontageStudio.spec'):
            previous=subprocess.check_output(['git','show','v'+args.cloud_baseline_version+':'+path],cwd=root)
            if previous.replace(b'\r\n',b'\n')!=(root/path).read_bytes().replace(b'\r\n',b'\n'):
                raise SystemExit('Cloud baseline cannot be reused after module changes: '+path)
    if not cloud.get('passed') or len(cloud.get('checks',[]))!=5 or any(not c.get('passed') for c in cloud['checks']) or cloud.get('exe_sha256')!=cloud_hash:
        raise SystemExit('Cloud validation does not match the release executable.')
    player=json.loads((player_verification/'播放器验证.json').read_text(encoding='utf-8'))
    if not player.get('passed') or len(player.get('checks',[]))!=5 or any(not c.get('passed') for c in player['checks']) or player.get('exe_sha256')!=portable.get('exe_sha256'):
        raise SystemExit('Player validation does not match the release executable.')
    if (package/'MontageStudio/data').exists():
        raise SystemExit('Distribution contains user data; do not include it in the release.')
    history=json.loads((history_verification/'历史记录验证.json').read_text(encoding='utf-8'))
    if not history.get('passed') or len(history.get('checks',[]))!=5 or any(not c.get('passed') for c in history['checks']) or history.get('exe_sha256')!=portable.get('exe_sha256'):
        raise SystemExit('History validation does not match the release executable.')
    subtitle=json.loads((subtitle_verification/'字幕进度条验证.json').read_text(encoding='utf-8'))
    if not subtitle.get('passed') or len(subtitle.get('checks',[]))!=6 or any(not c.get('passed') for c in subtitle['checks']) or subtitle.get('exe_sha256')!=portable.get('exe_sha256'):
        raise SystemExit('Subtitle timeline validation does not match the release executable.')
    sound=json.loads((sound_verification/'声音试听验证.json').read_text(encoding='utf-8'))
    if not sound.get('passed') or len(sound.get('checks',[]))!=6 or any(not c.get('passed') for c in sound['checks']) or sound.get('exe_sha256')!=portable.get('exe_sha256'):
        raise SystemExit('Sound audition validation does not match the release executable.')
    for src,dst in items.items():shutil.copy2(src,evidence/dst)
    for src,dst in [('docs/使用说明.md','使用说明.md'),('docs/DELIVERY.md','交付说明.md')]:shutil.copy2(root/src,package/dst)
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    (package/'版本.txt').write_text(args.version+'\nGit: '+revision+'\nWindows x64; Python 3.14.4 / PySide6 6.11.0\n',encoding='utf-8-sig')
    binary_zip=release/('混剪工坊_'+args.version+'_完整便携版.zip')
    with zipfile.ZipFile(binary_zip,'w',zipfile.ZIP_DEFLATED,compresslevel=4) as z:
        for p in sorted(package.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(release))
    source_zip=release/('混剪工坊_'+args.version+'_源码.zip')
    subprocess.run(['git','archive','--format=zip','--prefix=混剪工坊源码/','-o',str(source_zip),'HEAD'],cwd=root,check=True)
    report={'version':args.version,'git':revision,'exe_sha256':portable['exe_sha256'],'user_data_included':False,'archives':[]}
    report['cloud_verification']={'baseline_version':args.cloud_baseline_version or None,'exe_sha256':cloud_hash,'current_exe_retested':not bool(args.cloud_baseline_version)}
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
    (release/('交付包校验_'+args.version+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
else:
    raise SystemExit('Expected prepare or zip')
