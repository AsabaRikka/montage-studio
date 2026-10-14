from montage.naming import output_names, clean, display_name
from montage.store import Store
from montage.service import job_output


def test_rules_descriptions_dates_and_custom():
    assets={'a':dict(name='旧名 · a.mp4',cloud=dict(name='不烧心10.14'),custom_name='开头甲'),
            'b':dict(name='游戏.广告.MP4')}
    assert output_names(assets,[('a','b')],'b_a')==['游戏.广告_不烧心10.14.mp4']
    assert output_names(assets,[('a','b')],'a_date_b','10.14')==['不烧心10.1410.14_游戏.广告.mp4']
    assert output_names(assets,[('a','b')],'custom_b')==['开头甲_游戏.广告.mp4']
    assets['a'].pop('custom_name')
    assert display_name(assets['a'])=='不烧心10.14'


def test_windows_collisions_and_reserved_names():
    assets={'a':dict(name='A/甲'), 'a2':dict(name='A?甲'),
            'b':dict(name='Clip.mp4'), 'b2':dict(name='clip.mp4'), 'b3':dict(name='Clip_A_甲_2.mp4')}
    result=output_names(assets,[('a','b'),('a2','b'),('a','b2')],'b_a')
    assert result==['Clip_A_甲.mp4','Clip_A_甲_2.mp4','clip_A_甲_3.mp4']
    assert clean('CON')=='_CON' and clean('NUL.mp4')=='_NUL.mp4'
    assert clean(' . ' )=='video' and len(clean('长'*200))==72


def test_snapshots_retry_and_legacy(tmp_path):
    assets={'a':dict(name='前贴.mp4'), 'a2':dict(name='前贴.mp4'), 'b':dict(name='主片.mp4')}
    with_store=Store(tmp_path)
    try:
        settings=dict(output=str(tmp_path/'out'),naming_rule='b_a')
        bid=with_store.create('new',assets,[('a','b'),('a2','b')],settings,[{},{}])
        jobs=with_store.jobs(bid);batch=with_store.batch(bid)
        assert [job_output(batch,j).name for j in jobs]==['主片_前贴.mp4','主片_前贴_2.mp4']
        assets['a']['name']='改变后的名称'
        assert job_output(with_store.batch(bid),with_store.jobs(bid)[0]).name=='主片_前贴.mp4'
        with_store.update(bid,1,'failed',error='retry')
        assert job_output(with_store.batch(bid),with_store.jobs(bid)[0]).name=='主片_前贴.mp4'
        old=with_store.create('old',assets,[('a2','b')],dict(output=str(tmp_path/'out')),[{}])
        assert job_output(with_store.batch(old),with_store.jobs(old)[0]).name=='00001_前贴__主片.mp4'
    finally:with_store.close()
