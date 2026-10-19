"""Interactive spelling must be explicit and separate from formal evaluation."""
import ast
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest
from ir_hw3.core import Engine
from ir_hw3.corpus import ROOT
from ir_hw3.evaluation import load_queries


def widget(app, kind, label):
    return next(item for item in getattr(app, kind) if item.label == label)


def start():
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    assert not app.exception
    return app


def test_preview_does_not_rank_and_original_can_be_searched(monkeypatch):
    calls = []
    rank = Engine.rank
    def spy(self, query, *args, **kwargs):
        calls.append(query)
        return rank(self, query, *args, **kwargs)
    monkeypatch.setattr(Engine, "rank", spy)
    app = start()
    initial = list(calls)
    old_query = app.session_state["active_search"]["query"]
    widget(app, "text_input", "英文查詢").set_value("insulinn glucosee").run()
    assert not app.exception
    assert calls == initial
    assert widget(app, "button", "insulin")
    assert widget(app, "button", "glucose")
    assert app.session_state["active_search"]["query"] == old_query
    assert any("尚未搜尋" in item.value for item in app.info)
    widget(app, "button", "搜尋").click().run()
    assert not app.exception
    assert calls[-1] == "insulinn glucosee"
    assert app.session_state["active_search"]["query"] == "insulinn glucosee"
    assert any(item.value == "實際搜尋查詢：insulinn glucosee" for item in app.caption)
    assert not app.success


def test_adopt_one_word_updates_input_display_and_actual_ranking_once(monkeypatch):
    calls = []
    rank = Engine.rank
    def spy(self, query, *args, **kwargs):
        calls.append(query)
        return rank(self, query, *args, **kwargs)
    monkeypatch.setattr(Engine, "rank", spy)
    app = start()
    original = "(insulinn), glucosee; GLP-1"
    corrected = "(insulin), glucosee; GLP-1"
    widget(app, "text_input", "英文查詢").set_value(original).run()
    before = len(calls)
    widget(app, "button", "insulin").click().run()
    assert not app.exception
    assert len(calls) == before + 1 and calls[-1] == corrected
    assert widget(app, "text_input", "英文查詢").value == corrected
    assert app.session_state["active_search"]["query"] == corrected
    assert any(original + " → " + corrected in item.value for item in app.success)
    assert any(item.value == "實際搜尋查詢：" + corrected for item in app.caption)
    app.run()
    assert not app.exception
    assert len(calls) == before + 1
    assert app.session_state["active_search"]["query"] == corrected


def test_stale_adoption_leaves_new_draft_and_search_unchanged():
    # Execute the callback alone with a session-state double; no Streamlit run.
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    callback = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "commit_search")
    state = {"search_query": "newer input", "active_search": {"query": "old search"}}
    namespace = {"st": SimpleNamespace(session_state=state)}
    exec(compile(ast.Module(body=[callback], type_ignores=[]), "callback", "exec"), namespace)
    namespace["commit_search"]("insulinn", "insulin")
    assert state == {"search_query": "newer input", "active_search": {"query": "old search"}}


def test_delayed_button_click_in_streamlit_cannot_replace_new_input():
    app = start()
    initial = dict(app.session_state["active_search"])
    widget(app, "text_input", "英文查詢").set_value("insulinn").run()
    widget(app, "text_input", "英文查詢").set_value("newer input")
    widget(app, "button", "insulin").click().run()
    assert not app.exception
    assert widget(app, "text_input", "英文查詢").value == "newer input"
    assert app.session_state["active_search"] == initial


@pytest.mark.parametrize("source", ["人工標註", "規則弱標籤（示範）", "PubMed 主題參考＋弱規則回退"])
def test_adoption_never_changes_formal_evaluation_queries(monkeypatch, source):
    from ir_hw3 import evaluation
    received = []
    evaluate = evaluation.evaluate
    def spy(engine, queries, judgments, *args, **kwargs):
        received.append(([dict(query) for query in queries], judgments["source"]))
        return evaluate(engine, queries, judgments, *args, **kwargs)
    monkeypatch.setattr(evaluation, "evaluate", spy)
    app = start()
    widget(app, "text_input", "英文查詢").set_value("insulinn").run()
    widget(app, "button", "insulin").click().run()
    assert app.session_state["active_search"]["query"] == "insulin"
    app.sidebar.radio[0].set_value("效能評估").run()
    widget(app, "radio", "評估標註來源").set_value(source).run()
    widget(app, "button", "執行六種方法評估").click().run()
    assert not app.exception
    assert received and received[-1][0] == load_queries()
    assert all(query["text"] != "insulin" for query in received[-1][0])


def test_protected_terms_have_no_adoption_buttons_and_clear_preview():
    app = start()
    widget(app, "text_input", "英文查詢").set_value("insulinn").run()
    assert widget(app, "button", "insulin")
    widget(app, "text_input", "英文查詢").set_value("GLP-1 BRCA1 TNF mTOR eGFR 1.5 cancerr-treatment").run()
    assert not app.exception
    assert not any(button.key and button.key.startswith("spelling_") for button in app.button)
    widget(app, "text_input", "英文查詢").set_value("").run()
    assert not any(button.key and button.key.startswith("spelling_") for button in app.button)
