from __future__ import annotations
import csv
import json
import re
import threading
import time
from collections import Counter
from pathlib import Path
from .core import DEFAULTS, Cancelled, probe
from .media import MediaEngine
from .store import Store, identity
from .runtime import data_dir, write_json

SETTINGS = dict(DEFAULTS, transition='cut', audio_transition='cut', performance='background',
    a_sound='original', b_sound='original', a_music='', b_music='', a_voice='', b_voice='',
    a_volume=1., b_volume=1., a_music_volume=.3, b_music_volume=.3,
    a_music_start=0., b_music_start=0., music_mode='none', b_music_mode='none', subtitle_rows=None)


def scan(paths, role, stop=None, notify=None):
    result, errors, seen = [], [], set()
    for n,path in enumerate(paths):
        if stop and stop.is_set():
            raise Cancelled()
        path = Path(path).resolve()
        if notify:
            notify(dict(type='log', text=f'检查{n+1}/{len(paths)}：{path.name}'))
        try:
            info = probe(path)
            if role in ('a','b') and not info['video'] or role == 'music' and not info['audio']:
                raise ValueError('素材类型不匹配。')
            key = identity(path)
            if key in seen:
                continue
            seen.add(key)
            result.append(dict(id=key,path=str(path),name=path.name,duration=info['duration'],
                width=info['width'],height=info['height'],audio=bool(info['audio']),role=role))
        except Exception as exc:
            errors.append(path.name+'：'+str(exc)[-450:])
    return dict(assets=result, errors=errors)


def safe_name(name):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_',Path(name).stem).strip(' .')[:40] or 'video'


def job_output(batch, job):
    folder = Path(batch['settings']['output'])/('任务_'+batch['id'][:8])
    if job['settings'].get('output_name'):
        return folder/job['settings']['output_name']
    assets = batch['assets']
    return folder/f'{job["number"]:05d}_{safe_name(assets[job["a"]]["name"])}__{safe_name(assets[job["b"]]["name"])}.mp4'


def write_report(store,bid):
    batch=store.batch(bid)
    folder=Path(batch['settings']['output'])/('任务_'+bid[:8])
    folder.mkdir(parents=True,exist_ok=True)
    jobs=store.jobs(bid)
    fields=['序号','前贴','主视频','状态','前贴音乐','主视频音乐','转场','输出','错误']
    temp=folder/'任务清单.csv.tmp'
    labels=dict(pending='待处理',running='处理中',complete='完成',failed='失败',cancelled='已放弃')
    with temp.open('w',encoding='utf-8-sig',newline='') as file:
        writer=csv.writer(file)
        writer.writerow(fields)
        for job in jobs:
            s=job['settings']
            writer.writerow([job['number'],batch['assets'][job['a']]['name'],batch['assets'][job['b']]['name'],labels[job['status']],
                s.get('a_music',''),s.get('b_music',''),s.get('transition','cut'),job['output'],job['error']])
    temp.replace(folder/'任务清单.csv')
    write_json(folder/'任务配方.json',dict(batch=batch,jobs=jobs))


def run_batch(bid,stop=None,notify=None,folder=None,retry=False):
    stop=stop or threading.Event()
    notify=notify or (lambda _:None)
    store=Store(folder)
    engine=MediaEngine(stop,lambda t:notify(dict(type='log',text=t)),folder)
    started=time.monotonic()
    batch=store.batch(bid)
    jobs=store.jobs(bid)
    eligible=[j for j in jobs if j['status'] in ('pending','running') or retry and j['status']=='failed']
    try:
        # Verify source identity once per batch run; never export changed files under
        # a saved history identity. Missing media can be relocated by the GUI.
        referenced=set()
        for job in eligible:
            referenced.update((job['a'],job['b']))
            referenced.update(job['settings'].get('dependency_ids',[]))
        problems={}
        for key in referenced:
            if stop.is_set():
                raise Cancelled()
            try:
                p=batch['assets'][key]['path']
                notify(dict(type='log',text='核对原素材：'+Path(p).name))
                if identity(p)!=key:
                    raise ValueError('内容已改变，请重新导入；旧任务不能替换为不同素材。')
            except Exception as exc:
                problems[key]=str(exc)
        for job in eligible:
            if stop.is_set():
                break
            number=job['number']
            s=job['settings'].copy()
            bad=[problems[k] for k in [job['a'],job['b'],*s.get('dependency_ids',[])] if k in problems]
            if bad:
                store.update(bid,number,'failed',error='；'.join(bad))
                notify(dict(type='job',number=number,status='failed',error='；'.join(bad)))
                continue
            for field,key in s.get('media_ids',{}).items():
                s[field]=batch['assets'][key]['path']
            out=job_output(batch,job)
            store.update(bid,number,'running')
            notify(dict(type='job',number=number,status='running'))
            try:
                engine.render_pair(batch['assets'][job['a']]['path'],batch['assets'][job['b']]['path'],s,out,
                    progress=lambda p:notify(dict(type='progress',number=number,value=p)))
                store.update(bid,number,'complete',str(out))
                notify(dict(type='job',number=number,status='complete',output=str(out)))
            except Cancelled:
                store.update(bid,number,'pending')
                notify(dict(type='job',number=number,status='pending'))
                break
            except Exception as exc:
                store.update(bid,number,'failed',error=str(exc)[-2200:])
                notify(dict(type='job',number=number,status='failed',error=str(exc)[-2200:]))
            if number%10==0:
                try:
                    write_report(store,bid)
                except OSError as exc:
                    notify(dict(type='log',text='结果报告暂无法写入：'+str(exc)))
        try:
            write_report(store,bid)
        except OSError as exc:
            notify(dict(type='log',text='结果报告无法写入：'+str(exc)))
        return dict(counts=dict(Counter(j['status'] for j in store.jobs(bid))),seconds=round(time.monotonic()-started,2),paused=stop.is_set())
    finally:
        engine.close()
        store.close()


def api_rules(text, intro_count, endpoint, model, key):
    """Send rule text only. Never send paths, audio, frames, or material names."""
    import requests
    if not endpoint.startswith('https://') and not endpoint.startswith(('http://127.0.0.1:','http://localhost:')):
        raise ValueError('接口必须是HTTPS，或本机HTTP服务。')
    prompt=f'把视频组合指令转换为JSON。前贴有{intro_count}条，以1为起始编号。只支持count整数、mode为balanced或random、fixed为前贴编号到次数的对象。始终不重复。无法理解、要求重复或涉及其他操作时返回error说明。不要添加未要求的操作。只返回JSON。'
    response=requests.post(endpoint.rstrip('/')+'/chat/completions',headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},json=dict(model=model,messages=[dict(role='system',content=prompt),dict(role='user',content=text)],temperature=0),timeout=(10,60))
    response.raise_for_status()
    raw=response.json()['choices'][0]['message']['content'].strip()
    raw=re.sub(r'^```(?:json)?\s*|\s*```$','',raw)
    result=json.loads(raw)
    if not isinstance(result,dict):
        raise ValueError('AI返回的规则不是对象，请使用表单。')
    if result.get('error'):
        raise ValueError(result['error'])
    if not isinstance(result,dict) or set(result)-{'count','mode','fixed'} or type(result.get('count')) is not int or not 1<=result['count']<=100000 or result.get('mode') not in ('balanced','random') or not isinstance(result.get('fixed',{}),dict):
        raise ValueError('AI返回的规则格式不合法，请使用表单。')
    fixed={}
    for index,n in result.get('fixed',{}).items():
        if not str(index).isdigit() or not 1<=int(index)<=intro_count or type(n) is not int or n<0:
            raise ValueError('AI返回了不存在的前贴或无效次数。')
        fixed[str(int(index)-1)]=n
    return dict(count=result['count'],mode=result['mode'],fixed=fixed)
