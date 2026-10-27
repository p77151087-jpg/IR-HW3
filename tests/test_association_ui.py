"""UI reads saved models only; no full training in the test suite."""
import json

import pytest
from streamlit.dataframe_util import convert_arrow_bytes_to_pandas_df
from streamlit.testing.v1 import AppTest

from ir_hw3.corpus import ROOT
from ir_hw3.association_ui import PAGE


def widget(app, kind, label):
    return next(item for item in getattr(app, kind) if item.label == label)


def start():
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=45).run()


def neighbor_tables(app):
    return [frame.value for frame in app.dataframe if "關係" in frame.value.columns]


def charts_of_type(app, mark):
    return [chart for chart in app.get("vega_lite_chart") if json.loads(chart.proto.spec)["mark"]["type"] == mark]


def chart_data(chart):
    return convert_arrow_bytes_to_pandas_df(chart.proto.datasets[0].data.data)


def capture_loaded_runs(monkeypatch):
    from ir_hw3 import association_ui
    loaded = []
    original = association_ui.get_run

    def record(*args, **kwargs):
        run = original(*args, **kwargs)
        loaded.append(run)
        return run

    monkeypatch.setattr(association_ui, "get_run", record)
    return loaded


def test_model_switch_k_oov_and_charts_do_not_train_or_rank(monkeypatch):
    from gensim.models import Word2Vec
    from ir_hw3.core import Engine
    from ir_hw3.word_association import neighbors
    loaded = capture_loaded_runs(monkeypatch)
    def forbidden(*args, **kwargs):
        raise AssertionError("The comparison UI must never train or rank documents")
    app = start()
    original_search = dict(app.session_state["active_search"])
    monkeypatch.setattr(Word2Vec, "train", forbidden)
    monkeypatch.setattr(Engine, "rank", forbidden)
    app.sidebar.radio[0].set_value(PAGE).run()
    assert not app.exception, str(app.exception)
    assert [tab.label for tab in app.tabs] == ["找相關詞", "比較兩個詞", "整體分析"]
    assert not app.tabs[0].metric
    assert all(not expander.proto.expanded for expander in app.expander)
    details = next(expander for expander in app.expander if expander.label == "資料與模型明細")
    assert len(details.metric) == 4
    assert any("沒有共同詞" in item.value or "共同找到" in item.value for item in app.info)
    initial_run = loaded[-1]
    assert initial_run.manifest["tokenizer"]["condition"] == "C"
    assert initial_run.manifest["tokenizer"]["keep_stopwords"] is False
    assert [m.value for m in app.metric] == [
        f"{initial_run.manifest[key]:,}" for key in ("documents", "sentences", "tokens", "candidate_pool_size")]
    assert any("詞彙關聯同樣採 C" in row.value for row in app.sidebar.caption)
    widget(app, "selectbox", "Embedding 模型").set_value("skipgram_w5").run()
    widget(app, "selectbox", "顯示相關詞數").set_value(5).run()
    assert not app.exception
    assert [len(frame) for frame in neighbor_tables(app)] == [5, 5]
    run = loaded[-1]
    for actual, space in zip(neighbor_tables(app), (run.tfidf, run.models["skipgram_w5"])):
        expected = neighbors(space, "semaglutide", run.pool, 5)["rows"]
        assert actual[["rank", "term", "cosine"]].to_dict("records") == expected
    assert len(app.get("vega_lite_chart")) == 5
    for chart in charts_of_type(app, "rect"):
        spec = json.loads(chart.proto.spec)
        assert spec["encoding"]["color"]["scale"]["domain"] == [-1, 1]
        assert spec["encoding"]["x"]["sort"] == spec["encoding"]["y"]["sort"]
    scatter_spec = json.loads(charts_of_type(app, "circle")[0].proto.spec)
    assert scatter_spec["encoding"]["y"]["scale"]["domain"] == [-1, 1]
    assert "tooltip" in scatter_spec["encoding"] and "shape" in scatter_spec["encoding"]
    # Original fixed charts stay visible in the overall tab, outside expanders.
    assert len(app.tabs[2].get("vega_lite_chart")) == 3
    assert all(not expander.get("vega_lite_chart") for expander in app.expander)
    # Both pages use C; the word comparison still uses independent saved models.
    before = neighbor_tables(app)[0].copy()
    app.run()
    assert not {"前處理", "IDF 定義"} & {item.label for item in app.selectbox}
    assert neighbor_tables(app)[0].equals(before)
    widget(app, "text_input", "分析單詞").set_value("notinthecorpusxyz")
    widget(app, "button", "比較近鄰").click().run()
    assert not app.exception
    assert [len(frame) for frame in neighbor_tables(app)] == [0, 0]
    assert not charts_of_type(app, "bar")
    assert len(app.get("vega_lite_chart")) == 3
    assert any("無有效向量" in row.value for row in app.warning)
    assert dict(app.session_state["active_search"]) == original_search


def test_c_ui_uses_rebuilt_spaces_and_rejects_stopword_query(monkeypatch):
    from ir_hw3.core import stopwords
    loaded = capture_loaded_runs(monkeypatch)
    app = start()
    app.sidebar.radio[0].set_value(PAGE).run()
    blocked = stopwords()
    run = loaded[-1]
    for space in [run.tfidf, *run.models.values()]:
        assert not blocked.intersection(space.words)
    assert not blocked.intersection(run.pool)
    for table, chart in zip(neighbor_tables(app), charts_of_type(app, "bar")):
        assert not blocked.intersection(table["term"])
        assert table.equals(chart_data(chart))
    assert any("統一採 C 前處理" in row.value for row in app.caption)
    assert not any("B 前處理" in row.value or "保留常見英文詞" in row.value for row in app.caption)
    widget(app, "text_input", "分析單詞").set_value("the")
    widget(app, "button", "比較近鄰").click().run()
    assert any("已移除的停用詞" in row.value for row in app.warning)
    assert not charts_of_type(app, "bar")
    assert not neighbor_tables(app)
    assert not app.exception


def test_pair_form_and_fixed_45_rows_and_downloads(monkeypatch):
    from ir_hw3.word_association import pair_score
    loaded = capture_loaded_runs(monkeypatch)
    app = start()
    app.sidebar.radio[0].set_value(PAGE).run()
    widget(app, "text_input", "詞 A").set_value("GLP‑1")
    widget(app, "text_input", "詞 B").set_value("receptor")
    widget(app, "button", "比較詞對").click().run()
    assert not app.exception
    assert any("glp-1 ／ receptor" in row.value for row in app.caption)
    pair_table = next(frame.value for frame in app.dataframe if "cosine_display" in frame.value.columns)
    run = loaded[-1]
    expected = [pair_score(space, "glp-1", "receptor") for space in [run.tfidf, *run.models.values()]]
    assert pair_table["cosine"].tolist() == expected
    assert pair_table["cosine_display"].tolist() == [f"{score:.6f}" for score in expected]
    pairs = next(frame.value for frame in app.dataframe if "pair_id" in frame.value.columns)
    assert len(pairs) == 45
    assert set(pairs.columns) >= {"tfidf", "cbow_w2", "cbow_w5", "skipgram_w2", "skipgram_w5"}
    assert len(app.get("download_button")) >= 6
    widget(app, "text_input", "分析單詞").set_value("glp-1 receptor")
    widget(app, "button", "比較近鄰").click().run()
    assert any("請輸入一個詞" in row.value for row in app.warning)
    widget(app, "text_input", "詞 A").set_value("unknownwordxyz")
    widget(app, "button", "比較詞對").click().run()
    unavailable = next(frame.value for frame in app.dataframe if "cosine_display" in frame.value.columns)
    assert unavailable["cosine_display"].tolist() == ["無法計算"] * 5
    assert unavailable["cosine"].isna().all()
    assert not app.exception


def test_pair_xy_maps_follow_submitted_pair_and_model_without_changing_saved_charts(monkeypatch):
    from ir_hw3 import association_ui
    captured = []
    original = association_ui.get_word_maps
    def record(*args):
        value = original(*args)
        captured.append((args[2:], value))
        return value
    monkeypatch.setattr(association_ui, "get_word_maps", record)
    app = start()
    app.sidebar.radio[0].set_value(PAGE).run()
    assert not app.exception
    assert captured[-1][0] == ("cbow_w2", "insulin", "glucose")
    first = captured[-1][1]
    assert first["terms"] == association_ui.FIXED_TERMS
    assert len([el for el in app.get("iframe") if "viewBox=\"0 0 520 520\"" in el.proto.srcdoc]) == 2
    saved_fixed = [chart_data(chart) for mark in ("rect", "circle") for chart in charts_of_type(app, mark)]
    widget(app, "selectbox", "預選詞 A（中文提示）").set_value("semaglutide").run()
    assert captured[-1][0] == ("cbow_w2", "insulin", "glucose")
    widget(app, "text_input", "詞 B").set_value("liraglutide")
    widget(app, "button", "比較詞對").click().run()
    assert captured[-1][0] == ("cbow_w2", "semaglutide", "liraglutide")
    assert any("不是各自的前十名" in row.value for row in app.caption)
    tfidf_rows = captured[-1][1]["spaces"]["tfidf"]["rows"]
    embedding_rows = captured[-1][1]["spaces"]["embedding"]["rows"]
    widget(app, "selectbox", "Embedding 模型").set_value("skipgram_w5").run()
    assert captured[-1][1]["spaces"]["tfidf"]["rows"] == tfidf_rows
    assert captured[-1][1]["spaces"]["embedding"]["rows"] != embedding_rows
    assert len(app.tabs[2].get("vega_lite_chart")) == 3
    # Fixed heatmaps can follow the selected model as before; the 180-point scatter stays exact.
    assert chart_data(charts_of_type(app, "circle")[0]).equals(saved_fixed[-1])
    widget(app, "text_input", "詞 A").set_value("unknownwordxyz")
    widget(app, "button", "比較詞對").click().run()
    assert captured[-1][1]["status"] == "unavailable"
    assert not [el for el in app.get("iframe") if "viewBox=\"0 0 520 520\"" in el.proto.srcdoc]
    assert not app.exception


def test_returning_to_page_restores_submitted_word_and_pair_fields():
    app = start()
    app.sidebar.radio[0].set_value(PAGE).run()
    widget(app, "text_input", "分析單詞").set_value("insulin")
    widget(app, "button", "比較近鄰").click().run()
    widget(app, "text_input", "詞 A").set_value("glp-1")
    widget(app, "text_input", "詞 B").set_value("receptor")
    widget(app, "button", "比較詞對").click().run()
    app.sidebar.radio[0].set_value("搜尋與排名").run()
    app.sidebar.radio[0].set_value(PAGE).run()
    assert not app.exception
    assert widget(app, "text_input", "分析單詞").value == "insulin"
    assert widget(app, "text_input", "詞 A").value == "glp-1"
    assert widget(app, "text_input", "詞 B").value == "receptor"
    assert any("實際分析詞：insulin" in row.value for row in app.caption)


def test_pair_pca_tsne_switch_keeps_scores_words_and_saved_charts(monkeypatch):
    from ir_hw3 import association_ui
    captured = []
    original = association_ui.get_word_maps
    def record(*args):
        value = original(*args)
        captured.append(value)
        return value
    monkeypatch.setattr(association_ui, "get_word_maps", record)
    app = start()
    app.sidebar.radio[0].set_value(PAGE).run()
    pca = captured[-1]
    pair_table = next(frame.value.copy() for frame in app.dataframe if "cosine_display" in frame.value.columns)
    saved_scatter = chart_data(charts_of_type(app, "circle")[0]).copy()
    widget(app, "radio", "XY 降維方式").set_value("tsne").run()
    assert not app.exception
    tsne = captured[-1]
    assert tsne["projection"] == "tsne" and tsne["terms"] == pca["terms"]
    assert widget(app, "selectbox", "鄰近範圍（perplexity）").value == 5
    assert all(data["diagnostics"]["parameters"]["perplexity"] == 5 for data in tsne["spaces"].values())
    assert all(data["retained_variance"] is None for data in tsne["spaces"].values())
    assert not any("二維保留差異量" in row.value for row in app.tabs[1].caption)
    assert any("群與群的距離" in row.value for row in app.tabs[1].caption)
    html = [el.proto.srcdoc for el in app.get("iframe") if 'viewBox="0 0 520 520"' in el.proto.srcdoc]
    assert len(html) == 2 and all("t-SNE 維度 1" in text and "主成分" not in text for text in html)
    widget(app, "selectbox", "鄰近範圍（perplexity）").set_value(3).run()
    updated = captured[-1]
    assert updated["spaces"]["tfidf"]["diagnostics"]["parameters"]["perplexity"] == 3
    assert updated["spaces"]["tfidf"]["rows"] != tsne["spaces"]["tfidf"]["rows"]
    assert next(frame.value for frame in app.dataframe if "cosine_display" in frame.value.columns).equals(pair_table)
    assert chart_data(charts_of_type(app, "circle")[0]).equals(saved_scatter)
    widget(app, "radio", "XY 降維方式").set_value("pca").run()
    assert captured[-1] == pca
    assert len(app.tabs[2].get("vega_lite_chart")) == 3
    assert not app.exception


def test_submitted_word_updates_chart_data_and_same_request_explains_no_change(monkeypatch):
    from ir_hw3.word_association import neighbors
    loaded = capture_loaded_runs(monkeypatch)
    app = start()
    app.sidebar.radio[0].set_value(PAGE).run()
    original_bars = [chart_data(chart) for chart in charts_of_type(app, "bar")]
    original_fixed = [chart_data(chart) for mark in ("rect", "circle") for chart in charts_of_type(app, mark)]
    widget(app, "text_input", "分析單詞").set_value("insulin")
    widget(app, "button", "比較近鄰").click().run()
    assert not app.exception
    assert any("已更新為 insulin" in row.value for row in app.success)
    run = loaded[-1]
    bars = charts_of_type(app, "bar")
    for chart, space, old in zip(bars, (run.tfidf, run.models["cbow_w2"]), original_bars):
        actual = chart_data(chart)
        assert actual[["rank", "term", "cosine"]].to_dict("records") == neighbors(space, "insulin", run.pool, 10)["rows"]
        assert not actual.equals(old)
        spec = json.loads(chart.proto.spec)
        assert "insulin" in spec["title"]
        assert spec["encoding"]["x"]["scale"]["domain"] == [0, 1]
    for actual, old in zip([chart_data(chart) for mark in ("rect", "circle") for chart in charts_of_type(app, mark)], original_fixed):
        assert actual.equals(old)
    tables = neighbor_tables(app)
    common = set(tables[0]["term"]) & set(tables[1]["term"])
    for table in tables:
        assert table["關係"].tolist() == ["兩邊前 10 名都有" if term in common else "只在這邊前 10 名" for term in table["term"]]
    widget(app, "button", "比較近鄰").click().run()
    assert any("分析詞、模型與詞數相同" in row.value for row in app.info)
    assert not app.success
    assert not app.exception


def test_chinese_presets_fill_fields_without_committing_or_overwriting_custom_input():
    app = start()
    app.sidebar.radio[0].set_value(PAGE).run()
    assert "insulin（胰島素）" in widget(app, "selectbox", "預選分析詞（中文提示）").options
    widget(app, "selectbox", "預選分析詞（中文提示）").set_value("insulin").run()
    assert widget(app, "text_input", "分析單詞").value == "insulin"
    assert (app.session_state["assoc_submitted_word"] if "assoc_submitted_word" in app.session_state else "semaglutide") == "semaglutide"
    assert all("semaglutide" in json.loads(chart.proto.spec)["title"] for chart in charts_of_type(app, "bar"))
    widget(app, "button", "比較近鄰").click().run()
    assert all("insulin" in json.loads(chart.proto.spec)["title"] for chart in charts_of_type(app, "bar"))
    widget(app, "selectbox", "預選詞 A（中文提示）").set_value("obesity").run()
    widget(app, "selectbox", "預選詞 B（中文提示）").set_value("diabetes").run()
    assert widget(app, "text_input", "詞 A").value == "obesity"
    assert widget(app, "text_input", "詞 B").value == "diabetes"
    assert any("實際詞對：insulin ／ glucose" in row.value for row in app.caption)
    widget(app, "button", "比較詞對").click().run()
    assert any("實際詞對：obesity ／ diabetes" in row.value for row in app.caption)
    # An unrelated rerun must not reapply the old preset over a submitted edit.
    widget(app, "text_input", "詞 A").set_value("receptor")
    widget(app, "button", "比較詞對").click().run()
    widget(app, "selectbox", "顯示相關詞數").set_value(5).run()
    assert widget(app, "text_input", "詞 A").value == "receptor"
    assert any("實際詞對：receptor ／ diabetes" in row.value for row in app.caption)
    assert not app.exception


def test_reading_guides_explain_saved_overlap_and_switch_actual_scatter_pairs():
    from ir_hw3.word_association import MODEL_NAMES
    saved = json.loads((ROOT / "reports/word_association/runs/20261024-c-four-models/results.json").read_text(encoding="utf-8"))
    app = start()
    app.sidebar.radio[0].set_value(PAGE).run()
    assert not app.exception
    details = next(frame.value for frame in app.dataframe if {"分析詞", "共同詞數", "重疊率", "共同詞"} <= set(frame.value.columns))
    assert details["共同詞數"].tolist() == [1, 2, 0, 2, 2, 3, 0, 3, 3, 5]
    assert details["共同詞數"].sum() == 21
    for row in details.to_dict("records"):
        first = {r["term"] for r in saved["neighbors"] if r["method"] == "tfidf" and r["query"] == row["分析詞"] and r["k"] == 10}
        second = {r["term"] for r in saved["neighbors"] if r["method"] == "skipgram_w5" and r["query"] == row["分析詞"] and r["k"] == 10}
        assert row["共同詞數"] == len(first & second)
        expected = next(r["overlap"] for r in saved["overlap"] if r["model"] == "skipgram_w5" and r["term"] == row["分析詞"] and r["k"] == 10)
        assert row["重疊率"] == f"{expected:.0%}"
    assert details.iloc[0]["共同詞"] == "subcutaneous"
    assert any("1 ÷ 10 ＝ 10%" in row.value for row in app.markdown)
    assert any("21 ÷（10 × 10）＝21%" in row.value for row in app.markdown)
    assert any("共 180 個點" in row.value for row in app.caption)
    before_scatter = chart_data(charts_of_type(app, "circle")[0]).copy()
    for pair_id in (1, 34):
        widget(app, "selectbox", "散點圖實例詞對").set_value(pair_id).run()
        pair = next(row for row in saved["pairs"] if row["pair_id"] == pair_id)
        table = next(frame.value for frame in app.dataframe if {"模型", "tfidf", "embedding"} == set(frame.value.columns))
        assert table["tfidf"].tolist() == [pair["tfidf"]] * 4
        assert table["embedding"].tolist() == [pair[model] for model in MODEL_NAMES]
        assert any(f"詞對編號 {pair_id}：{pair['left']} ／ {pair['right']}" in row.value for row in app.caption)
        assert any(f"X 都是 {pair['tfidf']:.6f}" in row.value for row in app.markdown)
        assert chart_data(charts_of_type(app, "circle")[0]).equals(before_scatter)
        assert not app.exception


def test_chinese_tooltips_and_top10_overview_use_saved_c_results():
    from ir_hw3.word_association import MODEL_NAMES
    app = start()
    app.sidebar.radio[0].set_value(PAGE).run()
    assert not app.exception
    saved = json.loads((ROOT / "reports/word_association/runs/20261024-c-four-models/results.json").read_text(encoding="utf-8"))
    expected = [row for row in saved["summary"] if row["k"] == 10]
    overview = next(frame.value for frame in app.dataframe if "sample_display" in frame.value.columns)
    assert overview["model"].tolist() == [row["model"] for row in expected]
    assert overview["mean_overlap"].tolist() == [row["mean_overlap"] for row in expected]
    assert overview["overlap_display"].tolist() == ["6%", "5%", "8%", "21%"]
    assert overview["sample_display"].tolist() == ["10／10"] * 4
    assert any("部分重疊" in row.value and "Skip-Gram，視窗 5（21%）" in row.value and "2.1 個" in row.value for row in app.info)
    assert any("不是正確率" in row.value for row in app.caption)
    # This overview always describes saved Top-10 across ten anchors, even if
    # the interactive neighbor count is changed to five.
    widget(app, "selectbox", "顯示相關詞數").set_value(5).run()
    updated = next(frame.value for frame in app.dataframe if "sample_display" in frame.value.columns)
    assert updated.equals(overview)
    for chart in charts_of_type(app, "rect"):
        tips = json.loads(chart.proto.spec)["encoding"]["tooltip"]
        assert [(row["field"], row["title"]) for row in tips] == [
            ("left", "詞 A"), ("right", "詞 B"), ("cosine", "cosine 相似度")]
    scatter = charts_of_type(app, "circle")[0]
    spec = json.loads(scatter.proto.spec)
    assert [(row["field"], row["title"]) for row in spec["encoding"]["tooltip"]] == [
        ("model_label", "模型"), ("pair", "詞對"), ("pair_id", "詞對編號"),
        ("tfidf", "TF-IDF 相似度"), ("embedding", "Embedding 相似度"),
        ("cooccurring_documents", "共同出現摘要篇數")]
    actual = chart_data(scatter)
    columns = ["model", "pair_id", "tfidf", "embedding", "cooccurring_documents"]
    expected_points = [{"model": model, "pair_id": row["pair_id"], "tfidf": row["tfidf"],
                        "embedding": row[model], "cooccurring_documents": row["cooccurring_documents"]}
                       for row in saved["pairs"] for model in MODEL_NAMES]
    assert actual[columns].to_dict("records") == expected_points
    assert len(actual) == 180
    assert all("視窗" in label for label in actual["model_label"])
    assert len(app.tabs[2].get("vega_lite_chart")) == 3
    assert not app.exception
