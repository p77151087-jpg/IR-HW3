"""Read-only Streamlit word comparison. Training is an explicit offline CLI."""
import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from .word_association import (AssociationRun, FIXED_TERMS, MODEL_NAMES, VERSION, neighbors,
                               pair_score, single_term, overlap)

PAGE = "Embedding／TF-IDF 詞彙關聯"
MODEL_LABELS = {key: name.replace(" · window ", "，視窗 ") for key, name in MODEL_NAMES.items()}
WORD_PRESETS = {
    "insulin": "insulin（胰島素）",
    "glucose": "glucose（葡萄糖）",
    "obesity": "obesity（肥胖）",
    "diabetes": "diabetes（糖尿病）",
    "receptor": "receptor（受體）",
    "glp-1": "GLP-1（研究主題）",
    "semaglutide": "semaglutide（藥物名稱）",
    "liraglutide": "liraglutide（藥物名稱）",
    "dulaglutide": "dulaglutide（藥物名稱）",
    "tirzepatide": "tirzepatide（藥物名稱）",
}


def fill_preset(preset_key, input_key):
    term = st.session_state[preset_key]
    if term is not None:
        st.session_state[input_key] = term


def word_preset(label, preset_key, input_key):
    st.selectbox(label, [None, *WORD_PRESETS], key=preset_key,
                 format_func=lambda term: WORD_PRESETS[term] if term else "自行輸入／選擇預選詞",
                 on_change=fill_preset, args=(preset_key, input_key))


def neighbor_chart(rows, term, title, k):
    return alt.Chart(pd.DataFrame(rows)).mark_bar(color="#25877e").encode(
        x=alt.X("cosine:Q", title="cosine 相似度", scale=alt.Scale(domain=[0, 1])),
        y=alt.Y("term:N", sort=[row["term"] for row in rows], title="相關詞"),
        tooltip=[alt.Tooltip("rank:Q", title="名次"), alt.Tooltip("term:N", title="相關詞"),
                 alt.Tooltip("cosine:Q", title="cosine 相似度", format=".6f")]
    ).properties(title=f"{term} → {title} 前 {k} 名", height=max(180, len(rows) * 25))


def run_signature(root):
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    paths = [root / "manifest.json", *[root / name for name in manifest["artifacts_sha256"]]]
    return tuple((str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in paths)


@st.cache_resource(max_entries=2, show_spinner="核對詞彙模型與稀疏矩陣指紋…")
def get_run(root, signature):
    return AssociationRun(Path(root))


@st.cache_data(max_entries=128, show_spinner=False)
def get_neighbors(root, signature, model, term, k):
    run = get_run(root, signature)
    return (neighbors(run.tfidf, term, run.pool, k), neighbors(run.models[model], term, run.pool, k))


def heatmap(space, title):
    rows = [{"left": a, "right": b, "cosine": pair_score(space, a, b)} for a in FIXED_TERMS for b in FIXED_TERMS]
    return alt.Chart(pd.DataFrame(rows)).mark_rect().encode(
        x=alt.X("right:N", sort=FIXED_TERMS, title=None, axis=alt.Axis(labelAngle=-55)),
        y=alt.Y("left:N", sort=FIXED_TERMS, title=None),
        color=alt.Color("cosine:Q", scale=alt.Scale(domain=[-1, 1], scheme="redblue", reverse=True),
                        title="cosine 相似度"),
        tooltip=[alt.Tooltip("left:N", title="詞 A"), alt.Tooltip("right:N", title="詞 B"),
                 alt.Tooltip("cosine:Q", title="cosine 相似度", format=".5f")]
    ).properties(title=title, height=360)


def related_words(chosen, signature, run, model, k):
    st.write("輸入一個詞，看看兩種方法各找到哪些相關詞。")
    st.caption(f"目前使用 {MODEL_NAMES[model]}；每種方法最多顯示 {k} 個詞，可在「比較設定」更換。")
    word_preset("預選分析詞（中文提示）", "assoc_word_preset", "assoc_word_input")
    st.caption("預選詞會代填英文，也可自行修改；按「比較近鄰」才更新下方的單詞圖表與清單。")
    st.session_state.setdefault("assoc_word_input", st.session_state.get("assoc_submitted_word", "semaglutide"))
    with st.form("assoc_neighbor_form"):
        raw = st.text_input("分析單詞", key="assoc_word_input")
        submitted = st.form_submit_button("比較近鄰")
    if submitted:
        st.session_state["assoc_submitted_word"] = raw
    query = st.session_state.get("assoc_submitted_word", "semaglutide")
    term = single_term(query)
    if term is None:
        st.warning("請輸入一個詞，且不可為已移除的停用詞，例如 GLP-1；比較兩個詞請切到「比較兩個詞」。")
        return
    first, second = get_neighbors(str(chosen), signature, model, term, k)
    result_key = (str(chosen), signature, model, term, k)
    previous_key = st.session_state.get("assoc_displayed_neighbors")
    st.session_state["assoc_displayed_neighbors"] = result_key
    if submitted:
        if result_key == previous_key:
            st.info(f"已確認 {term}：分析詞、模型與詞數相同，因此結果維持相同。可換詞或更換「比較設定」。")
        else:
            st.success(f"已更新為 {term} · {MODEL_NAMES[model]} · 前 {k} 名。")
    shared = [row["term"] for row in first["rows"] if row["term"] in {r["term"] for r in second["rows"]}]
    value = overlap(first, second, k)
    st.caption(f"實際分析詞：{term}")
    st.caption(f"下方兩張長條圖與清單會隨此詞更新；「整體分析」的熱圖與散點圖使用固定十詞。")
    if value is None:
        st.info("這個詞在其中一種方法沒有可用向量，無法比較兩份清單的重疊。")
    elif shared:
        st.info(f"兩種方法共同找到 {len(shared)} 個詞：" + "、".join(shared))
    else:
        st.info(f"兩種方法的前 {k} 名沒有共同詞。這代表清單不同，不代表其中一邊正確率為零。")
    st.caption(f"「兩邊前 {k} 名都有」表示共同入榜；「只在這邊前 {k} 名」表示另一邊未入榜，不代表另一邊完全找不到或不相關。")
    for column, title, result in zip(st.columns(2),
            ["TF-IDF：文章分布相近", "Embedding：上下文相近"], [first, second]):
        with column:
            st.markdown(f"**{title}**")
            st.caption(f"顯示 {result['returned']} / {k} 個相關詞")
            if result["status"] != "ok":
                st.warning("無有效向量：這個詞未收錄、詞頻不足或向量為零，請換一個詞。")
            rows = [{**r, "關係": f"兩邊前 {k} 名都有" if r["term"] in shared else f"只在這邊前 {k} 名"} for r in result["rows"]]
            if rows:
                st.altair_chart(neighbor_chart(rows, term, title.split("：")[0], k), width="stretch")
            st.dataframe(pd.DataFrame(rows, columns=["rank", "term", "cosine", "關係"]), hide_index=True,
                         column_config={"rank": st.column_config.NumberColumn("名次", format="%d", width="small"),
                             "term": st.column_config.TextColumn("相關詞"),
                             "cosine": st.column_config.NumberColumn("cosine 相似度", format="%.6f")}, width="stretch")
    st.caption("cosine 越大，表示在該方法的空間中越相近；這不是語意正確率。兩種方法都已在建模前移除固定停用詞表中的詞；一般詞、數字與縮寫仍可能入榜。")
    with st.expander("詞頻與比較規則"):
        i = run.tfidf.lookup.get(term)
        cf, df = (int(run.tfidf.cf[i]), int(run.tfidf.df[i])) if i is not None else (0, 0)
        st.write(f"{term} 在整批摘要出現 {cf:,} 次，分布於 {df:,} 篇。")
        st.write(f"清單重疊率＝共同找到的詞數／指定的 {k} 個詞：" + (f"{value:.1%}" if value is not None else "無法計算"))
        st.caption("在固定共同候選池找近鄰，排除自身；只返回 cosine>0，不以零分補足 k。同分先取 12 位小數再按詞典序。返回不足 k 時，重疊分母仍為請求 k。")


def compare_two_words(run):
    st.write("輸入兩個詞，觀察 TF-IDF 與四組 Embedding 模型各自算出的關聯程度。")
    previous_left, previous_right = st.session_state.get("assoc_submitted_pair", ("insulin", "glucose"))
    preset_a, preset_b = st.columns(2)
    with preset_a:
        word_preset("預選詞 A（中文提示）", "assoc_preset_a", "assoc_pair_a")
    with preset_b:
        word_preset("預選詞 B（中文提示）", "assoc_preset_b", "assoc_pair_b")
    st.caption("先選附中文提示的詞，或直接修改下方英文；按「比較詞對」才更新結果。例如胰島素＋葡萄糖、肥胖＋糖尿病。")
    st.session_state.setdefault("assoc_pair_a", previous_left)
    st.session_state.setdefault("assoc_pair_b", previous_right)
    with st.form("assoc_pair_form"):
        left_col, right_col = st.columns(2)
        left = left_col.text_input("詞 A", key="assoc_pair_a")
        right = right_col.text_input("詞 B", key="assoc_pair_b")
        pair_submitted = st.form_submit_button("比較詞對")
    if pair_submitted:
        st.session_state["assoc_submitted_pair"] = (left, right)
    a_raw, b_raw = st.session_state.get("assoc_submitted_pair", ("insulin", "glucose"))
    a_term, b_term = single_term(a_raw), single_term(b_raw)
    if a_term is None or b_term is None:
        st.warning("每個輸入框請填一個非停用詞，例如 insulin 與 glucose。")
        return
    rows = [{"method": name, "cosine": pair_score(space, a_term, b_term),
             "詞A狀態": space.status(a_term), "詞B狀態": space.status(b_term)}
            for name, space in {"tfidf": run.tfidf, **run.models}.items()]
    display = [{**row, "method_label": "TF-IDF" if row["method"] == "tfidf" else MODEL_NAMES[row["method"]],
                "cosine_display": f"{row['cosine']:.6f}" if row["cosine"] is not None else "無法計算"} for row in rows]
    st.caption(f"實際詞對：{a_term} ／ {b_term} · 共同出現於 {run.tfidf.cooccurrence(a_term, b_term)}／3,000 篇摘要")
    st.dataframe(pd.DataFrame(display), hide_index=True, width="stretch",
                 column_order=["method_label", "cosine_display"], column_config={
                     "method_label": st.column_config.TextColumn("方法"),
                     "cosine_display": st.column_config.TextColumn("cosine 相似度")})
    st.caption("每列都在自己的向量空間計算；正分表示方向相近，負分保留。分數高低不是方法的正確率。此表一次比較全部四組模型。")
    if any(row["cosine"] is None for row in rows):
        st.warning("部分方法沒有可用向量，因此顯示「無法計算」，不當作 0 分。")
        with st.expander("查看無法計算的原因"):
            states = {"ok": "可計算", "oov": "詞表未收錄", "zero_vector": "向量為零"}
            st.dataframe(pd.DataFrame([{"方法": row["method_label"], "詞 A": states[row["詞A狀態"]],
                                       "詞 B": states[row["詞B狀態"]]} for row in display]), hide_index=True)


def overlap_calculation(results):
    st.markdown("**平均重疊率怎麼算？**")
    st.markdown("1. 選一個分析詞，TF-IDF 與 Embedding 各取前 10 個近鄰。\n"
                "2. 共同入榜的詞數 ÷ 10 ＝這個分析詞的重疊率。\n"
                "3. 將每個有效分析詞的重疊率相加，再除以有效分析詞數。")
    model = "skipgram_w5"
    details = []
    for row in results["overlap"]:
        if row["model"] != model or row["k"] != 10:
            continue
        first = [r["term"] for r in results["neighbors"]
                 if r["query"] == row["term"] and r["method"] == "tfidf" and r["k"] == 10]
        second = {r["term"] for r in results["neighbors"]
                  if r["query"] == row["term"] and r["method"] == model and r["k"] == 10}
        shared = [term for term in first if term in second]
        count = len(shared) if row["overlap"] is not None else None
        details.append({"分析詞": row["term"], "共同詞數": count,
                        "重疊率": f"{row['overlap']:.0%}" if count is not None else "無法計算",
                        "共同詞": "、".join(shared) if shared else "無"})
    anchor = next((row for row in details if row["分析詞"] == "semaglutide"), None)
    st.caption(f"以下實例固定比較 TF-IDF 與 {MODEL_LABELS[model]}，使用目前 C 版本保存的近鄰清單。")
    if anchor is not None and anchor["共同詞數"] is not None:
        st.write(f"實例：semaglutide 的兩份前 10 名有 {anchor['共同詞數']} 個共同詞"
                 f"（{anchor['共同詞']}），所以是 {anchor['共同詞數']} ÷ 10 ＝ {anchor['重疊率']}。")
    valid = [row for row in details if row["共同詞數"] is not None]
    if valid:
        total = sum(row["共同詞數"] for row in valid)
        rate = total / (10 * len(valid))
        st.write(f"這組模型的 {len(valid)} 個有效分析詞，共有 {total} 個共同入榜詞次。"
                 f"平均重疊率＝{total} ÷（10 × {len(valid)}）＝{rate:.0%}，"
                 f"等同平均每 10 個近鄰有 {total / len(valid):.1f} 個共同詞。")
    with st.expander("查看十個分析詞的重疊率計算明細"):
        st.dataframe(pd.DataFrame(details), hide_index=True, width="stretch",
                     column_config={"共同詞數": st.column_config.NumberColumn("共同詞數", format="%d")})
        st.caption("共同詞數按各分析詞分別計算，同一詞在不同分析詞的清單中會分別計入；只比較是否入榜，不比較名次或分數。分母固定為 10，不足十個不補零分詞；缺向量者顯示無法計算，不當成 0% 納入平均。")


def overlap_overview(results):
    st.subheader("TF-IDF 和 Embedding 的關係一樣嗎？")
    st.write("TF-IDF 看兩個詞在文章中的出現分布；Embedding 看兩個詞的上下文。下面比較它們找出的相關詞，有多少相同。")
    rows = [{**row, "model_label": MODEL_LABELS[row["model"]],
             "overlap_display": f"{row['mean_overlap'] * 100:g}%" if row["mean_overlap"] is not None else "無法計算",
             "sample_display": f"{row['valid_terms']}／{row['total_terms']}"}
            for row in results["summary"] if row["k"] == 10]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                 column_order=["model_label", "overlap_display", "sample_display"], column_config={
                     "model_label": st.column_config.TextColumn("Embedding 模型"),
                     "overlap_display": st.column_config.TextColumn("平均重疊率"),
                     "sample_display": st.column_config.TextColumn("有效分析詞數")})
    st.caption("固定十個分析詞，每個取兩方法的前 10 名：共同詞數 ÷ 10，再對有效分析詞取平均。這張表固定看前 10 名，不隨單詞輸入或「顯示相關詞數」改變；缺向量的詞不納入平均。")
    valid = [row for row in rows if row["mean_overlap"] is not None]
    if valid:
        best_rate = max(row["mean_overlap"] for row in valid)
        best = "、".join(row["model_label"] for row in valid if row["mean_overlap"] == best_rate)
        if best_rate == 0:
            finding = "本次有效分析詞的前 10 名沒有共同詞，兩種方法找到的近鄰清單不同。"
        elif all(row["mean_overlap"] == 1 for row in valid):
            finding = "本次有效分析詞的前 10 名集合完全重疊；集合相同仍不表示名次或分數相同。"
        else:
            finding = "本次近鄰清單有部分重疊，但整體並不相同。"
        st.info(f"{finding}與 TF-IDF 重疊最高的是 {best}（{best_rate:.0%}），平均每 10 個近鄰約有 {best_rate * 10:.1f} 個相同。")
    else:
        st.info("目前沒有可用的重疊率，無法比較兩方法的近鄰清單。")
    st.caption("重疊率衡量兩方法是否一致，不是正確率；較一致也不代表語意判斷較正確。")
    overlap_calculation(results)


def scatter_example(results):
    st.markdown("**用實際詞對對照圖上的座標**")
    examples = [row for row in results["pairs"] if (row["left"], row["right"]) in {
        ("semaglutide", "liraglutide"), ("insulin", "receptor")}]
    if not examples:
        st.info("這份成果沒有可用的示範詞對。")
        return
    chosen = st.selectbox("散點圖實例詞對", [row["pair_id"] for row in examples],
                          format_func=lambda pair_id: next(f"{r['left']} ／ {r['right']}" for r in examples if r["pair_id"] == pair_id),
                          key="assoc_scatter_pair")
    pair = next(row for row in examples if row["pair_id"] == chosen)
    rows = [{"模型": MODEL_LABELS[model], "tfidf": pair["tfidf"], "embedding": pair[model]}
            for model in MODEL_NAMES]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", column_config={
        "tfidf": st.column_config.NumberColumn("X：TF-IDF", format="%.6f"),
        "embedding": st.column_config.NumberColumn("Y：Embedding", format="%.6f")})
    st.caption(f"詞對編號 {pair['pair_id']}：{pair['left']} ／ {pair['right']}；共同出現於 {pair['cooccurring_documents']}／3,000 篇摘要。編號不是名次，共現篇數也不是正確率。")
    if pair["tfidf"] is not None:
        st.write(f"這組詞對的 X 都是 {pair['tfidf']:.6f}，所以四組模型的點在同一個 X 位置；"
                 "Y 則依表中的 Embedding 分數上下分開。可在圖上移到該詞對，對照模型、詞對與兩個分數。")
    else:
        st.info("這組詞對缺少 TF-IDF 向量，無法在散點圖定位；缺值不當成 0 分。")
    st.caption("分數較高表示在該方法的空間中較接近，不能只因某模型的點比較高，就認定它比較正確。")


def overall_analysis(run, results, model, k):
    overlap_overview(results)
    st.write("這區使用固定十個詞，比較四組模型與 TF-IDF 的整體一致程度。")
    st.caption("固定分析不隨「分析單詞」或「詞 A／詞 B」的輸入改變；重疊與一致度都不是正確率。")
    summary = [{**row, "model_label": MODEL_NAMES[row["model"]],
                "overlap_display": f"{row['mean_overlap']:.1%}" if row["mean_overlap"] is not None else "無法計算"}
               for row in results["summary"] if row["k"] == k]
    with st.expander("進階：排序一致度與逐詞明細"):
        st.dataframe(pd.DataFrame(summary), hide_index=True, width="stretch",
                     column_order=["model_label", "overlap_display", "rho", "valid_terms", "valid_pairs"], column_config={
                         "model_label": st.column_config.TextColumn("Embedding 模型"),
                         "overlap_display": st.column_config.TextColumn(f"前 {k} 詞平均重疊率"),
                         "rho": st.column_config.NumberColumn("詞對排序一致度", format="%.4f",
                             help="Spearman ρ：比較同一批詞對的分數排序，範圍 −1 到 1。"),
                         "valid_terms": st.column_config.NumberColumn("有效單詞數", format="%d"),
                         "valid_pairs": st.column_config.NumberColumn("有效詞對數", format="%d")})
        st.caption("重疊率：兩邊前 k 名共同找到多少詞。排序一致度：兩方法對同一批詞對的關聯強弱排序是否相近。")
        st.write("、".join(FIXED_TERMS))
        st.caption(f"以下逐詞重疊使用 {MODEL_NAMES[model]} 與前 {k} 詞。")
        st.dataframe(pd.DataFrame([r for r in results["overlap"] if r["k"] == k and r["model"] == model]), hide_index=True)
        st.dataframe(pd.DataFrame(results["term_status"]), hide_index=True)
    st.subheader("詞彙關聯熱圖")
    st.write("每一格代表橫軸與縱軸那兩個詞的 cosine。兩張圖使用相同詞序與色階，可比較同一格的關聯程度。")
    for col, space, title in zip(st.columns(2), [run.tfidf, run.models[model]], ["TF-IDF", MODEL_NAMES[model]]):
        with col:
            st.altair_chart(heatmap(space, title), width="stretch")
    st.caption("色階固定 [-1,1]，負分保留，缺向量為空白；各自在原始 3,000 維／100 維空間計算。更換「比較設定」中的模型會更新右圖；單詞輸入不改變這批固定十詞。")
    st.subheader("詞對分數散點圖")
    st.write("每個點是一對詞在一個 Embedding 模型下的比較；顏色區分四組模型。")
    st.markdown("- **往右看 X 軸**：TF-IDF 認為兩詞的文章分布越相近。\n"
                "- **往上看 Y 軸**：該 Embedding 模型認為兩詞的上下文越相近。\n"
                "- **同一詞對看四種顏色**：X 相同，Y 可能不同，可看出模型與視窗帶來的評分差異。")
    st.caption("本次固定十詞形成 45 組不重複詞對，每組搭配四個模型，共 180 個點。重疊率比較近鄰清單是否相同；這張圖比較同一批詞對的分數。")
    scatter = [{"model": key, "model_label": MODEL_LABELS[key], "pair": f"{row['left']} ／ {row['right']}", "pair_id": row["pair_id"],
                "tfidf": row["tfidf"], "embedding": row[key], "cooccurring_documents": row["cooccurring_documents"]}
               for row in results["pairs"] for key in MODEL_NAMES if row["tfidf"] is not None and row[key] is not None]
    chart = alt.Chart(pd.DataFrame(scatter)).mark_circle(size=65, opacity=.75).encode(
        x=alt.X("tfidf:Q", title="TF-IDF cosine 相似度", scale=alt.Scale(domain=[0, 1])),
        y=alt.Y("embedding:Q", title="Embedding cosine 相似度", scale=alt.Scale(domain=[-1, 1])),
        color=alt.Color("model_label:N", title="模型"), shape=alt.Shape("model_label:N", title="模型"),
        tooltip=[alt.Tooltip("model_label:N", title="模型"), alt.Tooltip("pair:N", title="詞對"),
                 alt.Tooltip("pair_id:Q", title="詞對編號", format="d"),
                 alt.Tooltip("tfidf:Q", title="TF-IDF 相似度", format=".6f"),
                 alt.Tooltip("embedding:Q", title="Embedding 相似度", format=".6f"),
                 alt.Tooltip("cooccurring_documents:Q", title="共同出現摘要篇數", format="d")]
    ).properties(height=420).interactive()
    st.altair_chart(chart, width="stretch")
    st.caption("使用固定 45 個不重複詞對；Spearman 的同分採平均名次，缺值或常數陣列不硬算，也不據此宣稱統計顯著。")
    scatter_example(results)
    with st.expander("查看 45 詞對原始分數"):
        st.dataframe(pd.DataFrame(results["pairs"]), hide_index=True)


def association_page(root, expected_corpus):
    st.header(PAGE)
    st.write("比較兩種找相關詞的方法：TF-IDF 看詞在文章中的分布，Embedding 看詞的上下文。")
    st.caption("這裡比較詞與詞的關聯，與文件搜尋排名及檢索評估分開。")
    st.caption("本頁統一採 C 前處理：切詞＋移除停用詞。TF-IDF 與四組 Embedding 都由去停用詞後的摘要重新建立。")
    available = []
    from .demo_policy import is_demo
    if is_demo():
        from .cloud_results import ASSOCIATION_RUN
        candidates = [root / ASSOCIATION_RUN / "manifest.json"]
    else:
        candidates = sorted((root / "reports/word_association/runs").glob("*/manifest.json"), reverse=True)
    for path in candidates:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if (manifest.get("status") == "complete" and manifest.get("version") == VERSION
                and manifest.get("corpus_sha256") == expected_corpus
                and manifest.get("tokenizer", {}).get("condition") == "C"
                and manifest.get("tokenizer", {}).get("keep_stopwords") is False):
            available.append(path.parent)
    if not available:
        if is_demo():
            raise ValueError("缺少指定的完整 C 詞彙模型；展示版不會訓練或下載。")
        st.warning("尚無這批 3,000 篇的完整 C 詞彙關聯成果。完成訓練與輸出後才會顯示。")
        st.code(r".\.venv\Scripts\python.exe -B -X utf8 -m ir_hw3.embedding_training", language="powershell")
        return
    with st.expander("比較設定（更換模型、顯示詞數）"):
        left, right = st.columns([3, 1])
        model = left.selectbox("Embedding 模型", list(MODEL_NAMES), format_func=MODEL_NAMES.get, key="assoc_model",
                               help="CBOW 與 Skip-Gram 是兩種訓練方式；window 是參考附近詞的最大範圍。這裡只選已完成模型，不重新訓練。")
        k = right.selectbox("顯示相關詞數", [5, 10, 20], index=1, key="assoc_k",
                            help="每種方法最多列出幾個相關詞；不以零分補足。")
    words, pair, overall = st.tabs(["找相關詞", "比較兩個詞", "整體分析"])
    with st.expander("資料與模型明細"):
        chosen = (st.selectbox("詞彙關聯 run", available, format_func=lambda p: p.name, key="assoc_run")
                  if len(available) > 1 else available[0])
        st.caption(f"目前資料版本：{chosen.name}。固定 3,000 篇摘要／C 前處理，與文件檢索共用停用詞表。")
        signature = run_signature(chosen)
        run = get_run(str(chosen), signature)
        results = json.loads((chosen / "results.json").read_text(encoding="utf-8"))
        meta = run.metadata[model]
        a, b, c, d = st.columns(4)
        a.metric("摘要", f"{meta['documents']:,}")
        b.metric("句子", f"{meta['sentences']:,}")
        c.metric("Tokens", f"{meta['tokens']:,}")
        d.metric("共同候選詞", f"{len(run.pool):,}")
        st.dataframe(pd.DataFrame([{"model": key, "documents": m["documents"], "sentences": m["sentences"],
                                    "tokens": m["tokens"], "vocabulary": m["vocabulary_size"], "seconds": m["seconds"],
                                    "offline_reload": m["offline_reload_exact"]} for key, m in run.metadata.items()]), hide_index=True)
        st.json(meta)
        st.caption("100 維、30 epochs、min_count=2、seed=42、workers=1；模型已完成並驗證離線重載。Loss 不能當語意正確率，也不能直接比較架構優劣。")
        st.markdown("TF-IDF 使用去停用詞後的完整 C 詞表建立 TF × log10(N/DF) 文件×詞矩陣，先做完整文件列 L2，再比較詞欄 cosine。Embedding 在自己的原始 100 維空間比較 cosine。省略文件 L2 時，正的固定 IDF 倍數會在詞欄 cosine 抵消；本方法的 IDF 效果來自文件 norm。")
        st.caption(f"C 使用固定停用詞表（{meta['tokenizer']['stopwords_count']} 詞），不 stemming、不展開搜尋複合詞；window 按移除後留下的詞計算。單一主題、低頻詞、句界與單次 seed 限制一般化；沒有預設勝出模型。")
    with words:
        related_words(chosen, signature, run, model, k)
    with pair:
        compare_two_words(run)
    with overall:
        overall_analysis(run, results, model, k)
    with st.expander("下載與重現"):
        for filename, label in [("neighbors.csv", "全部近鄰 CSV"), ("overlap.csv", "全部重疊率 CSV"),
                                ("pairs.csv", "45 詞對 CSV"), ("summary.csv", "模型摘要 CSV"),
                                ("term_status.csv", "十詞頻率與狀態 CSV"), ("REPORT.md", "完整比較報告")]:
            st.download_button(label, (chosen / filename).read_bytes(), filename, key="assoc_download_" + filename)
        st.caption(f"成果位置：{chosen.relative_to(root)}。以下下載為保存的固定十詞實驗，不隨互動輸入改寫。模型、稀疏矩陣與近鄰按來源指紋快取，切換不訓練。")
        st.code(r".\.venv\Scripts\python.exe -B -X utf8 -m ir_hw3.embedding_training", language="powershell")

