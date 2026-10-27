"""Exercise the real cloud entry point in an isolated process; never train."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from streamlit.testing.v1 import AppTest


def widget(app, kind, label):
    return next(item for item in getattr(app, kind) if item.label == label)


def healthy(app):
    assert not app.exception, str(app.exception)
    assert not app.error, [x.value for x in app.error]


def main():
    from ir_hw3.corpus import sha256
    from ir_hw3.cloud_results import ASSOCIATION_RUN, EVALUATION_RUN
    protected = [p for directory in ["data", ASSOCIATION_RUN, EVALUATION_RUN]
                 for p in (ROOT / directory).rglob("*") if p.is_file()]
    before = {str(p): sha256(p) for p in protected}
    app = AppTest.from_file(str(ROOT / "cloud_app.py"), default_timeout=120).run()
    healthy(app)
    from ir_hw3 import demo_policy, evaluation, experiments, acquisition, embedding_training, word_association
    assert demo_policy.is_demo()
    from ir_hw3.core import METHODS
    for method in METHODS:
        widget(app, "selectbox", "權重方法").set_value(method)
        widget(app, "text_input", "英文查詢").set_value("GLP-1 receptor")
        widget(app, "button", "搜尋").click().run()
        healthy(app)
        results = app.session_state["active_search"]
        assert results["method"] == method
        assert any("score" in frame.value.columns and len(frame.value) == 10 for frame in app.dataframe)
    widget(app, "text_input", "英文查詢").set_value("insulinn").run()
    healthy(app)
    widget(app, "button", "insulin").click().run()
    healthy(app)
    assert app.session_state["active_search"]["query"] == "insulin"
    assert any("passage" in x.value and "<mark>" in x.value for x in app.markdown)
    for page in ["語料與設定", "方法比較", "效能評估"]:
        app.sidebar.radio[0].set_value(page).run()
        healthy(app)
    assert "匯出這組設定的完整實驗與 RQ 解讀" not in [x.label for x in app.button]
    assert any(x.label == "下載 RQ_DISCUSSION.md" for x in app.get("download_button"))
    widget(app, "button", "執行六種方法評估").click().run()
    healthy(app)
    assert len(app.session_state["evaluation_result"]["summary"]) == 6
    app.sidebar.radio[0].set_value("Embedding／TF-IDF 詞彙關聯").run()
    healthy(app)
    for model in ["cbow_w2", "cbow_w5", "skipgram_w2", "skipgram_w5"]:
        widget(app, "selectbox", "Embedding 模型").set_value(model).run()
        healthy(app)
        assert len(app.get("vega_lite_chart")) == 5
        assert len([frame for frame in app.dataframe if "關係" in frame.value.columns]) == 2
    widget(app, "button", "比較詞對").click().run()
    healthy(app)
    pair_scores = next(frame.value.copy() for frame in app.dataframe if "cosine_display" in frame.value.columns)
    def projection_html():
        return [item.proto.srcdoc for item in app.get("iframe") if 'viewBox="0 0 520 520"' in item.proto.srcdoc]
    assert len(projection_html()) == 2 and all("主成分 1" in html for html in projection_html())
    assert any("PCA、t-SNE 與 X／Y 怎麼看？" in item.value for item in app.tabs[1].markdown)
    widget(app, "radio", "XY 降維方式").set_value("tsne").run()
    healthy(app)
    assert len(projection_html()) == 2 and all("t-SNE 維度 1" in html for html in projection_html())
    widget(app, "selectbox", "鄰近範圍（perplexity）").set_value(3).run()
    healthy(app)
    assert next(frame.value for frame in app.dataframe if "cosine_display" in frame.value.columns).equals(pair_scores)
    widget(app, "radio", "XY 降維方式").set_value("pca").run()
    healthy(app)
    assert len(app.get("download_button")) >= 6
    # Exercise backend functions directly, without their UI and with invalid args:
    # policy must reject them before validating inputs or touching the filesystem.
    blocked = [evaluation.atomic_json, evaluation.save_judgments, evaluation.parse_judgment_csv,
               experiments.run_experiment, acquisition.cached_request, acquisition.expand_snapshot,
               embedding_training.train_model, embedding_training.train_run, word_association.write_json,
               word_association.write_csv, word_association.TfidfWords.save]
    from gensim.models import Word2Vec
    blocked.append(Word2Vec.train)
    for function in blocked:
        try:
            function()
        except demo_policy.DemoReadOnlyError:
            pass
        else:
            raise AssertionError("Mutation backend was not blocked")
    sentinel = ROOT / "tmp/cloud-must-never-write.txt"
    assert not sentinel.exists()
    try:
        sentinel.write_text("forbidden", encoding="utf-8")
    except demo_policy.DemoReadOnlyError:
        pass
    else:
        raise AssertionError("Direct project write was not blocked")
    assert not sentinel.exists()
    assert before == {str(p): sha256(p) for p in protected}
    peak_mib = None
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("faults", ctypes.c_ulong)] + [
                (name, ctypes.c_size_t) for name in ["peak_working", "working", "peak_paged", "paged", "peak_nonpaged", "nonpaged", "pagefile", "peak_pagefile"]]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            peak_mib = round(counters.peak_working / 2**20, 2)
    print(json.dumps({"status": "passed", "entrypoint": "cloud_app.py", "six_methods_top10": True,
                      "spelling_explicit_adoption": True, "highlight_reader": True,
                      "four_models_neighbors_pairs_heatmaps_scatter": True,
                      "pca_tsne_switch_perplexity_reading_guide_scores_unchanged": True,
                      "evaluation_saved_reports_downloads": True, "blocked_backend_calls": len(blocked),
                      "direct_write_blocked": True, "protected_files_unchanged": len(before),
                      "peak_working_set_mib_windows": peak_mib}, ensure_ascii=False))


if __name__ == "__main__":
    main()
