import json
import threading
from pathlib import Path
import pytest
from montage.cloud import CloudLibrary, normalize_records
from montage.core import Cancelled


def row(n):
    return dict(record_id='rec'+str(n), **{'描述':'前贴'+str(n), '成品文件':[
        dict(file_token='token'+str(n),name='clip.mp4',size=123),
        dict(file_token='image',name='image.png',size=10)], '备注':'备注', '制作人':['同事']})


def test_projection_only_finished_videos():
    record=row(1);record['参考视频']=[dict(file_token='reference',name='reference.mp4')]
    target=dict(base_token='base',table_id='table')
    result=normalize_records([record],target)
    assert len(result)==1 and result[0]['file_token']=='token1'
    assert result[0]['creator']=='同事' and result[0]['note']=='备注'
    assert normalize_records([record],dict(base_token='other',table_id='table'))[0]['key']!=result[0]['key']


def test_refresh_pagination_commits_only_complete_catalog(tmp_path,monkeypatch):
    library=CloudLibrary(tmp_path);library.library['items']=[dict(key='existing')]
    library.config['access_mode']='account'
    library.library['cache']={'keep':'saved'}
    class CLI:
        work=tmp_path
        fail=False
        def call(self,args,stop):
            if '+url-resolve' in args:return dict(data=dict(resource_type='bitable',base_token='base',table_id='table',view_id='view'))
            assert '--view-id' in args
            offset=int(args[args.index('--offset')+1])
            if self.fail and offset:raise RuntimeError('network')
            filename=args[args.index('--output')+1]
            (tmp_path/filename).write_text(json.dumps(row(offset+1)),encoding='utf-8')
            return dict(records_count=1,has_more=offset==0)
    cli=CLI();monkeypatch.setattr(library,'cli',lambda:cli)
    cli.fail=True
    with pytest.raises(RuntimeError):library.refresh()
    assert library.library['items']==[dict(key='existing')]
    assert not (tmp_path/'library.json').exists()
    cli.fail=False;result=library.refresh()
    assert result['records']==2 and len(result['items'])==2
    assert result['cache']=={'keep':'saved'}
    assert not list(tmp_path.glob('records-*.ndjson'))


def test_sync_failure_cancel_and_offline_reuse(tmp_path,monkeypatch):
    import montage.cloud as cloud
    library=CloudLibrary(tmp_path);library.config['access_mode']='account';target=dict(base_token='base',table_id='table')
    items=normalize_records([row(1),row(2),row(3)],target)
    for item in items:item['size']=3
    original_url=library.config['url']
    library.library.update(target=target,items=items,source_url=original_url)
    class CLI:
        work=tmp_path
        downloads=0
        fail_second=True
        cancel_second=False
        def call(self,args,stop,timeout):
            self.downloads+=1
            if args[args.index('--record-id')+1]=='rec2':
                if self.cancel_second:raise Cancelled()
                if self.fail_second:raise RuntimeError('download failed')
            (self.work/args[args.index('--output')+1]).write_bytes(b'abc')
    cli=CLI();monkeypatch.setattr(library,'cli',lambda:cli)
    monkeypatch.setattr(cloud,'scan',lambda paths,*args:dict(assets=[dict(id='sha',path=str(paths[0]),name='a',role='a')],errors=[]))
    monkeypatch.setattr(cloud,'identity',lambda path:'sha')
    result=library.sync(items)
    assert result['downloaded']==2 and len(result['errors'])==1
    assert len(result['assets'])==2 and not result['cancelled']
    assert not list(tmp_path.rglob('download-*'))
    cli.fail_second=False;cli.cancel_second=True
    result=library.sync(items)
    assert result['cancelled'] and result['reused']==1 and len(result['assets'])==1
    def no_network(*args,**kwargs):raise AssertionError('network called')
    cli.call=no_network
    library.save_config('https://my.feishu.cn/base/other?table=other','')
    result=library.sync([items[0],items[2]])
    assert result['reused']==2 and not result['errors']
    assert all(a['cloud']['source_url']==original_url for a in result['assets'])
    library.library['cache'][items[0]['key']]['relative_path']='../outside.mp4'
    assert library.cached(items[0]) is None


def test_link_validation_keeps_existing_config(tmp_path):
    library=CloudLibrary(tmp_path)
    previous=library.config.copy()
    with pytest.raises(ValueError):library.save_config('https://feishu.cn.evil.example/wiki/id','')
    assert library.config==previous
