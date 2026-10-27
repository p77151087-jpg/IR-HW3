"""Read and expose one pinned, hash-verified historical evaluation run."""
import json

import altair as alt
import pandas as pd
import streamlit as st

from .core import METHODS
from .corpus import ROOT
from .evaluation import fingerprint, load_queries
from .experiments import _read_run

ASSOCIATION_RUN = "reports/word_association/runs/20261024-c-four-models"
EVALUATION_RUN = "reports/pubmed_hybrid/runs/20261026T105110.598151Z-af1e25ab"


@st.cache_resource(max_entries=1, show_spinner="核對已保存的評估與報告…")
def load_saved_run(signature):
    run = _read_run(ROOT / EVALUATION_RUN)
    if run["hashes"]["queries"] != fingerprint(load_queries()):
        raise ValueError("展示評估與目前查詢版本不符")
    return run


def saved_results():
    root = ROOT / EVALUATION_RUN
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    paths = [root / "manifest.json", *(root / name for name in manifest["outputs_sha256"])]
    signature = tuple((str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in paths)
    run = load_saved_run(signature)
    st.subheader("已保存的正式評估結果")
    st.caption(f"{root.name} · C／standard · k={run['k']} · PubMed 主題參考＋弱規則回退；非人工判讀。")
    st.caption("這是部署前保存的結果。上方互動評估只在記憶體計算，不改寫此 run。")
    frame = pd.DataFrame(run["summary"])
    frame["方法"] = frame["method"].map(METHODS)
    fields = ["precision_at_k", "recall_at_k", "reciprocal_rank", "ndcg_at_k"]
    st.dataframe(frame[["方法", *fields]], hide_index=True, width="stretch")
    chart = frame.melt(id_vars=["方法"], value_vars=fields, var_name="指標", value_name="數值")
    st.altair_chart(alt.Chart(chart).mark_bar().encode(
        x=alt.X("方法:N", sort=list(METHODS.values())),
        y=alt.Y("數值:Q", scale=alt.Scale(domain=[0, 1])),
        color="指標:N", xOffset="指標:N",
        tooltip=["方法:N", "指標:N", alt.Tooltip("數值:Q", format=".6f")]), width="stretch")
    with st.expander("下載已保存評估、圖表與報告"):
        for name in ["metrics_summary.csv", "metrics_per_query.csv", "rankings.csv", "normalization.csv",
                     "query_status.csv", "reference_coverage.csv", "RQ_DISCUSSION.md", "manifest.json"]:
            st.download_button("下載 " + name, (root / name).read_bytes(), name, key="saved_" + name)
        association = ROOT / ASSOCIATION_RUN
        for path in sorted((association / "figures").glob("*.png")):
            st.download_button("下載圖表 " + path.stem, path.read_bytes(), path.name, "image/png", key="saved_figure_" + path.stem)
        for name in ["HW3_REPORT_TFDF.md", "HW3_REPORT_BM25.md"]:
            path = ROOT / "reports" / name
            st.download_button("下載 " + name, path.read_bytes(), name, "text/markdown", key="report_" + name)
