from collections import Counter
import itertools
import random
import pytest
from montage.planner import make_plan, PlanError, parse_instruction
from montage.store import Store, identity


def test_production_size():
    a,b=list(range(20)),list(range(500))
    p=make_plan(a,b,1000)
    assert len(set(p))==1000
    assert set(Counter(x for x,y in p).values())=={50}
    assert set(Counter(y for x,y in p).values())=={2}
    p2=make_plan(a,b,1000,fixed={0:200},seed=7)
    assert Counter(x for x,y in p2)[0]==200
    assert set(Counter(x for x,y in p2 if x!=0).values())=={42,43}
    assert set(Counter(y for x,y in p2).values())=={2}
    assert p==make_plan(a,b,1000)


def test_solver_matches_exhaustive_small_cases():
    rng=random.Random(4)
    all_pairs=list(itertools.product(range(3),range(3)))
    for _ in range(60):
        available=rng.sample(all_pairs,rng.randrange(1,10))
        n=rng.randrange(1,len(available)+1)
        fixed={0:rng.randrange(0,4)} if rng.random()<.5 else {}
        def valid(p):
            ac=Counter(x for x,y in p);bc=Counter(y for x,y in p)
            if any(ac[x]!=v for x,v in fixed.items()): return False
            rest=[ac[x] for x in range(3) if x not in fixed]
            return (not rest or max(rest)-min(rest)<=1) and max(bc[x] for x in range(3))-min(bc[x] for x in range(3))<=1
        possible=any(valid(p) for p in itertools.combinations(available,n))
        try:
            result=make_plan(list(range(3)),list(range(3)),n,fixed=fixed,excluded=set(all_pairs)-set(available))
            assert possible and valid(result)
        except PlanError:
            assert not possible


def test_limits_and_language():
    with pytest.raises(PlanError): make_plan(['a'],list(range(500)),600,fixed={'a':600})
    assert parse_instruction('生成1000条，均匀分配，前贴01用200次',20)==dict(count=1000,mode='balanced',fixed={'0':200})
    with pytest.raises(PlanError): parse_instruction('随便做一些',20)
    with pytest.raises(PlanError): parse_instruction('生成10条，允许重复',20)


def test_transactions_history_and_backup(tmp_path):
    s=Store(tmp_path/'db')
    assets={'a':dict(path='a'), 'b':dict(path='b'), 'c':dict(path='c')}
    with pytest.raises(ValueError): s.create('game',assets,[('a','b')],{},[])
    bid=s.create('game',assets,[('a','b'),('a','c')],{},[{},{}])
    assert s.excluded('game')=={('a','b'),('a','c')}
    with pytest.raises(ValueError): s.create('game',assets,[('a','b')],{},[{}])
    assert len(s.batches())==1
    s.update(bid,1,'complete','out.mp4')
    s.update(bid,2,'failed',error='invalid')
    s.backup(tmp_path/'backup.sqlite3')
    s.close()
    s=Store(tmp_path/'db')
    assert len(s.history())==1 and s.jobs(bid)[1]['status']=='failed'
    s.abandon(bid)
    assert s.excluded('game')=={('a','b')}
    with pytest.raises(ValueError): s.update(bid,2,'running')
    s.restore(tmp_path/'backup.sqlite3')
    assert len(s.history())==1 and len(s.excluded('game'))==2
    s.close()


def test_identity(tmp_path):
    p=tmp_path/'前贴.mp4';p.write_bytes(b'video')
    h=identity(p);q=p.rename(tmp_path/'renamed.mp4')
    assert identity(q)==h
    q.write_bytes(b'other')
    assert identity(q)!=h
