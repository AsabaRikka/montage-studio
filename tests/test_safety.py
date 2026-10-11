import json
import pytest
from montage.planner import parse_instruction, PlanError
from montage.service import api_rules
from montage.subtitles import align_script, read_srt, write_srt


def test_instruction_rejects_silent_constraint_loss():
    assert parse_instruction('生成1000条，均匀分配，前贴01用200次，不重复配对，避开历史',20)['fixed']=={'0':200}
    for text in ['生成10条，按内容挑最合适的','生成10条，生成20条','生成10条，不要均匀','生成10条，均匀随机分配','生成10条，允许重复','生成10条，前贴1至少用3次','生成0条']:
        with pytest.raises(PlanError):parse_instruction(text,20)


def test_api_sends_only_instruction_and_validates_response(monkeypatch):
    import requests
    value={'count':10,'mode':'balanced','fixed':{'1':3}}
    def post(url,**kwargs):
        assert url=='https://example.com/v1/chat/completions'
        assert kwargs['json']['messages'][1]['content']=='生成10条'
        assert 'assets' not in kwargs['json']
        class Response:
            def raise_for_status(self):pass
            def json(self):return {'choices':[{'message':{'content':json.dumps(value)}}]}
        return Response()
    monkeypatch.setattr(requests,'post',post)
    assert api_rules('生成10条',2,'https://example.com/v1','test','key')['fixed']=={'0':3}
    for bad in [[],{'count':0,'mode':'random'}, {'count':True,'mode':'random'}, {'count':2,'mode':'random','fixed':[]}, {'count':2,'mode':'random','fixed':{'3':1}}, {'count':2,'mode':'random','command':'rm'}]:
        value=bad
        with pytest.raises(ValueError):api_rules('生成10条',2,'https://example.com/v1','test','key')


def test_script_alignment_and_srt(tmp_path):
    rows=align_script('这是一条字幕。\n这是第二句话。',[],6)
    assert rows[0]['start']==0 and rows[-1]['end']==6
    assert all(a['end']<=b['start'] for a,b in zip(rows,rows[1:]))
    out=tmp_path/'字幕.srt';write_srt(out,rows)
    assert [r['text'] for r in read_srt(out)]==[r['text'] for r in rows]
