"""HW3 Streamlit UI: fixed corpus, weighting, ranking, annotation and evaluation."""
from dataclasses import asdict
import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from ir_hw3.core import (CONDITIONS, IDF_MODES,
                         METHODS, VECTOR_METHODS, Engine, Settings)
from ir_hw3.corpus import ROOT, SNAPSHOT, ORIGINAL_SNAPSHOT, abstract_text, load_corpus, sha256
from ir_hw3.spelling import SpellingIndex, build_vocabulary, suggest_query, replace_selected_term
from ir_hw3.evaluation import (csv_rows, evaluate, export_judgment_rows, fingerprint, load_judgments,
                               judgment_path, load_queries, parse_judgment_csv, query_status, save_judgments)
from ir_hw3.experiments import candidate_pool, compare_runs, list_runs, run_experiment, weak_judgments
from ir_hw3.pubmed_reference import build_reference, concept_groups, coverage_rows, load_rules

REFERENCE_LABEL = "PubMed 主題參考＋弱規則回退"
SOURCE_LABELS = {"人工標註": "human", REFERENCE_LABEL: "pubmed_hybrid", "規則弱標籤（示範）": "weak_rules"}

st.set_page_config(page_title="BioSearch · HW3", page_icon="🔬", layout="wide")
st.markdown("""<style>
.stApp { background:#f6f8fa; color:#182d3b; }
[data-testid="stSidebar"] { background:#eaf1f3; }
.block-container { max-width:1360px; padding-top:2rem; }
[data-testid="stMetric"] { background:white; border:1px solid #dde6eb; border-radius:12px; padding:14px; }
mark { background:#c9f2df; color:#153e32; padding:1px 2px; border-radius:3px; }
.eyebrow { color:#287e78; font-weight:700; letter-spacing:.15em; font-size:.8rem; }
.passage { background:white; border-left:4px solid #39968a; padding:16px 20px; line-height:1.8; border-radius:8px; }
</style>""", unsafe_allow_html=True)

def corpus_signature(root=SNAPSHOT):
    paths = [root / "snapshot.json", root / "abstracts.jsonl", root / "selection.json"]
    manifest = json.loads(paths[0].read_text(encoding="utf-8"))
    paths.extend(root / raw["file"] for raw in manifest["raw_files"])
    return tuple((str(path), path.stat().st_size, path.stat().st_mtime_ns) for path in paths)

@st.cache_resource(max_entries=2, show_spinner="驗證固定語料…")
def get_corpus(signature):
    return load_corpus()

@st.cache_resource(max_entries=4, show_spinner="建立文件與查詢的詞彙空間…")
def get_engine(signature, condition, idf):
    documents, _ = get_corpus(signature)
    return Engine(documents, Settings(condition, idf))

@st.cache_resource(max_entries=2, show_spinner="建立固定 1,000 篇摘要的校字詞彙…")
def get_spelling(signature, token_contract):
    documents, manifest = load_corpus(ORIGINAL_SNAPSHOT)
    if len(documents) != 1000:
        raise ValueError("校字語料必須為固定 1,000 篇摘要。")
    return SpellingIndex(build_vocabulary(documents, abstracts_only=True)), manifest["sha256"]

def commit_search(original=None, replacement=None):
    """Callbacks run before widgets; stale suggestion clicks cannot overwrite a draft."""
    query = st.session_state["search_query"]
    if original is not None:
        if query != original:
            return
        query = replacement
        st.session_state["search_query"] = query
        st.session_state["adopted_spelling"] = (original, query)
    else:
        st.session_state.pop("adopted_spelling", None)
    st.session_state["active_search"] = {
        "query": query, "method": st.session_state["search_method"],
    }
    st.session_state["search_pending"] = True

@st.fragment
def search_controls(prepared_spelling):
    # Fragment input changes only update suggestions. Search/adoption escalates
    # to an app rerun, where the committed query becomes the result's query.
    if st.session_state.get("search_pending"):
        st.rerun()
    query = st.text_input("英文查詢", key="search_query", max_chars=2000, live="200ms")
    st.selectbox("權重方法", list(METHODS), key="search_method", format_func=METHODS.get)
    st.button("搜尋", type="primary", on_click=commit_search)
    st.caption("打字稍停即更新候選；可直接搜尋原輸入，或點選一個候選詞後採用並搜尋。未知生醫詞不一定是錯字。")
    st.caption("校字詞彙固定取原 1,000 篇摘要，保留未 stemming 詞形；只用於互動搜尋，正式評估使用原始查詢。")
    if query.strip():
        preview = suggest_query(query, prepared_spelling)
        for change in preview["changes"]:
            st.markdown(f"**「{change['original']}」候選詞（第 {change['start'] + 1} 字元起）：**")
            with st.container(horizontal=True):
                for candidate in change["candidates"]:
                    choice = replace_selected_term(query, change, candidate["term"])
                    label = candidate["term"].capitalize() if change["original"].istitle() else candidate["term"]
                    st.button(label, key=f"spelling_{change['start']}_{candidate['term']}",
                              help=f"採用並搜尋：{choice}（距離 {candidate['distance']}；CF {candidate['cf']}）",
                              on_click=commit_search, args=(query, choice))
        if preview["unresolved_terms"]:
            st.caption("部分未知詞沒有合適候選，已保留原詞；可直接搜尋。")
    active = st.session_state["active_search"]
    if query != active["query"] or st.session_state["search_method"] != active["method"]:
        st.info(f"輸入／設定尚未搜尋；目前結果的實際查詢：{active['query']}")

@st.cache_data(max_entries=2, show_spinner="依已公開規則建立弱標籤…")
def get_weak(signature, queries_hash):
    documents, manifest = get_corpus(signature)
    return weak_judgments(get_engine(signature, "C", "standard"), load_queries(), manifest["sha256"])

@st.cache_data(max_entries=2, show_spinner="從已保存的 PubMed XML 建立參考標籤…")
def get_reference(signature, queries_hash, rules_hash):
    _, manifest = get_corpus(signature)
    return build_reference(get_engine(signature, "C", "standard"), load_queries(), manifest)

def table(rows, **kwargs):
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", **kwargs)

def downloads(rows, label, name):
    st.download_button(label, csv_rows(rows), file_name=name, mime="text/csv")

def document_reader(engine, doc_id, query, method, *, full_first=False):
    document = engine.documents[doc_id]
    st.subheader(document.title)
    st.caption(f"PMID {doc_id} · {document.year} · 原文來源：PubMed · 僅摘要正文參與計分")
    if full_first:
        full, snippet, explanation = st.tabs(["完整摘要", "命中片段", "詞項與計分"])
    else:
        snippet, full, explanation = st.tabs(["命中片段", "完整摘要", "詞項與計分"])
    with snippet:
        st.markdown('<div class="passage">' + engine.snippet(doc_id, query) + '</div>', unsafe_allow_html=True)
    with full:
        for block in document.blocks:
            if block.kind == "abstract":
                st.caption(block.section)
                st.write(block.text)
        st.link_button("在 PubMed 開啟來源", f"https://pubmed.ncbi.nlm.nih.gov/{doc_id}/")
    with explanation:
        rows = engine.explain(query, doc_id, method)
        table(rows)
        if method == "bm25":
            score = sum(row["bm25_contribution"] for row in rows)
            st.caption(f"各詞貢獻總和＝BM25 {score:.8f}；k1=1.2、b=0.75，長度為前處理後摘要 tokens，沒有 L2。")
        else:
            score = sum(row["cosine_contribution"] for row in rows)
            st.caption(f"各詞貢獻總和＝cosine {score:.8f}；文件長度使用整個詞彙空間的 L2 norm。")
        downloads(rows, "下載這篇文件的計分明細", f"weights-{doc_id}-{method}.csv")

def corpus_page(engine, manifest):
    st.title("語料與權重設定")
    st.write("固定同一批文件、前處理與查詢，觀察詞項權重如何改變排名。")
    a, b, c, d = st.columns(4)
    a.metric("英文摘要", f"{engine.n:,}")
    b.metric("詞彙數", f"{len(engine.df):,}")
    c.metric("Tokens", f"{sum(engine.cf.values()):,}")
    d.metric("評估查詢", len(load_queries()))
    st.caption(f"快照：{SNAPSHOT.name} · 摘要與原始 XML 雜湊驗證通過 · {manifest['sha256'][:16]}…")
    formulas = [
        {"方法": "原始 TF", "公式（f > 0）": "f", "意義": "保留線性重複次數"},
        {"方法": "Log TF", "公式（f > 0）": "1 + log10(f)", "意義": "抑制重複詞的線性增長"},
        {"方法": "僅 IDF", "公式（f > 0）": "IDF", "意義": "出現一次或多次使用相同權重"},
        {"方法": "TF × IDF", "公式（f > 0）": "f × IDF", "意義": "同時考慮頻率和區辨力"},
        {"方法": "Log TF × IDF", "公式（f > 0）": "(1 + log10(f)) × IDF", "意義": "原搜尋方法的延伸"},
        {"方法": "BM25", "公式（f > 0）": "Σ query_tf × BM25_IDF × f(k1+1) / [f+k1(1−b+b×dl/avgdl)]",
         "意義": "第六種獨立計分：詞頻飽和與摘要長度校正"},
    ]
    table(formulas)
    st.info("Log TF 與 IDF 均採 log10（以 10 為底）；所有方法在 f=0 時貢獻為 0。五種向量方法的文件與查詢使用相同詞彙表和公式，查詢保留重複詞頻。"
            "標準 IDF 中 DF=N 的詞權重為 0；平滑版保留權重 1。")
    st.caption("BM25：k1=1.2、b=0.75；IDF=log10(1+(N−DF+0.5)/(DF+0.5))。"
               "dl／avgdl 使用前處理後摘要 tokens（平均含所有文件）；查詢 TF 線性累加。BM25 不使用側欄 IDF 或顯式 L2。")
    term_rows = engine.term_statistics()
    st.subheader("CF、DF 與 IDF")
    selected = st.text_input("搜尋詞項", placeholder="例如 semaglutide")
    displayed = [row for row in term_rows if selected.casefold() in row["term"]] if selected else term_rows
    table(displayed[:100])
    st.caption(f"符合 {len(displayed):,} 個詞，畫面最多顯示 100 個；下載包含全部詞彙。CF 是整體詞頻，DF 是文件數。")
    chart = pd.DataFrame(term_rows[:20])
    st.bar_chart(chart, x="term", y="df", color="#29897f", horizontal=True)
    downloads(term_rows, "下載完整詞項統計", "term-statistics.csv")
    with st.expander("資料與實驗界線"):
        st.write(f"只使用摘要正文，標題供閱讀且不參與排名。目前固定 {engine.n:,} 篇；保留原 1,000 篇並依相同 PubMed 條件擴充，沒有混入活動文章庫。"
                 "前處理沿用原 tokenizer，不進行搜尋專用的複合詞展開。GLP-1 保留為一個詞。"
                 "這是單一主題、非隨機抽樣語料，結論不能直接推廣到全部 PubMed。")
        st.download_button("下載作業題目", (ROOT / "docs/Homework-3.pdf").read_bytes(), "Homework-3.pdf", "application/pdf")

def search_page(engine):
    st.title("搜尋與排名")
    st.write("原五種權重方法固定使用 cosine 排名；BM25 使用獨立分數。檢視前 10 名，以及每一個詞如何影響分數。")
    default = st.session_state.get("active_search", {"query": "semaglutide weight loss obesity", "method": "log_tfidf"})
    # Discard the removed option from sessions opened before this UI change.
    st.session_state["active_search"] = {"query": default["query"], "method": default["method"]}
    st.session_state.pop("search_normalize", None)
    for key, value in (("search_query", default["query"]), ("search_method", default["method"])):
        st.session_state.setdefault(key, value)
    st.session_state.pop("search_pending", None)
    token_contract = tuple(sha256(ROOT / path) for path in ("ir_hw1/preprocessing.py", "ir_hw3/spelling.py"))
    prepared_spelling, _ = get_spelling(corpus_signature(ORIGINAL_SNAPSHOT), token_contract)
    search_controls(prepared_spelling)
    active = st.session_state["active_search"]
    query, method = active["query"], active["method"]
    adoption = st.session_state.get("adopted_spelling")
    if adoption and adoption[1] == query:
        st.success(f"原始查詢 → 採用後查詢：{adoption[0]} → {adoption[1]}")
    st.caption(f"實際搜尋查詢：{query}")
    # Also avoid reranking on full reruns (e.g. reader selection or AppTest).
    result_key = (query, method)
    cached = st.session_state.get("search_result", {})
    if cached.get("engine") is not engine or cached.get("key") != result_key:
        _, weights, unknown = engine.query(query, method)
        ranking = engine.rank(query, method, limit=None)
        cached = {"engine": engine, "key": result_key, "weights": weights, "unknown": unknown, "ranking": ranking}
        st.session_state["search_result"] = cached
    weights, unknown, ranking = cached["weights"], cached["unknown"], cached["ranking"]
    if unknown:
        st.warning("詞彙表中沒有：" + "、".join(unknown) + "。這些詞不加入查詢向量。")
    if method == "bm25":
        st.info("BM25 使用自己的分數與固定 IDF：k1=1.2、b=0.75、log10；不適用側欄 IDF。分數可超過 1，不能與 cosine 直接比大小。")
    if not ranking:
        st.info("沒有非零相似度的結果。請改用其他詞；空白、只有停用詞、OOV 或零 IDF 查詢都可能得到零向量。")
        return
    a, b, c = st.columns(3)
    a.metric("有效查詢詞", len(weights))
    score_label = "BM25" if method == "bm25" else "cosine"
    b.metric("非零分數文件", len(ranking))
    c.metric("最高 " + score_label, f"{ranking[0]['score']:.6f}")
    st.caption(f"查詢：{query} · {METHODS[method]} · {score_label} 由高至低；分數不是正確率。")
    top = ranking[:10]
    table(top, column_config={"score": st.column_config.NumberColumn(score_label + " 分數", format="%.6f")})
    downloads(top, "下載 Top 10", f"top10-{method}.csv")
    selected = st.selectbox("查看文件與計分", [row["pmid"] for row in top],
                            format_func=lambda doc_id: f"PMID {doc_id} · {engine.documents[doc_id].title}")
    document_reader(engine, selected, query, method)

def comparison_page(engine, queries):
    st.title("方法比較")
    st.write("原五種方法固定 IDF 與 cosine，比較詞項權重；第六種 BM25 使用獨立公式。六種方法共用語料、前處理與查詢。")
    st.caption("BM25 固定 k1=1.2、b=0.75，使用自己的 log10 IDF，不受側欄 IDF 影響。跨模型請比較名次與評估指標，原始分數不可直接比大小。")
    example = st.selectbox("對照查詢", queries, format_func=lambda q: f"{q['qid']} · {q['text']}")
    query = st.text_input("比較查詢文字", value=example["text"], key="comparison_query_" + example["qid"])
    rankings = {method: engine.rank(query, method, limit=10) for method in METHODS}
    rows = []
    for rank in range(10):
        row = {"排名": rank + 1}
        for method, ranking in rankings.items():
            row[METHODS[method]] = (f"{ranking[rank]['pmid']} · {ranking[rank]['score']:.6f}" if rank < len(ranking) else "—")
        rows.append(row)
    table(rows)
    downloads(rows, "下載方法比較", "method-comparison.csv")
    tabs = st.tabs(list(METHODS.values()))
    for tab, (method, ranking) in zip(tabs, rankings.items()):
        with tab:
            table(ranking)
    st.subheader("Top 10 文件與名次變化")
    left, right = st.columns(2)
    baseline = left.selectbox("基準方法", list(METHODS), format_func=METHODS.get)
    compared = right.selectbox("比較方法", list(METHODS), index=4, format_func=METHODS.get)
    old = {row["pmid"]: row["rank"] for row in rankings[baseline]}
    new = {row["pmid"]: row["rank"] for row in rankings[compared]}
    changes = []
    for doc_id in dict.fromkeys([*new, *old]):
        change = ("新進 Top 10" if doc_id not in old else "移出 Top 10" if doc_id not in new
                  else "名次不變" if old[doc_id] == new[doc_id] else "名次變動")
        changes.append({"pmid": doc_id, "title": engine.documents[doc_id].title, "change": change,
                        "baseline_rank": old.get(doc_id), "compared_rank": new.get(doc_id),
                        "rank_improvement": old[doc_id] - new[doc_id] if doc_id in old and doc_id in new else None})
    table(changes)
    st.caption("名次改善＝基準名次－比較名次，正值表示上升。空白名次表示該方法 Top 10 之外，並不表示整份排名沒有此文件。")
    downloads(changes, "下載 Top 10 變化", f"top10-changes-{baseline}-{compared}.csv")
    st.subheader("raw dot 與 cosine 對照")
    st.info("raw dot 是共同詞權重乘積的總和；cosine 再除以查詢與文件的向量長度。"
            "對照兩者可觀察向量大小對排名的影響。")
    st.caption("此對照使用相同查詢與詞項權重，只含原五種向量方法，BM25 不適用。")
    chosen = st.selectbox("對照的詞項權重", list(VECTOR_METHODS), index=4, format_func=METHODS.get)
    left, right = st.columns(2)
    with left:
        st.caption("raw dot（未正規化點積，補充實驗）")
        table(engine.rank(query, chosen, scoring="dot"))
    with right:
        st.caption("cosine（搜尋使用的相似度）")
        table(engine.rank(query, chosen, scoring="cosine"))

STATUS_LABELS = {"unjudged": "尚未標註", "judged_no_known_relevant": "已判讀，但尚未找到相關文件",
                 "has_known_relevant": "已有相關文件"}
EXCLUSION_LABELS = {"unjudged": "尚未標註", "no_known_relevant": "沒有已知相關文件", "": "納入平均"}

def annotation_drafts(version):
    return st.session_state.setdefault("annotation_drafts", {}).setdefault(version, {})

def capture_annotation(version, qid, doc_id, original, grade_key, reason_key):
    """Copy widget edits into durable session data before navigation cleans widgets."""
    drafts = annotation_drafts(version)
    key = qid + ":" + doc_id
    baseline = drafts.get(key, {}).get("original", original)
    grade, reason = st.session_state[grade_key], st.session_state[reason_key]
    current = {"grade": grade, "reason": reason}
    saved = baseline or {"grade": -1, "reason": ""}
    if current == saved:
        drafts.pop(key, None)
    else:
        drafts[key] = {"qid": qid, "pmid": doc_id, **current, "original": baseline}

def save_annotation_drafts(version, keys, engine, queries, manifest):
    drafts = annotation_drafts(version)
    updates = [drafts[key] for key in keys]
    try:
        if any(row["grade"] == -1 and row["reason"].strip() for row in updates):
            raise ValueError("未標註草稿含有理由；請選擇 0／1／2，或清空理由後再儲存。")
        # Only changed records are merged; a newer edit to the same record is protected.
        expected = {(row["qid"], row["pmid"]): row["original"] for row in updates}
        save_judgments(manifest["sha256"], queries, engine.documents, updates, expected=expected)
    except (ValueError, KeyError, OSError) as exc:
        st.error(f"儲存失敗，草稿仍保留：{exc}")
        return
    for key in keys:
        drafts.pop(key, None)
    path = judgment_path(manifest["sha256"]).relative_to(ROOT).as_posix()
    st.session_state["annotation_saved"] = f"已儲存 {len(updates)} 筆變更至 {path}。"
    st.rerun()

def annotation_panel(engine, queries, manifest, signature):
    manual = load_judgments(manifest["sha256"], queries, engine.documents)
    version = fingerprint([manifest["sha256"], fingerprint(queries)])
    drafts = annotation_drafts(version)
    st.caption("草稿在同一連線中跨文件、查詢、範圍及工作頁保留；儲存成功後才會納入評估。")
    with st.expander("判讀準則與候選池限制"):
        st.markdown((ROOT / "docs/ANNOTATION_GUIDE.md").read_text(encoding="utf-8"))
    query = st.selectbox("標註查詢", queries, format_func=lambda q: f"{q['qid']} · {q['intent']}")
    qid = query["qid"]
    st.write("**查詢：** " + query["text"])
    pool_mode = st.radio("文件範圍", ["六種方法 Top 20 聯集", f"全部 {engine.n:,} 篇"], horizontal=True)
    st.caption("人工標註檔：" + judgment_path(manifest["sha256"]).relative_to(ROOT).as_posix())
    pool = candidate_pool(engine, query["text"])
    ids = pool if pool_mode.startswith("六種") else sorted(engine.documents, key=int)
    records = manual["judgments"].get(qid, {})
    judged_in_pool = sum(doc_id in records for doc_id in pool)
    st.progress(judged_in_pool / len(pool) if pool else 0,
                text=f"目前設定候選池：已儲存 {judged_in_pool} / {len(pool)} 篇")
    relevant = sum(r["grade"] > 0 for r in records.values())
    state = "has_known_relevant" if relevant else ("judged_no_known_relevant" if records else "unjudged")
    st.caption(f"{STATUS_LABELS[state]} · 此查詢已儲存 {len(records)} 篇，其中 {relevant} 篇相關；"
               f"池外已判讀 {sum(doc_id not in pool for doc_id in records)} 篇。完成候選池不等於完整語料判讀。")
    phrase = st.text_input("篩選 PMID 或標題", key="annotation_filter").strip().casefold()
    status_filter = st.radio("標註篩選", ["全部", "尚未標註", "已標註"], horizontal=True)
    ids = [doc_id for doc_id in ids if (phrase in doc_id or phrase in engine.documents[doc_id].title.casefold())
           and (status_filter == "全部" or (doc_id in records) == (status_filter == "已標註"))]
    st.caption(f"篩選符合 {len(ids)} 篇；切換設定時候選池可能變動，人工標註仍依語料與查詢版本保存。")
    if drafts:
        st.warning(f"此資料版本有 {len(drafts)} 筆未儲存草稿。切換不會捨棄；關閉或重新整理連線前請儲存或下載草稿。")
        if st.button("儲存全部草稿", type="primary"):
            save_annotation_drafts(version, list(drafts), engine, queries, manifest)
    if ids:
        selection_key = "annotation_document_" + fingerprint([version, qid, pool_mode, phrase, status_filter])
        if st.session_state.get(selection_key) not in ids:
            st.session_state[selection_key] = ids[0]
        selected = st.selectbox("閱讀待標註摘要", ids, key=selection_key,
                                format_func=lambda doc_id: f"PMID {doc_id} · {engine.documents[doc_id].title}")
        position = ids.index(selected)
        def move_document(offset):
            st.session_state[selection_key] = ids[position + offset]
        previous, progress, following = st.columns([1, 2, 1])
        previous.button("上一篇", on_click=move_document, args=(-1,), disabled=position == 0)
        progress.caption(f"第 {position + 1} / {len(ids)} 篇")
        following.button("下一篇", on_click=move_document, args=(1,), disabled=position + 1 == len(ids))
        document_reader(engine, selected, query["text"], "log_tfidf", full_first=True)
        key = qid + ":" + selected
        original = records.get(selected)
        current = drafts.get(key, original or {"grade": -1, "reason": ""})
        grade_key = "annotation_grade_" + version + key
        reason_key = "annotation_reason_" + version + key
        # Clean editors follow the latest disk record. Dirty editors retain the
        # original snapshot used by expected=..., even after other UI reruns.
        if key not in drafts or grade_key not in st.session_state:
            st.session_state[grade_key] = current["grade"]
        if key not in drafts or reason_key not in st.session_state:
            st.session_state[reason_key] = current["reason"]
        callback = (version, qid, selected, original, grade_key, reason_key)
        st.selectbox("這篇文件的相關性", [-1, 0, 1, 2], key=grade_key,
                     format_func=lambda grade: {-1: "-1 · 未標註", 0: "0 · 不相關", 1: "1 · 相關", 2: "2 · 高度相關"}[grade],
                     on_change=capture_annotation, args=callback)
        st.text_area("這篇文件的判斷依據", key=reason_key, height=100,
                     placeholder="指出摘要中的研究對象、介入／機制與結果，說明與此查詢的關係。",
                     on_change=capture_annotation, args=callback)
        if st.session_state[grade_key] == -1 and st.session_state[reason_key].strip():
            st.info("未標註的理由只保留在草稿；請選擇 0／1／2 後儲存判讀，或清空理由保留未標註。")
        if key in drafts and drafts[key]["grade"] == -1 and not drafts[key]["reason"].strip():
            st.warning("儲存後會移除這筆既有判讀，回到未標註狀態。")
        saveable = key in drafts and (drafts[key]["grade"] != -1 or not drafts[key]["reason"].strip())
        if st.button("儲存這篇人工標註", type="primary", disabled=not saveable):
            save_annotation_drafts(version, [key], engine, queries, manifest)
        if key in drafts:
            if st.button("還原這篇為已儲存版本"):
                drafts.pop(key)
                st.session_state.pop(grade_key, None)
                st.session_state.pop(reason_key, None)
                st.rerun()
        else:
            st.caption("這篇沒有未儲存變更。")
    else:
        st.info("此篩選沒有文件。可清除篩選或切至全部語料補查。")
    with st.expander("匯入／匯出人工標註"):
        all_rows = [{"qid": saved_qid, "pmid": doc_id, **record} for saved_qid, values in manual["judgments"].items()
                    for doc_id, record in values.items()]
        downloads(export_judgment_rows(all_rows, manifest["sha256"], queries), "下載已儲存人工標註", "manual-qrels.csv")
        template = [{"qid": qid, "pmid": doc_id, **records.get(doc_id, {"grade": -1, "reason": ""}),
                     "title": engine.documents[doc_id].title} for doc_id in ids]
        downloads(export_judgment_rows(template, manifest["sha256"], queries), "下載目前範圍標註表", "annotation-template.csv")
        upload = st.file_uploader("匯入版本化人工標註 CSV", type="csv")
        legacy = st.checkbox("我已核對舊格式 CSV 屬於目前語料與查詢版本，允許匯入缺少版本欄位的檔案",
                             help="只供舊版四欄 CSV。無法由檔案證明其版本；已存在但不符的版本欄位不能略過。")
        st.caption("匯入會合併 CSV 中的判讀；有草稿時先儲存或還原，避免同筆資料互相覆蓋。")
        if st.button("匯入人工標註 CSV", disabled=upload is None or bool(drafts)):
            try:
                imported = parse_judgment_csv(upload.getvalue(), manifest["sha256"], queries,
                                              engine.documents, allow_legacy=legacy)
                save_judgments(manifest["sha256"], queries, engine.documents, imported)
                st.session_state["annotation_saved"] = f"已匯入 {len(imported)} 筆人工標註。"
                st.rerun()
            except (ValueError, KeyError, UnicodeError, OSError) as exc:
                st.error(f"匯入失敗，已儲存資料未被取代：{exc}")

def evaluation_page(engine, queries, manifest, signature):
    st.title("效能評估")
    st.write("用固定的 10 個查詢建立相關性集合，再比較六種方法的檢索品質。")
    if "annotation_saved" in st.session_state:
        st.success(st.session_state.pop("annotation_saved"))
    manual = load_judgments(manifest["sha256"], queries, engine.documents)
    progress = query_status(queries, manual)
    ready = sum(row["included_in_mean"] for row in progress)
    st.metric("已有人工相關文件的查詢", f"{ready} / {len(queries)}")
    tab_labels, tab_scores, tab_reproduce = st.tabs(["人工標註", "效能比較", "重現與報告"])
    with tab_labels:
        annotation_panel(engine, queries, manifest, signature)
    with tab_scores:
        source = st.radio("評估標註來源", list(SOURCE_LABELS), horizontal=True)
        k = st.selectbox("評估 k", [5, 10, 20], index=1)
        if source == "人工標註":
            judgments = manual
            if ready < 10:
                st.warning(f"目前只有 {ready} 個查詢具已知相關文件；尚未完成至少 10 個查詢的人工評估。")
            st.caption("池外與未標註文件評分時暫按 0 處理；Recall 只針對已知相關集合，不能稱作完整語料 Recall。")
        elif source == REFERENCE_LABEL:
            st.warning("自動參考標籤，非人工或 PubMed 官方查詢答案。主題依據不足才回退摘要 weak rule；0／1 只表示規則結果。")
            rules = load_rules()
            judgments = get_reference(signature, fingerprint(queries), fingerprint(rules))
            with st.expander("查看 PubMed 參考規則、涵蓋率與限制", expanded=True):
                table(coverage_rows(judgments))
                table([{"qid": q["qid"], "概念組（各組至少一詞）": json.dumps(concept_groups(rules, q["qid"]), ensure_ascii=False)} for q in queries])
                st.caption("metadata_positive 為主題參考正例；weak_fallback 分別列出完全缺少主題資料與資料不足。回退須獨立符合摘要全部概念組。")
                st.write("僅使用原始 XML 的 MeSH、藥物／化學物質、補充概念與關鍵字，不使用排名或標題。人體、動物及細胞不因研究類型而排除。")
                st.write("Recall 為規則參考集合 Recall；nDCG 為二元等級。主題共現不保證研究關係或醫學效度，弱規則仍可能偏向詞彙搜尋。")
                downloads(coverage_rows(judgments), "下載參考標籤涵蓋率", "reference-coverage.csv")
            with st.expander("查看逐筆參考標籤依據"):
                qid = st.selectbox("參考標籤查詢", [q["qid"] for q in queries])
                records = judgments["judgments"][qid]
                pmid = st.selectbox("參考標籤 PMID", list(records), format_func=lambda x: x + " · " + engine.documents[x].title[:75])
                st.json(records[pmid])
                st.caption("人工標註與其草稿另存，這裡不會寫入 manual.json。")
        else:
            st.warning("規則弱標籤只用於示範：依摘要中概念詞共同出現判定，不是人工判讀，也不是醫學相關性的標準答案。")
            judgments = get_weak(signature, fingerprint(queries))
            with st.expander("查看弱標籤規則與限制"):
                table([{"qid": q["qid"], "概念組（各組至少一詞，全組皆需命中）": json.dumps(q["groups"], ensure_ascii=False)} for q in queries])
                st.write("規則獨立於搜尋排名，但與詞彙搜尋共享詞面訊號，可能高估這類方法。每個查詢對整批摘要都產生 0／1 弱標籤。")
        status_rows = query_status(queries, judgments)
        st.caption("六方法一起評估：原五方法使用 cosine；BM25 固定 k1=1.2、b=0.75 與自己的 log10 IDF。"
                   "標籤、查詢、語料與 k 相同；比較排名指標，原始分數尺度不同。")
        included = sum(row["included_in_mean"] for row in status_rows)
        st.info(f"平均指標實際納入 {included} / {len(queries)} 個查詢；排除 {len(queries) - included} 個。"
                "可計算指標不表示人工判讀完成；自動來源衡量的是對該參考規則的符合程度。")
        table([{**row, "status": STATUS_LABELS[row["status"]],
                "exclusion_reason": EXCLUSION_LABELS[row["exclusion_reason"]]} for row in status_rows])
        downloads(status_rows, "下載查詢納入與排除明細", "query-status.csv")
        state_key = fingerprint([asdict(engine.settings), fingerprint(judgments), k])
        if st.button("執行六種方法評估", type="primary"):
            with st.spinner("評估固定查詢集…"):
                detail, summary = evaluate(engine, queries, judgments, k)
                st.session_state["evaluation_result"] = {"key": state_key, "detail": detail, "summary": summary}
        result = st.session_state.get("evaluation_result", {})
        if result.get("key") == state_key:
            if any(row["queries_evaluated"] > 0 for row in result["summary"]):
                table(result["summary"])
                plot = pd.DataFrame(result["summary"]).set_index("method")
                chart = plot[["precision_at_k", "reciprocal_rank", "ndcg_at_k"]].rename(columns={
                    "precision_at_k": f"P@{k}", "reciprocal_rank": "MRR", "ndcg_at_k": f"nDCG@{k}"})
                chart = chart.rename(index={"tf": "TF", "log_tf": "Log TF", "idf": "IDF",
                                            "tfidf": "TF-IDF", "log_tfidf": "Log TF-IDF", "bm25": "BM25"})
                chart_rows = chart.rename_axis("method").reset_index().melt("method", var_name="metric", value_name="value")
                st.altair_chart(alt.Chart(chart_rows).mark_bar().encode(
                    x=alt.X("method:N", title="權重方法", sort=list(chart.index)),
                    xOffset=alt.XOffset("metric:N"),
                    y=alt.Y("value:Q", title="指標分數（0–1）", scale=alt.Scale(domain=[0, 1])),
                    color=alt.Color("metric:N", title="指標", scale=alt.Scale(range=["#237e73", "#4788b5", "#c99b3c"])),
                    tooltip=["method", "metric", alt.Tooltip("value:Q", format=".4f")]), width="stretch")
                downloads(result["summary"], "下載平均指標", "metrics-summary.csv")
                downloads(result["detail"], "下載逐查詢指標", "metrics-per-query.csv")
            else:
                st.info("尚無具已知相關文件的查詢。可完成標註，或選擇自動參考來源並揭露限制。")
                table(result["summary"])
                downloads(result["summary"], "下載評估母數（指標未計算）", "metrics-summary.csv")
        st.caption("P@k 分母固定為 k；MRR 使用完整返回排名；nDCG 的 gain=2^grade−1；judged@k 表示前 k 名的標註覆蓋率。")
        if st.button("匯出這組設定的完整實驗與 RQ 解讀"):
            try:
                with st.spinner("保存排名、指標、正規化檢查與來源雜湊…"):
                    exported = run_experiment(engine, manifest, judgments=judgments, k=k)
                st.session_state["last_experiment_export"] = {"key": state_key, "output": exported["output"]}
            except (ValueError, OSError) as exc:
                st.error(f"實驗保存失敗：{exc}")
        saved_run = st.session_state.get("last_experiment_export", {})
        if saved_run.get("key") == state_key:
            st.success("獨立實驗已保存於 " + saved_run["output"])
            report = (Path(saved_run["output"]) / "RQ_DISCUSSION.md").read_text(encoding="utf-8")
            st.download_button("下載 RQ1–RQ5 解讀", report, "RQ_DISCUSSION.md", "text/markdown")
    with tab_reproduce:
        table([{**row, "status": STATUS_LABELS[row["status"]],
                "exclusion_reason": EXCLUSION_LABELS[row["exclusion_reason"]]} for row in progress])
        st.write("所有實驗固定語料與查詢；輸出包含逐查詢排名、平均與逐查詢指標、L2 檢查、標註候選池、"
                 "完整詞項統計及程式／資料／設定的 SHA256。相同設定重跑，CSV 可逐位元比對。")
        st.code('.\\.venv\\Scripts\\python.exe -m ir_hw3.cli verify\n'
                '.\\.venv\\Scripts\\python.exe -m ir_hw3.cli experiment --source weak\n'
                '.\\.venv\\Scripts\\python.exe -m ir_hw3.cli experiment --source pubmed\n'
                '.\\.venv\\Scripts\\python.exe -m ir_hw3.cli experiment --source human')
        st.info("HW3 必須回答 RQ1–RQ5。報告模板已說明 TF、IDF、排名與 L2 的原理；"
                "使用 PubMed 主題參考時，結論限於自動規則下的結果；真實檢索品質仍待獨立人工驗證。")
        st.subheader("實驗歷史與比較")
        history_source = st.radio("歷史標註來源", list(SOURCE_LABELS), horizontal=True)
        history = list_runs(SOURCE_LABELS[history_source])
        st.caption("只列出輸出指紋完整的成功實驗；每次執行建立獨立目錄。舊版根目錄結果標為 legacy，保留供追溯。")
        if history:
            table([{"run_id": run["run_id"], "UTC": run["created_at_utc"], "legacy": run["legacy"],
                    "source": run["judgment_source"], "documents": run["manifest"]["documents"], **run["settings"], "k": run["k"],
                    "evaluated": run["queries_evaluated"], "total": run["queries_total"],
                    "output": run["output"]} for run in history])
            lookup = {run["output"]: run for run in history}
            chosen = st.selectbox("查看已保存實驗", list(lookup),
                                  format_func=lambda path: lookup[path]["run_id"] + " · " + str(lookup[path]["settings"]))
            table(lookup[chosen]["summary"])
            with st.expander("此實驗的設定與指紋"):
                st.json(lookup[chosen]["manifest"])
            if len(history) > 1:
                other = st.selectbox("與另一實驗比較", list(lookup), index=1,
                                     format_func=lambda path: lookup[path]["run_id"] + " · " + str(lookup[path]["settings"]))
                if st.button("檢查控制條件並比較歷史指標"):
                    comparison = compare_runs(Path(chosen), Path(other))
                    if comparison["settings_differences"]:
                        st.json(comparison["settings_differences"])
                    if comparison["controlled_comparison"]:
                        st.caption("差值＝另一實驗－目前選取實驗；語料、查詢、標註、k、程式與環境證據相同。")
                        table(comparison["metric_differences"])
                    else:
                        st.warning("控制條件或來源版本不同，不能把指標差異歸因於 weighting 或設定；未產生差值。")
                        table([{"field": row["field"], "left": str(row["left"]), "right": str(row["right"])}
                               for row in comparison["mismatches"]])
        else:
            st.info("此來源尚無完整實驗。先於效能比較頁匯出目前設定。")

try:
    signature = corpus_signature()
    with st.sidebar:
        st.markdown('<p class="eyebrow">BIOMEDICAL INFORMATION RETRIEVAL</p>', unsafe_allow_html=True)
        st.title("BioSearch · HW3")
        page = st.radio("工作頁", ["語料與設定", "搜尋與排名", "方法比較", "效能評估", "Embedding／TF-IDF 詞彙關聯"], index=1)
        st.divider()
        st.caption("六種方法共用前處理；IDF 選項適用原五種向量方法")
        condition = st.selectbox("前處理", list(CONDITIONS), index=1, format_func=CONDITIONS.get)
        idf = st.selectbox("IDF 定義", list(IDF_MODES), format_func=IDF_MODES.get)
        st.caption(f"固定 {json.loads((SNAPSHOT / 'snapshot.json').read_text(encoding='utf-8'))['counts']['selected']:,} 篇英文摘要\n\n截止：2026/10/27\n\n語料與搜尋皆可離線使用。")
    engine = get_engine(signature, condition, idf) if page != "Embedding／TF-IDF 詞彙關聯" else None
    _, manifest = get_corpus(signature)
    queries = load_queries()
    if page == "語料與設定":
        corpus_page(engine, manifest)
    elif page == "搜尋與排名":
        search_page(engine)
    elif page == "方法比較":
        comparison_page(engine, queries)
    elif page == "Embedding／TF-IDF 詞彙關聯":
        from ir_hw3.association_ui import association_page
        association_page(ROOT, manifest["sha256"])
    else:
        evaluation_page(engine, queries, manifest, signature)
    all_drafts = {version: rows for version, rows in st.session_state.get("annotation_drafts", {}).items() if rows}
    if all_drafts:
        with st.sidebar:
            st.warning(f"尚有 {sum(len(rows) for rows in all_drafts.values())} 筆未儲存標註草稿。請至效能評估儲存；關閉或重整連線會清除草稿。")
            st.download_button("下載未儲存草稿備份（JSON）",
                               json.dumps({"kind": "unsaved_annotation_drafts", "versions": all_drafts}, ensure_ascii=False, indent=2),
                               "annotation-drafts.json", "application/json")
except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
    st.error(f"資料或設定有誤：{exc}")
    st.info("請在終端機執行 python -m ir_hw3.cli verify 檢查固定語料與設定。")
