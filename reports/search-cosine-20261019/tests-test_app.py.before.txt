import json
import pytest
from streamlit.testing.v1 import AppTest
from ir_hw3.corpus import ROOT
from ir_hw3 import evaluation

@pytest.fixture(autouse=True)
def isolated_manual_file(tmp_path, monkeypatch):
    """UI tests must never create or change the user's actual manual judgments."""
    path = tmp_path / "manual.json"
    load, save = evaluation.load_judgments, evaluation.save_judgments
    monkeypatch.setattr(evaluation, "load_judgments",
                        lambda corpus, queries, docs, path=path: load(corpus, queries, docs, path))
    monkeypatch.setattr(evaluation, "save_judgments",
                        lambda corpus, queries, docs, rows, path=path, **kwargs:
                        save(corpus, queries, docs, rows, path, **kwargs))
    return path

def start():
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=40).run()

def test_search_top10_reader_and_oov():
    app = start()
    assert not app.exception
    assert len(app.dataframe[0].value) == 10
    assert "score" in app.dataframe[0].value.columns
    app.text_input[0].set_value("totallyunknownwordxyz")
    next(button for button in app.button if button.label == "搜尋").click().run()
    assert not app.exception
    assert any("沒有非零" in info.value for info in app.info)

def test_all_four_pages_and_weak_evaluation():
    app = start()
    for page in ("語料與設定", "方法比較", "效能評估"):
        app.sidebar.radio[0].set_value(page).run()
        assert not app.exception, str(app.exception)
        if page == "語料與設定":
            formulas = next(frame.value for frame in app.dataframe if "公式（f > 0）" in frame.value.columns)
            assert "1 + log10(f)" in formulas["公式（f > 0）"].tolist()
            assert any("log10" in item.value for item in app.info)
    assert app.metric[0].value == "0 / 10"
    next(radio for radio in app.radio if radio.label == "評估標註來源").set_value("規則弱標籤（示範）").run()
    next(button for button in app.button if button.label == "執行六種方法評估").click().run()
    assert not app.exception
    assert any("judgment_source" in frame.value.columns and len(frame.value) == 6 for frame in app.dataframe)
    spec = json.loads(app.get("vega_lite_chart")[0].proto.spec)
    assert spec["encoding"]["y"]["scale"]["domain"] == [0, 1]
    assert "xOffset" in spec["encoding"]

def widget(app, kind, label):
    return next(item for item in getattr(app, kind) if item.label == label)


def test_bm25_search_reader_comparison_and_evaluation():
    app = start()
    methods = widget(app, "selectbox", "權重方法")
    assert methods.options[-1] == "BM25" and len(methods.options) == 6
    methods.set_value("bm25")
    widget(app, "checkbox", "先做 L2 正規化").set_value(True)
    widget(app, "button", "搜尋").click().run()
    assert not app.exception
    assert any(m.label == "最高 BM25" for m in app.metric)
    assert any("bm25_contribution" in f.value.columns for f in app.dataframe)
    assert not any("cosine_contribution" in f.value.columns for f in app.dataframe)
    scores = app.dataframe[0].value["score"].tolist()
    widget(app, "selectbox", "IDF 定義").set_value("smooth").run()
    assert app.dataframe[0].value["score"].tolist() == scores
    app.sidebar.radio[0].set_value("方法比較").run()
    assert not app.exception
    assert "BM25" in app.dataframe[0].value.columns
    assert len(widget(app, "selectbox", "點積對照的權重").options) == 5
    widget(app, "selectbox", "比較方法").set_value("bm25").run()
    assert not app.exception
    app.sidebar.radio[0].set_value("效能評估").run()
    widget(app, "radio", "評估標註來源").set_value("規則弱標籤（示範）").run()
    widget(app, "button", "執行六種方法評估").click().run()
    assert not app.exception
    summary = next(f.value for f in app.dataframe if "precision_at_k" in f.value.columns)
    assert summary["method"].tolist()[-1] == "bm25" and len(summary) == 6


def test_pubmed_reference_ui_discloses_sources_and_keeps_manual_empty(isolated_manual_file):
    app = start()
    app.sidebar.radio[0].set_value("效能評估").run()
    widget(app, "radio", "評估標註來源").set_value("PubMed 主題參考＋弱規則回退").run(timeout=60)
    assert not app.exception
    coverage = next(f.value for f in app.dataframe if "metadata_positive" in f.value.columns)
    assert len(coverage) == 10 and (coverage["documents"] == 3000).all()
    assert (coverage["metadata_positive"] + coverage["weak_fallback"] == 3000).all()
    widget(app, "button", "執行六種方法評估").click().run()
    assert not app.exception
    summary = next(f.value for f in app.dataframe if "precision_at_k" in f.value.columns)
    assert (summary["judgment_source"] == "pubmed_hybrid").all()
    assert (summary["queries_evaluated"] == 10).all()
    assert app.metric[0].value == "0 / 10"
    assert not isolated_manual_file.exists()

def annotation_app():
    app = start()
    app.sidebar.radio[0].set_value("效能評估").run()
    assert not app.exception
    return app

def test_annotation_drafts_survive_document_query_page_and_settings_navigation(isolated_manual_file):
    app = annotation_app()
    first = widget(app, "selectbox", "閱讀待標註摘要").value
    widget(app, "selectbox", "這篇文件的相關性").set_value(2)
    widget(app, "text_area", "這篇文件的判斷依據").set_value("測試草稿：摘要提供直接證據。")
    app.run()
    widget(app, "button", "下一篇").click().run()
    assert widget(app, "selectbox", "閱讀待標註摘要").value != first
    widget(app, "button", "上一篇").click().run()
    assert widget(app, "selectbox", "這篇文件的相關性").value == 2
    assert "直接證據" in widget(app, "text_area", "這篇文件的判斷依據").value
    queries = evaluation.load_queries()
    widget(app, "selectbox", "標註查詢").set_value(queries[1]).run()
    widget(app, "selectbox", "標註查詢").set_value(queries[0]).run()
    app.sidebar.radio[0].set_value("搜尋與排名").run()
    assert any("未儲存" in warning.value for warning in app.warning)
    app.sidebar.radio[0].set_value("效能評估").run()
    assert widget(app, "selectbox", "這篇文件的相關性").value == 2
    assert "直接證據" in widget(app, "text_area", "這篇文件的判斷依據").value
    widget(app, "radio", "文件範圍").set_value("全部 3,000 篇").run()
    widget(app, "radio", "文件範圍").set_value("六種方法 Top 20 聯集").run()
    assert widget(app, "selectbox", "這篇文件的相關性").value == 2
    assert not isolated_manual_file.exists()
    assert not app.exception

def test_annotation_requires_reason_then_saves_only_changed_record(isolated_manual_file):
    app = annotation_app()
    pmid = widget(app, "selectbox", "閱讀待標註摘要").value
    widget(app, "selectbox", "這篇文件的相關性").set_value(0).run()
    widget(app, "button", "儲存這篇人工標註").click().run()
    assert not isolated_manual_file.exists()
    assert any("草稿仍保留" in error.value for error in app.error)
    widget(app, "text_area", "這篇文件的判斷依據").set_value("測試負例：研究主體不同。").run()
    widget(app, "button", "儲存這篇人工標註").click().run()
    saved = json.loads(isolated_manual_file.read_text(encoding="utf-8"))
    assert saved["judgments"] == {"Q01": {pmid: {"grade": 0, "reason": "測試負例：研究主體不同。"}}}
    assert any("已儲存 1 筆變更" in success.value for success in app.success)
    statuses = next(frame.value for frame in app.dataframe if "status" in frame.value.columns)
    assert statuses.iloc[0]["status"] == "已判讀，但尚未找到相關文件"
    assert not statuses.iloc[0]["included_in_mean"]
    assert not app.exception

def test_zero_evaluation_denominator_is_not_zero_score():
    app = annotation_app()
    widget(app, "button", "執行六種方法評估").click().run()
    summary = next(frame.value for frame in app.dataframe if "queries_evaluated" in frame.value.columns)
    assert (summary["queries_total"] == 10).all()
    assert (summary["queries_evaluated"] == 0).all()
    assert summary["precision_at_k"].isna().all()
    assert not app.exception

def test_unjudged_notes_cannot_be_silently_dropped_by_save_all(isolated_manual_file):
    app = annotation_app()
    widget(app, "text_area", "這篇文件的判斷依據").set_value("待釐清納排條件。").run()
    widget(app, "button", "儲存全部草稿").click().run()
    assert not isolated_manual_file.exists()
    assert any("未標註草稿含有理由" in error.value for error in app.error)
    assert widget(app, "text_area", "這篇文件的判斷依據").value == "待釐清納排條件。"
    assert not app.exception

def test_write_failure_keeps_annotation_draft(isolated_manual_file, monkeypatch):
    def failed_save(*args, **kwargs):
        raise OSError("測試模擬磁碟寫入失敗")
    monkeypatch.setattr(evaluation, "save_judgments", failed_save)
    app = annotation_app()
    widget(app, "selectbox", "這篇文件的相關性").set_value(1)
    widget(app, "text_area", "這篇文件的判斷依據").set_value("測試：有具體證據。")
    app.run()
    widget(app, "button", "儲存這篇人工標註").click().run()
    assert not isolated_manual_file.exists()
    assert any("草稿仍保留" in error.value and "磁碟" in error.value for error in app.error)
    assert widget(app, "text_area", "這篇文件的判斷依據").value == "測試：有具體證據。"
    assert not app.exception
