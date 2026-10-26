"""New query intent must not reuse old labels even when Q01 IDs are unchanged."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from ir_hw3.core import Engine
from ir_hw3.corpus import ROOT, load_corpus, sha256
from ir_hw3 import evaluation
from ir_hw3.evaluation import load_queries, fingerprint
from ir_hw3.pubmed_reference import load_rules, reference_judgments
from ir_hw3.query_design import CASE_ORDER, classify, load_design, term_profile
from test_core import documents


def test_four_measured_classes_and_exact_six_pairs_are_the_active_presets():
    queries = load_queries()
    assert [tuple(q['types']) for q in queries] == CASE_ORDER
    assert len({q['text'] for q in queries}) == 10
    engine = Engine(load_corpus()[0])
    design = load_design(queries)
    assert design['documents'] == 3000
    for anchor in design['anchors']:
        profile = term_profile(engine, anchor['term'])
        assert profile['df'] == anchor['df']
        assert profile['mean_positive_tf'] == anchor['mean_positive_tf']
        assert classify(profile) == anchor['category']
    for query in queries:
        assert len(engine.query(query['text'], 'tf')[0]) == len(query['types'])
        assert len(query['groups']) == len(query['types'])


def test_new_rules_reject_changed_queries_even_with_the_same_ids():
    queries = load_queries()
    rules = load_rules()
    assert rules['queries_sha256'] == fingerprint(queries)
    changed = deepcopy(queries)
    changed[0]['text'] = 'semaglutide'
    engine = Engine(documents('alpha'))
    metadata = {'documents': {'1': {'entries': []}}, 'counts': {}}
    with pytest.raises(ValueError, match='查詢版本不符'):
        reference_judgments(engine, changed, 'corpus', metadata, rules)
    with pytest.raises(ValueError, match='查詢版本不符'):
        load_design(changed)


def test_manual_judgments_separate_query_versions_and_preserve_both(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluation, 'ROOT', tmp_path)
    manual = tmp_path / 'data/judgments/manual.json'
    monkeypatch.setattr(evaluation, 'JUDGMENTS', manual)
    old = [{'qid': 'Q01', 'text': 'old topic'}]
    new = [{'qid': 'Q01', 'text': 'new topic'}]
    evaluation.save_judgments('same-corpus', old, ['1'], [{'qid': 'Q01', 'pmid': '1', 'grade': 1, 'reason': 'old evidence'}])
    before = manual.read_bytes()
    assert evaluation.load_judgments('same-corpus', new, ['1'])['judgments'] == {}
    evaluation.save_judgments('same-corpus', new, ['1'], [{'qid': 'Q01', 'pmid': '1', 'grade': 0, 'reason': 'new evidence'}])
    assert manual.read_bytes() == before
    assert evaluation.judgment_path('same-corpus', new) != manual
    assert evaluation.load_judgments('same-corpus', old, ['1'])['judgments']['Q01']['1']['grade'] == 1
    assert evaluation.load_judgments('same-corpus', new, ['1'])['judgments']['Q01']['1']['grade'] == 0


def test_archived_biomedical_queries_and_rules_are_preserved():
    archives = list((ROOT / 'data/query_sets').glob('*/manifest.json'))
    original = next(path for path in archives if json.loads((path.parent/'queries.json').read_text(encoding='utf-8'))[0]['text']=='semaglutide weight loss obesity')
    manifest = json.loads(original.read_text(encoding='utf-8'))
    assert sha256(original.parent/'queries.json') == manifest['queries_file_sha256']
    assert sha256(original.parent/'reference_rules.json') == manifest['reference_rules_file_sha256']
    assert manifest['queries_sha256'] != fingerprint(load_queries())


def test_search_has_all_ten_presets_fills_input_then_searches_without_changing_formal_queries():
    queries = load_queries()
    version = fingerprint(queries)
    app = AppTest.from_file(str(ROOT/'app.py'), default_timeout=60).run()
    assert not app.exception
    assert app.session_state['active_search']['query'] == queries[0]['text']
    widget = next(item for item in app.selectbox if item.label=='預設查詢（Q01～Q10）')
    assert len(widget.options) == 10
    labels = ['高 TF 高 DF', '低 TF 高 DF', '高 TF 低 DF', '低 TF 低 DF']
    expected = [f"{q['qid']} · {q['text']}（{' 搭配 '.join(labels[i-1] for i in q['types'])}）" for q in queries]
    assert widget.options == expected
    old = dict(app.session_state['active_search'])
    widget.set_value(queries[6]).run()
    assert not app.exception
    assert next(item for item in app.text_input if item.label=='英文查詢').value == queries[6]['text']
    assert app.session_state['active_search'] == old
    next(item for item in app.button if item.label=='搜尋').click().run()
    assert not app.exception
    assert app.session_state['active_search']['query'] == queries[6]['text']
    assert fingerprint(load_queries()) == version
    app.sidebar.radio[0].set_value('方法比較').run()
    comparison = next(item for item in app.selectbox if item.label=='對照查詢')
    assert len(comparison.options) == 10
    assert comparison.options == expected
    comparison.set_value(queries[9]).run()
    assert not app.exception
    assert next(item for item in app.text_input if item.label=='比較查詢文字').value == queries[9]['text']
