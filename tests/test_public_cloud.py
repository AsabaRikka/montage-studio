import copy
import json
import threading
import pytest
from montage.cloud import CloudLibrary, DEFAULT_URL
from montage.core import Cancelled
from montage.public_cloud import PublicFeishu, PublicAccessError, public_rows, safe_host


def table():
    return dict(currentView='v1',viewMap={'v1':{}},recordCount=1,
        groupList=[dict(recordIDList=['r1'])],fieldMap={
            'a':dict(name='成品文件',type=17), 'd':dict(name='描述',type=1),
            'c':dict(name='制作人',type=3,property=dict(options=[dict(id='o1',name='同事')])),
            'other':dict(name='参考视频',type=17)},
        recordMap={'r1':{'a':dict(value=[dict(attachmentToken='f1',name='a.mp4',size=3)]),
            'd':dict(value=[dict(text='前贴',type='text')]),'c':dict(value='o1'),
            'other':dict(value=[dict(attachmentToken='not_allowed',name='other.mp4')])}})


def test_public_view_projection_and_completeness():
    t=table();rows,field=public_rows(t,'v1')
    assert rows[0]['描述']=='前贴' and rows[0]['制作人']=='同事' and field=='a'
    assert '参考视频' not in rows[0]
    for mutation in [dict(currentView='v2'),dict(recordCount=2),dict(recordMap={}),dict(recordPage={'next':1}),dict(deniedRecords=['r1'])]:
        bad=copy.deepcopy(t);bad.update(mutation)
        with pytest.raises(PublicAccessError):public_rows(bad,'v1')


def test_public_urls_and_cancellation():
    assert safe_host('https://my.feishu.cn/wiki/x')
    for url in ['http://my.feishu.cn','https://feishu.cn.evil.com','https://user:secret@my.feishu.cn','https://my.feishu.cn:444']:
        assert not safe_host(url)
    with pytest.raises(PublicAccessError):PublicFeishu('https://my.feishu.cn/base/x?table=t')
    with pytest.raises(PublicAccessError):PublicFeishu('https://my.feishu.cn/base/x?table=t/evil&view=v')
    stop=threading.Event();stop.set()
    with pytest.raises(Cancelled):PublicFeishu(DEFAULT_URL,stop).prepare()


def test_public_refresh_never_uses_cli_and_preserves_failed_catalog(tmp_path,monkeypatch):
    import montage.public_cloud as public
    lib=CloudLibrary(tmp_path);lib.library['cache']={'kept':{'asset':{}}}
    target=dict(base_token='b',table_id='t',view_id='v')
    class Client:
        def __init__(self,*args):pass
        def prepare(self):
            return [dict(record_id='r',描述='a',成品文件=[dict(file_token='f',name='a.mp4',size=3)])],target
    monkeypatch.setattr(public,'PublicFeishu',Client)
    monkeypatch.setattr(lib,'cli',lambda:pytest.fail('CLI used'))
    r=lib.refresh();assert r['access_mode']=='public' and len(r['items'])==1
    before=(tmp_path/'library.json').read_bytes()
    def fail(*args):raise PublicAccessError('share closed')
    monkeypatch.setattr(Client,'prepare',fail)
    with pytest.raises(PublicAccessError):lib.refresh()
    assert (tmp_path/'library.json').read_bytes()==before and lib.library['cache']=={'kept':{'asset':{}}}


def test_old_config_defaults_public_without_deleting_cache(tmp_path):
    (tmp_path/'config.json').write_text(json.dumps(dict(url=DEFAULT_URL,profile='old')),encoding='utf-8')
    lib=CloudLibrary(tmp_path);lib.save_config(DEFAULT_URL,'old')
    assert lib.config['access_mode']=='public' and lib.config['profile']=='old'


def test_migrated_account_catalog_never_uses_cli_in_public_mode(tmp_path,monkeypatch):
    import montage.public_cloud as public
    lib=CloudLibrary(tmp_path)
    item=dict(key='k',name='a',filename='a.mp4',record_id='r',file_token='f',size=1)
    lib.library=dict(access_mode='account',target={},items=[item],cache={},source_url=DEFAULT_URL)
    calls=[]
    class Client:
        def __init__(self,*args):pass
        def download(self,*args):
            calls.append(True)
            raise PublicAccessError('公开下载限制')
    monkeypatch.setattr(public,'PublicFeishu',Client)
    monkeypatch.setattr(lib,'cli',lambda:pytest.fail('old catalog invoked CLI'))
    result=lib.sync([item]);assert calls==[True] and result['errors'] and result['downloaded']==0


def test_public_sync_failure_cancel_cleanup_and_completed_reuse(tmp_path,monkeypatch):
    import montage.public_cloud as public
    import montage.cloud as cloud
    lib=CloudLibrary(tmp_path)
    target=dict(base_token='b',table_id='t',view_id='v')
    items=[dict(key=k,record_id=k,file_token=k,filename=k+'.mp4',name=k,size=3) for k in ['ok','bad','cancel']]
    lib.library=dict(target=target,items=items,cache={},access_mode='public',source_url=DEFAULT_URL)
    class Client:
        def __init__(self,*args):pass
        def download(self,item,target,path):
            path.write_bytes(b'abc')
            if item['key']=='bad':raise PublicAccessError('网络中断')
            if item['key']=='cancel':raise Cancelled()
    monkeypatch.setattr(public,'PublicFeishu',Client)
    monkeypatch.setattr(cloud,'scan',lambda paths,*args:dict(assets=[dict(path=str(paths[0]),id=cloud.identity(paths[0]))]))
    monkeypatch.setattr(lib,'cli',lambda:pytest.fail('CLI used'))
    result=lib.sync(items)
    assert result['downloaded']==1 and result['cancelled'] and len(result['errors'])==1
    assert len(result['assets'])==1 and set(lib.library['cache'])=={'ok'}
    assert not list(tmp_path.rglob('download-*'))
    monkeypatch.setattr(Client,'download',lambda *args:pytest.fail('offline used network'))
    reopened=CloudLibrary(tmp_path);result=reopened.sync(items[:1])
    assert result['reused']==1 and not result['errors']
