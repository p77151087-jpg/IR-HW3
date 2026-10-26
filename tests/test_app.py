import json
from html.parser import HTMLParser
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
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()


def overview_table(app):
    markup = next(item.proto.body for item in app.get("html") if "rank-overview-table" in item.proto.body)

    class Reader(HTMLParser):
        def __init__(self):
            super().__init__()
            self.rows, self.row, self.cell = [], None, None

        def handle_starttag(self, tag, attrs):
            if tag == "tr":
                self.row = []
            elif tag in {"th", "td"}:
                self.cell = []

        def handle_data(self, data):
            if self.cell is not None:
                self.cell.append(data)

        def handle_endtag(self, tag):
            if tag in {"th", "td"}:
                self.row.append("".join(self.cell))
                self.cell = None
            elif tag == "tr":
                self.rows.append(self.row)
                self.row = None

    reader = Reader()
    reader.feed(markup)
    return [dict(zip(reader.rows[0], row)) for row in reader.rows[1:]]

def test_search_top10_reader_and_oov():
    app = start()
    assert not app.exception
    assert len(app.dataframe[0].value) == 10
    assert "score" in app.dataframe[0].value.columns
    before = app.dataframe[0].value.copy()
    for column in ("query_term_hits", "abstract_length_tokens"):
        assert column in before.columns
        assert (before[column] > 0).all()
    assert (before["query_term_hits"] <= before["abstract_length_tokens"]).all()
    ranking = app.session_state["search_result"]["ranking"][:10]
    assert before["pmid"].tolist() == [row["pmid"] for row in ranking]
    assert before["score"].tolist() == [row["score"] for row in ranking]
    assert all("query_term_hits" not in row for row in ranking)
    assert not any(item.label == "先做 L2 正規化" for item in app.checkbox)
    app.text_input[0].set_value("GLP-1 GLP-1 the").run()
    next(button for button in app.button if button.label == "搜尋").click().run()
    assert not app.exception
    repeated = app.dataframe[0].value
    assert repeated["pmid"].tolist() == before["pmid"].tolist()
    assert repeated["query_term_hits"].tolist() == before["query_term_hits"].tolist()
    assert repeated["abstract_length_tokens"].tolist() == before["abstract_length_tokens"].tolist()
    app.text_input[0].set_value("totallyunknownwordxyz")
    next(button for button in app.button if button.label == "搜尋").click().run()
    assert not app.exception
    assert any("沒有非零" in info.value for info in app.info)

def test_all_four_pages_and_reference_evaluation():
    app = start()
    for page in ("語料與設定", "方法比較", "效能評估"):
        app.sidebar.radio[0].set_value(page).run()
        assert not app.exception, str(app.exception)
        if page == "語料與設定":
            descriptions = next(frame.value for frame in app.dataframe if "意義" in frame.value.columns)
            assert descriptions.columns.tolist() == ["方法", "意義"]
            assert descriptions["方法"].tolist() == ["原始 TF", "Log TF", "僅 IDF", "TF × IDF", "Log TF × IDF", "BM25"]
            assert any("log10" in item.value for item in app.info)
    assert not app.metric
    next(button for button in app.button if button.label == "執行六種方法評估").click().run()
    assert not app.exception
    assert any("judgment_source" in frame.value.columns and len(frame.value) == 6 for frame in app.dataframe)
    charts = app.get("vega_lite_chart")
    assert len(charts) == 4
    fields = []
    for chart in charts:
        spec = json.loads(chart.proto.spec)
        encoding = spec.get("encoding", spec["layer"][0].get("encoding", {}))
        assert encoding["x"]["scale"]["domain"] == [0, 1]
        assert encoding["y"]["field"] == "method_label"
        assert "aggregate" not in encoding["x"]
        fields.append(encoding["x"]["field"])
    assert fields == ["precision_at_k", "recall_at_k", "reciprocal_rank", "ndcg_at_k"]
    assert any("未經人工驗證" in item.value and "Recall" in item.value for item in app.caption)

def widget(app, kind, label):
    return next(item for item in getattr(app, kind) if item.label == label)


def test_corpus_term_filter_updates_chart_and_clears_stale_results(monkeypatch):
    import pandas as pd
    import streamlit as st
    charts = []
    bar_chart = st.bar_chart

    def record_chart(data, *args, **kwargs):
        charts.append(data.copy())
        return bar_chart(data, *args, **kwargs)

    monkeypatch.setattr(st, "bar_chart", record_chart)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()
    app.sidebar.radio[0].set_value("語料與設定").run()
    assert not app.exception
    original = charts[-1].copy()
    for term in ("semaglutide", "GLP-1"):
        widget(app, "text_input", "搜尋詞項").set_value(term).run()
        assert not app.exception
        filtered = next(frame.value for frame in app.dataframe if "term" in frame.value.columns)
        assert filtered["term"].str.contains(term.casefold(), regex=False).all()
        pd.testing.assert_frame_equal(charts[-1], filtered.head(20))
    count = len(charts)
    widget(app, "text_input", "搜尋詞項").set_value("no_such_term_987654321").run()
    assert not app.exception
    assert len(charts) == count and not app.get("vega_lite_chart")
    assert any("表格與長條圖已清空" in item.value for item in app.info)
    widget(app, "text_input", "搜尋詞項").set_value("").run()
    assert not app.exception
    pd.testing.assert_frame_equal(charts[-1], original)


def test_search_discards_legacy_l2_state_and_uses_standard_cosine(monkeypatch):
    from ir_hw3.core import Engine
    calls = []
    rank = Engine.rank

    def spy(self, query, method="log_tfidf", **kwargs):
        calls.append((query, method, kwargs.get("scoring"), kwargs.get("normalize", False)))
        return rank(self, query, method, **kwargs)

    monkeypatch.setattr(Engine, "rank", spy)
    app = start()
    app.session_state["active_search"] = {"query": "insulin", "method": "log_tfidf", "normalize": True}
    app.session_state["search_normalize"] = True
    widget(app, "text_input", "英文查詢").set_value("insulin")
    calls.clear()
    app.run()
    assert not app.exception
    assert calls == [("insulin", "log_tfidf", None, False)]
    assert "search_normalize" not in app.session_state
    assert app.session_state["active_search"] == {"query": "insulin", "method": "log_tfidf"}
    assert not any(item.label == "先做 L2 正規化" for item in app.checkbox)
    expected = rank(app.session_state["search_result"]["engine"], "insulin", "log_tfidf")
    assert app.dataframe[0].value["pmid"].tolist() == [row["pmid"] for row in expected]
    assert app.dataframe[0].value["score"].tolist() == [row["score"] for row in expected]


def test_comparison_shows_raw_dot_and_cosine_from_the_same_query_and_weights(monkeypatch):
    from ir_hw3.core import Engine
    calls = []
    rank = Engine.rank

    def spy(self, query, method="log_tfidf", **kwargs):
        calls.append((self, query, method, kwargs))
        return rank(self, query, method, **kwargs)

    monkeypatch.setattr(Engine, "rank", spy)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()
    calls.clear()
    app.sidebar.radio[0].set_value("方法比較").run()
    assert not app.exception
    assert [call[3] for call in calls[-2:]] == [{"scoring": "dot"}, {"scoring": "cosine"}]
    assert calls[-2][1:3] == calls[-1][1:3]
    assert any(item.value == "raw dot 與 cosine 對照" for item in app.subheader)
    assert any(item.value == "L2 正規化前後比較" for item in app.subheader)
    normalized = next(frame.value for frame in app.dataframe if "cosine_before" in frame.value.columns)
    assert normalized["rank_before"].tolist() == normalized["rank_after"].tolist()
    assert normalized["cosine_before"].tolist() == pytest.approx(normalized["cosine_after"].tolist(), abs=1e-12)
    assert normalized["document_norm_after"].tolist() == pytest.approx([1] * len(normalized))
    assert normalized["query_norm_before"].tolist() == normalized["query_norm_after"].tolist()
    assert normalized["normalization_scope"].unique().tolist() == ["documents_only"]
    assert normalized["query_norm_after"].iloc[0] != pytest.approx(1)
    assert any("未做 L2，保持不變" in item.value for item in app.markdown)
    assert any("固定相同標註與 k" in item.value for item in app.success)
    assert all(not call[3].get("normalize", False) for call in calls)
    assert not any("same_ranking" in frame.value.columns for frame in app.dataframe)
    assert len(widget(app, "selectbox", "對照的詞項權重").options) == 5
    for frame, (engine, query, method, kwargs) in zip(app.dataframe[-2:], calls[-2:]):
        expected = rank(engine, query, method, **kwargs)
        assert frame.value["pmid"].tolist() == [row["pmid"] for row in expected]
        assert frame.value["score"].tolist() == [row["score"] for row in expected]
    overview = overview_table(app)
    assert next(item.proto for item in app.get("html") if "rank-overview-table" in item.proto.body).unsafe_allow_javascript
    assert len({row["PMID"] for row in overview}) == len(overview)
    assert {"文章標題", "詞命中數", "文章長度", "BM25"} <= set(overview[0])
    assert "Top 10 方法數" not in overview[0]
    _, weights, _ = engine.query(query, "tf")
    from ir_hw3.core import METHODS
    for row in overview:
        pid = row["PMID"]
        assert int(row["詞命中數"]) == sum(engine.counts[pid][term] for term in weights)
        assert int(row["文章長度"]) == engine.lengths[pid]
        assert row["文章標題"] == engine.documents[pid].title
    for frame, method in zip(app.dataframe[:6], METHODS):
        expected = rank(engine, query, method, limit=10)
        assert frame.value["pmid"].tolist() == [row["pmid"] for row in expected]
        assert frame.value["score"].tolist() == [row["score"] for row in expected]
        assert frame.value["query_term_hits"].tolist() == [
            sum(engine.counts[row["pmid"]][term] for term in weights) for row in expected]
        assert frame.value["abstract_length_tokens"].tolist() == [engine.lengths[row["pmid"]] for row in expected]
        config = json.loads(frame.proto.columns)
        assert config["score"]["label"] == ("BM25 分數" if method == "bm25" else "cosine 分數")
    assert any("兩者共有（" in tab.label for tab in app.tabs)
    assert any("新進 Top 10（" in tab.label for tab in app.tabs)
    assert any("移出 Top 10（" in tab.label for tab in app.tabs)
    changes = [frame.value for frame in app.dataframe if "baseline_rank" in frame.value.columns or "compared_rank" in frame.value.columns]
    assert changes and all(not frame.isna().any().any() for frame in changes)
    widget(app, "selectbox", "比較方法").set_value("tf").run()
    assert not app.exception
    assert any("目前選擇相同方法" in item.value for item in app.info)
    widget(app, "text_input", "比較查詢文字").set_value("zzzxxyyunknownqueryzzz").run()
    assert not app.exception and len(app.dataframe) == 0
    assert any("沒有非零分數" in item.value for item in app.info)


def test_bm25_search_reader_comparison_and_evaluation():
    app = start()
    methods = widget(app, "selectbox", "權重方法")
    assert methods.options[-1] == "BM25" and len(methods.options) == 6
    methods.set_value("bm25")
    widget(app, "button", "搜尋").click().run()
    assert not app.exception
    assert any(m.label == "最高 BM25" for m in app.metric)
    assert any("bm25_contribution" in f.value.columns for f in app.dataframe)
    assert not any("cosine_contribution" in f.value.columns for f in app.dataframe)
    scores = app.dataframe[0].value["score"].tolist()
    app.run()
    assert not any(item.label == "IDF 定義" for item in app.selectbox)
    assert app.dataframe[0].value["score"].tolist() == scores
    app.sidebar.radio[0].set_value("方法比較").run()
    assert not app.exception
    assert "BM25" in overview_table(app)[0]
    assert len(widget(app, "selectbox", "對照的詞項權重").options) == 5
    widget(app, "selectbox", "比較方法").set_value("bm25").run()
    assert not app.exception
    app.sidebar.radio[0].set_value("效能評估").run()
    widget(app, "button", "執行六種方法評估").click().run()
    assert not app.exception
    summary = next(f.value for f in app.dataframe if "precision_at_k" in f.value.columns)
    assert summary["method"].tolist()[-1] == "bm25" and len(summary) == 6


def test_retrieval_settings_are_fixed_across_search_comparison_and_evaluation(monkeypatch):
    from ir_hw3.core import Engine
    settings_seen = []
    rank = Engine.rank

    def record_settings(self, *args, **kwargs):
        settings_seen.append((self.settings.condition, self.settings.idf))
        return rank(self, *args, **kwargs)

    monkeypatch.setattr(Engine, "rank", record_settings)
    app = start()
    for page in ("搜尋與排名", "方法比較", "效能評估"):
        app.sidebar.radio[0].set_value(page).run()
        assert not app.exception
        assert not {"前處理", "IDF 定義"} & {item.label for item in app.selectbox}
    widget(app, "button", "執行六種方法評估").click().run()
    assert not app.exception
    assert settings_seen and set(settings_seen) == {("C", "standard")}


def test_pubmed_reference_ui_discloses_sources_and_keeps_manual_empty(isolated_manual_file):
    app = start()
    app.sidebar.radio[0].set_value("效能評估").run()
    assert not app.exception
    coverage = next(f.value for f in app.dataframe if "metadata_positive" in f.value.columns)
    assert len(coverage) == 10 and (coverage["documents"] == 3000).all()
    assert (coverage["metadata_positive"] + coverage["weak_fallback"] == 3000).all()
    widget(app, "button", "執行六種方法評估").click().run()
    assert not app.exception
    summary = next(f.value for f in app.dataframe if "precision_at_k" in f.value.columns)
    assert (summary["judgment_source"] == "pubmed_hybrid").all()
    assert (summary["queries_evaluated"] == 10).all()
    assert not app.metric
    assert not isolated_manual_file.exists()

def annotation_app():
    """Exercise retained annotation components without exposing them on the website."""
    import ast
    import textwrap
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    page = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "evaluation_page")
    harness = textwrap.dedent('''
        with st.tabs(["人工標註"])[0]:
            manual = load_judgments(manifest["sha256"], queries, engine.documents)
            progress = query_status(queries, manual)
            if "annotation_saved" in st.session_state:
                st.success(st.session_state.pop("annotation_saved"))
            table([{**row, "status": STATUS_LABELS[row["status"]],
                    "exclusion_reason": EXCLUSION_LABELS[row["exclusion_reason"]]} for row in progress])
            annotation_panel(engine, queries, manifest, signature)
    ''')
    page.body = ast.parse(harness).body
    ast.fix_missing_locations(tree)
    app = AppTest.from_string(ast.unparse(tree), default_timeout=120).run()
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
    manual_tab = next(tab for tab in app.tabs if tab.label == "人工標註")
    statuses = next(frame.value for frame in manual_tab.dataframe if "status" in frame.value.columns)
    assert statuses.iloc[0]["status"] == "已判讀，但尚未找到相關文件"
    assert not statuses.iloc[0]["included_in_mean"]
    assert not app.exception

def test_zero_evaluation_denominator_is_not_zero_score(monkeypatch):
    import streamlit as st
    from ir_hw3 import pubmed_reference
    original = pubmed_reference.build_reference

    def no_reference_positives(*args, **kwargs):
        labels = original(*args, **kwargs)
        for records in labels["judgments"].values():
            for record in records.values():
                record["grade"] = 0
        return labels

    monkeypatch.setattr(pubmed_reference, "build_reference", no_reference_positives)
    st.cache_data.clear()
    try:
        app = start()
        app.sidebar.radio[0].set_value("效能評估").run()
        widget(app, "button", "執行六種方法評估").click().run()
        summary = next(frame.value for frame in app.dataframe if "queries_evaluated" in frame.value.columns)
        assert (summary["queries_total"] == 10).all()
        assert (summary["queries_evaluated"] == 0).all()
        assert summary["precision_at_k"].isna().all()
        assert not app.exception and not app.get("vega_lite_chart")
        widget(app, "selectbox", "圖表顯示").set_value("Q01").run()
        assert not app.exception and not app.get("vega_lite_chart")
        assert any("Q01 沒有參考相關文件" in item.value for item in app.info)
    finally:
        st.cache_data.clear()


def test_evaluation_has_one_fixed_source_and_preserves_metrics_and_query_averaging(isolated_manual_file, monkeypatch):
    from ir_hw3 import experiments
    import pandas as pd
    import streamlit as st
    calls, charts = [], []
    evaluate, altair_chart = evaluation.evaluate, st.altair_chart

    def record_evaluation(*args, **kwargs):
        calls.append(True)
        return evaluate(*args, **kwargs)

    def record_chart(chart, *args, **kwargs):
        charts.append(chart.to_dict())
        return altair_chart(chart, *args, **kwargs)

    def unused_path(*args, **kwargs):
        raise AssertionError("The website must not load manual judgments or experiment history")

    monkeypatch.setattr(evaluation, "load_judgments", unused_path)
    monkeypatch.setattr(experiments, "list_runs", unused_path)
    monkeypatch.setattr(evaluation, "evaluate", record_evaluation)
    monkeypatch.setattr(st, "altair_chart", record_chart)
    app = start()
    app.sidebar.radio[0].set_value("效能評估").run()
    assert not app.exception and not app.tabs and not app.metric
    assert not {"評估標註來源", "歷史標註來源", "標註查詢"} & {item.label for item in app.selectbox}
    assert not any("人工標註" in item.label or "實驗紀錄" in item.label for item in app.button)
    assert all(not expander.proto.expanded for expander in app.expander)
    assert any("弱規則是什麼" in expander.label for expander in app.expander)
    assert any("不使用搜尋框當下" in item.value for item in app.markdown)
    assert not app.get("vega_lite_chart")
    widget(app, "button", "執行六種方法評估").click().run()
    assert not app.exception and len(app.get("vega_lite_chart")) == 4
    summary = next(frame for frame in app.dataframe if "queries_evaluated" in frame.value.columns)
    average_table = summary.value.copy()
    assert widget(app, "selectbox", "圖表顯示").value == "average"
    assert len(widget(app, "selectbox", "圖表顯示").options) == 11
    assert list(summary.proto.column_order) == ["method_label", "precision_at_k", "recall_at_k", "reciprocal_rank", "ndcg_at_k"]
    raw = app.session_state["evaluation_result"]["summary"]
    detail = app.session_state["evaluation_result"]["detail"]
    assert {row["qid"] for row in detail} == {q["qid"] for q in evaluation.load_queries()}
    assert all(row["judgment_source"] == "pubmed_hybrid" and row["queries_evaluated"] == 10 for row in raw)
    for field in ("precision_at_k", "recall_at_k", "reciprocal_rank", "ndcg_at_k"):
        assert summary.value[field].tolist() == [row[field] for row in raw]
        for row in raw:
            values = [item[field] for item in detail if item["method"] == row["method"]]
            assert row[field] == pytest.approx(sum(values) / 10)
    fields = ("precision_at_k", "recall_at_k", "reciprocal_rank", "ndcg_at_k")
    for query in evaluation.load_queries():
        charts.clear()
        widget(app, "selectbox", "圖表顯示").set_value(query["qid"]).run()
        assert not app.exception and len(charts) == 4
        expected = {row["method"]: row for row in detail if row["qid"] == query["qid"]}
        frame = next(frame for frame in app.dataframe if "reciprocal_rank" in frame.value.columns)
        assert set(frame.value["qid"]) == {query["qid"]} and len(frame.value) == 6
        assert json.loads(frame.proto.columns)["reciprocal_rank"]["label"] == "RR"
        for spec, field in zip(charts, fields):
            encoding = spec["layer"][0]["encoding"]
            assert encoding["x"]["field"] == field and encoding["x"]["scale"]["domain"] == [0, 1]
            assert "aggregate" not in encoding["x"]
            rows = spec["datasets"][spec["data"]["name"]]
            assert len(rows) == 6 and {row["qid"] for row in rows} == {query["qid"]}
            assert {row["method"] for row in rows} == set(expected)
            assert all(row[field] == expected[row["method"]][field] for row in rows)
        assert calls == [True]  # Changing the view must not rerun evaluation.
    widget(app, "selectbox", "圖表顯示").set_value("average").run()
    restored = next(frame.value for frame in app.dataframe if "queries_evaluated" in frame.value.columns)
    pd.testing.assert_frame_equal(restored, average_table)
    assert any(item.value == "**MRR**" for item in app.markdown)
    assert calls == [True]
    widget(app, "selectbox", "圖表顯示").set_value("Q10").run()
    widget(app, "selectbox", "評估 k").set_value(5).run()
    assert not app.exception and not app.get("vega_lite_chart")
    assert any("設定或參考標籤已變更" in item.value for item in app.info)
    widget(app, "button", "執行六種方法評估").click().run()
    assert not app.exception and len(app.get("vega_lite_chart")) == 4
    assert widget(app, "selectbox", "圖表顯示").value == "Q10"
    assert calls == [True, True]
    assert not isolated_manual_file.exists()


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
