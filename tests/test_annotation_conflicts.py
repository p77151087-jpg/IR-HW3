"""UI regression checks for stale annotation widgets and saved-record conflicts."""
import json

import pytest
from test_app import annotation_app

from ir_hw3 import evaluation


@pytest.fixture
def manual_path(tmp_path, monkeypatch):
    path = tmp_path / "manual.json"
    load, save = evaluation.load_judgments, evaluation.save_judgments
    monkeypatch.setattr(evaluation, "load_judgments",
                        lambda corpus, queries, docs, path=path: load(corpus, queries, docs, path))
    monkeypatch.setattr(evaluation, "save_judgments",
                        lambda corpus, queries, docs, rows, path=path, **kwargs:
                        save(corpus, queries, docs, rows, path, **kwargs))
    return path


def widget(app, kind, label):
    return next(item for item in getattr(app, kind) if item.label == label)


def saved_annotation_app():
    app = annotation_app()
    pmid = widget(app, "selectbox", "閱讀待標註摘要").value
    widget(app, "selectbox", "這篇文件的相關性").set_value(1)
    widget(app, "text_area", "這篇文件的判斷依據").set_value("初始原因 A")
    app.run()
    widget(app, "button", "儲存這篇人工標註").click().run()
    assert not app.exception
    return app, pmid


def external_update(path, pmid):
    value = json.loads(path.read_text(encoding="utf-8"))
    value["judgments"]["Q01"][pmid] = {"grade": 2, "reason": "另一位判讀者的新原因 B"}
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return value


def test_clean_widgets_refresh_latest_saved_record_before_further_edits(manual_path):
    app, pmid = saved_annotation_app()
    external_update(manual_path, pmid)
    app.run()
    assert widget(app, "selectbox", "這篇文件的相關性").value == 2
    assert widget(app, "text_area", "這篇文件的判斷依據").value == "另一位判讀者的新原因 B"
    # Changing one field must not reintroduce the stale value of the other field.
    widget(app, "selectbox", "這篇文件的相關性").set_value(0).run()
    widget(app, "button", "儲存這篇人工標註").click().run()
    saved = json.loads(manual_path.read_text(encoding="utf-8"))
    assert saved["judgments"]["Q01"][pmid] == {"grade": 0, "reason": "另一位判讀者的新原因 B"}
    assert not app.exception


def test_dirty_conflict_keeps_draft_and_restore_loads_latest_saved_record(manual_path):
    app, pmid = saved_annotation_app()
    widget(app, "text_area", "這篇文件的判斷依據").set_value("本連線未儲存的原因 C").run()
    expected = external_update(manual_path, pmid)
    app.run()
    assert widget(app, "text_area", "這篇文件的判斷依據").value == "本連線未儲存的原因 C"
    widget(app, "button", "儲存這篇人工標註").click().run()
    assert json.loads(manual_path.read_text(encoding="utf-8")) == expected
    assert any("草稿仍保留" in error.value and "重新載入" in error.value for error in app.error)
    assert widget(app, "text_area", "這篇文件的判斷依據").value == "本連線未儲存的原因 C"
    widget(app, "button", "還原這篇為已儲存版本").click().run()
    assert widget(app, "selectbox", "這篇文件的相關性").value == 2
    assert widget(app, "text_area", "這篇文件的判斷依據").value == "另一位判讀者的新原因 B"
    assert not app.exception
