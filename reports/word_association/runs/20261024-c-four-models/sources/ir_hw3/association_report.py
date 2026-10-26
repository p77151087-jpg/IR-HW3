"""Saved figures and a complete, data-derived word association report."""
from itertools import combinations
from pathlib import Path
import os

# Keep plot/font caches inside HW3, including on restricted Windows hosts.
os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parents[1] / "tmp/matplotlib"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .word_association import FIXED_TERMS, MODEL_NAMES, POLICY, pair_score


def markdown_table(rows, columns):
    def cell(value):
        if value is None:
            return "NA"
        return f"{value:.4f}" if isinstance(value, float) else str(value)
    return "\n".join(["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns),
                      *["| " + " | ".join(cell(row.get(c)) for c in columns) + " |" for row in rows]])


def heatmap_values(space):
    return np.array([[pair_score(space, a, b) if pair_score(space, a, b) is not None else np.nan
                      for b in FIXED_TERMS] for a in FIXED_TERMS], dtype=float)


def build_report(output, shared, tfidf, models, pool, metadata, results):
    figures = output / "figures"
    figures.mkdir()
    spaces = {"tfidf": tfidf, **models}
    for name, space in spaces.items():
        values = heatmap_values(space)
        fig, ax = plt.subplots(figsize=(10, 8), layout="constrained")
        image = ax.imshow(values, vmin=-1, vmax=1, cmap="RdBu_r")
        ax.set_xticks(range(10), FIXED_TERMS, rotation=50, ha="right")
        ax.set_yticks(range(10), FIXED_TERMS)
        ax.set_title("TF-IDF word columns (document L2)" if name == "tfidf" else MODEL_NAMES[name])
        for i in range(10):
            for j in range(10):
                value = values[i, j]
                ax.text(j, i, f"{value:.2f}" if np.isfinite(value) else "NA", ha="center", va="center",
                        fontsize=7, color="white" if abs(value) > .65 else "black")
        fig.colorbar(image, ax=ax, label="Cosine in the original word space", shrink=.8)
        fig.savefig(figures / f"heatmap-{name}.png", dpi=150)
        plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(13, 11), layout="constrained", sharex=True, sharey=True)
    for ax, key in zip(axes.ravel(), models):
        for row in results["pairs"]:
            if row["tfidf"] is not None and row[key] is not None:
                ax.scatter(row["tfidf"], row[key], s=22, color="#287e78", alpha=.8)
                ax.annotate(str(row["pair_id"]), (row["tfidf"], row[key]), fontsize=6, xytext=(2, 2), textcoords="offset points")
        ax.plot([0, 1], [0, 1], linestyle="--", color="gray", linewidth=.8)
        ax.set(xlim=(0, 1), ylim=(-1, 1), xlabel="TF-IDF column cosine", ylabel="Embedding cosine", title=MODEL_NAMES[key])
        ax.grid(alpha=.2)
    fig.suptitle("All 45 fixed unordered pairs (numbers = pair_id in pairs.csv)")
    fig.savefig(figures / "pair-scatter.png", dpi=170)
    plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(12, 7), layout="constrained")
    for ax, (key, meta) in zip(axes.ravel(), metadata.items()):
        ax.plot([r["epoch"] for r in meta["epoch_losses"]], [r["loss"] for r in meta["epoch_losses"]])
        ax.set(title=MODEL_NAMES[key], xlabel="Epoch", ylabel="Approximate loss sum")
    fig.suptitle("Training observation only; not semantic accuracy or architecture comparison")
    fig.savefig(figures / "training-loss.png", dpi=150)
    plt.close(fig)

    summary10 = [r for r in results["summary"] if r["k"] == 10]
    frequencies = results["term_status"]
    group_sets = {"四種藥物（6 對）": set(combinations(FIXED_TERMS[:4], 2)),
                  "insulin／glucose／diabetes（3 對）": {tuple(sorted(p, key=FIXED_TERMS.index)) for p in combinations(["insulin", "glucose", "diabetes"], 2)},
                  "receptor／glp-1（1 對）": {("receptor", "glp-1")}}
    groups = []
    for label, members in group_sets.items():
        selected = [r for r in results["pairs"] if (r["left"], r["right"]) in members]
        groups.append({"group": label, **{key: float(np.mean([r[key] for r in selected if r[key] is not None]))
                                          if any(r[key] is not None for r in selected) else None for key in spaces}})
    neighbor_preview = []
    for term in FIXED_TERMS:
        neighbor_preview.append({"term": term, **{method: ", ".join(r["term"] for r in results["neighbors"]
                                     if r["query"] == term and r["method"] == method and r["k"] == 10 and r["rank"] <= 3) for method in spaces}})
    observations = []
    for key in models:
        available = [r for r in results["pairs"] if r[key] is not None and r["tfidf"] is not None]
        if available:
            largest = max(available, key=lambda r: abs(r[key] - r["tfidf"]))
            smallest = min(available, key=lambda r: abs(r[key] - r["tfidf"]))
            observations.append(f"- **{MODEL_NAMES[key]}**：差距最大詞對 {largest['left']}／{largest['right']}，TF-IDF={largest['tfidf']:.4f}、Embedding={largest[key]:.4f}，共同出現於 {largest['cooccurring_documents']} 篇；差距最小詞對 {smallest['left']}／{smallest['right']}，分別為 {smallest['tfidf']:.4f}、{smallest[key]:.4f}。這是完整 45 對的描述統計，數值接近本身不等於語意正確。")
    rho_text = "；".join(f"{r['model']}：ρ={r['rho']:.4f}、平均 Top-10 重疊={r['mean_overlap']:.1%}" if r["rho"] is not None and r["mean_overlap"] is not None else f"{r['model']}：NA" for r in summary10)
    report = f"""# HW3：同一批 3,000 篇的 Embedding 與 TF-IDF 詞彙關聯

本 run：`{output.name}`。四組模型各從新初始化，以同一批 **{shared['documents']:,} 篇摘要、{shared['sentences']:,} 個非空句、{shared['tokens']:,} tokens** 訓練；完整 C 詞彙 {len(tfidf.words):,}，共同候選池 {len(pool):,}。僅摘要正文，標題不進入任何向量。原有 RQ1–RQ5、檢索評估與人工標註另行保留。詞彙關聯統一採 C，舊 B 模型與成果依使用者要求移除。

## 1. 詞關係是否接近？

{rho_text}。Spearman 描述固定詞對的相似度排序是否一致；Top-k 重疊描述整個共同候選池中的近鄰是否一致。兩者衡量一致程度，沒有語意 gold standard，不能解讀成正確率或勝負。

{markdown_table(results['summary'], ['model','k','mean_overlap','valid_terms','total_terms','rho','valid_pairs','status'])}

## 2. 詞群與實際例子

下表是事先固定詞群內的平均 cosine；不同表示的 cosine 分布及基線不同，不能僅以絕對分數較高判斷語意較好。

{markdown_table(groups, ['group', *spaces])}

以下列出全部十詞的前 3 名，完整 Top-5／10／20 在 `neighbors.csv`；逐詞重疊及實際返回數在 `overlap.csv`，沒有事後只保留共同近鄰。

{markdown_table(neighbor_preview, ['term', *spaces])}

{chr(10).join(observations)}

## 3. CBOW／Skip-Gram 與 window 2／5

CBOW 平均局部上下文來預測中心詞，Skip-Gram 由中心詞預測局部上下文；window 是最大句內半徑，`shrink_windows=True` 使實際窗口隨機縮小。上方摘要保留四組全部結果，可直接比較同架構兩個 window、同 window 兩個架構的一致程度。這是固定 seed=42 的單次觀察；不能據此宣稱某架構或窗口普遍最佳。loss 僅供訓練觀察；不同架構的樣本數與累積誤差不同，不能以 loss 當成語意準確率或模型優劣證據。

## 4. 頻率、文件共現與局部上下文

TF-IDF 詞欄向量描述兩詞在整批文件的分布是否相似；僅同篇出現仍不足以保證高 cosine，還受各文件詞頻及整篇文件 norm 影響。Word2Vec 只看同句局部 context；兩詞可不常同篇直接共現，卻因出現在相似的局部上下文而接近。反之，同篇討論的疾病、藥物和試驗用語未必在局部 context 互換。高 CF／DF 通常提供較多訓練或分布資訊；固定停用詞表中的詞已在 C 前處理移除，沒有進入 TF-IDF、訓練序列、模型詞表或候選池，並非顯示階段隱藏。

{markdown_table(frequencies, ['term','cf','df','tfidf', *models, 'in_candidate_pool'])}

`pairs.csv` 的共同出現文件數以相同 3,000 篇、C 詞形計算。低頻詞受 min_count=2 影響，CF=1 會被 Word2Vec 排除；零 IDF 詞會產生 TF-IDF 零欄。狀態逐詞列出，缺詞沒有隨機替代。

## 5. 方法、順序及數學界線

文件以 PMID **字串升冪**排序（沿用 HW2 訓練規則），每篇保留原摘要區塊、句子與剩餘 token 順序；`document_order.json` 和 `sentences.jsonl` 可逐筆查核。每篇「逐句展平 tokens」與整個摘要區塊直接 C 前處理完全一致，並核對與檢索引擎 C 相同。沿用 `english-rules-v1` 句界，context 不跨文件、摘要區塊或偵測句界；縮寫、URL、DOI、email、小數有保護，規則式句界仍可能誤判。C 移除固定停用詞，不 stemming、不展開搜尋複合詞；全為停用詞的句子略過，window 以留下來的詞計算，不能視為仍採原始位置距離。

停用詞表：`resources/stopwords.json`，版本 `{shared['tokenizer']['stopwords_version']}`，共 {shared['tokenizer']['stopwords_count']} 詞；SHA256：`{shared['tokenizer']['stopwords_sha256']}`。此表刻意保留 no、not、without 等否定詞。未列於表中的一般詞、數字或縮寫仍可能出現，去停用詞不保證近鄰具有醫學語意。

完整詞彙建立 A[d,t]=TF(d,t)×log10(N/DF(t))，N=3,000。先以**完整詞彙空間**計算每文件列 L2 norm，再將各列除以該 norm；零列保持零。取詞欄 u(t)（3,000 維）計算詞間 cosine。norm 不因畫面選詞或共同候選池改變。Embedding 用原始 100 維詞向量 cosine，沒有降維取代計算，也不跨空間相減或互算 cosine。

若省略文件列 L2，正 IDF 是每個詞欄的固定倍數，所以 cosine(c·u,d·v)=cosine(u,v)，IDF 會抵消（零 IDF／零欄不適用）。本方法保留的 IDF 影響，是 IDF 改變完整文件 norm 後對各文件座標的**間接**影響，不能籠統說 IDF 直接改變所有詞間 cosine。小型手算及 IDF 抵消測試見測試檔。

- 候選池：四模型詞彙與 TF-IDF 非零欄的交集，字串排序保存；所有方法共用 min_count=2 所得門檻，沒有額外顯示篩選。
- 近鄰：排除自身，所有方法只返回 cosine>0；零分、負分不補入 Top-k。不足 k 顯示實際返回數。**詞對、熱圖、散點保留所有負 cosine**，沒有截零。
- 同分：cosine 取 12 位小數後降冪，再按詞典序；CSV 保存原始分數。
- 重疊：交集數／請求 k（5／10／20），即使返回不足 k 仍固定分母；anchor 缺失或零向量為 NA，摘要明列實際有效分析詞數。
- 固定 45 對：十詞依固定順序取不重複組合，排除對角線。Spearman 使用相同順序、共同有限值、ties 平均名次；少於 2 對或常數陣列為 NA。不報統計顯著，因詞對共享詞彙且不是獨立樣本。

## 6. 完整 45 詞對

{markdown_table(results['pairs'], ['pair_id','left','right','cooccurring_documents', *spaces])}

## 7. 圖表

五張熱圖使用完全相同十詞、順序與 [-1,1] 色階，保留負值與 NA。原空間 cosine 決定所有分數。

{chr(10).join(f'![{name}](figures/heatmap-{name}.png)' for name in spaces)}

![45 詞對；數字對應上表 pair_id](figures/pair-scatter.png)

![訓練 loss；不能當成語意正確率](figures/training-loss.png)

## 8. 限制及重現

這批 GLP-1 主題摘要不是隨機樣本，保留原 1,000 篇後擴充；主題偏差可能使常同篇出現的藥物、疾病、機制詞在 TF-IDF 接近。低頻詞向量與小樣本共現不穩定；只有一次 seed，無法估計重訓變異、一般化或統計顯著。句界規則可能誤判縮寫。新舊 1,000／3,000 篇模型的版本、順序及環境不同，不能只憑新舊差異歸因於增加語料。

正式檢索與評估沒有呼叫這個模組，也沒有使用這頁 session_state。原始 queries.json、人工標註與歷史結果均不回寫。

訓練（另開全新 run，不覆寫本次）：
```powershell
.\\.venv\\Scripts\\python.exe -B -X utf8 -m ir_hw3.embedding_training
```
離線驗證：
```powershell
.\\.venv\\Scripts\\python.exe -B -X utf8 -m ir_hw3.association_validation --run {output.relative_to(output.parents[3]).as_posix() if len(output.parents) > 3 else output.as_posix()}
```

每模型 `models/<name>/metadata.json` 保存全部共同參數、額外 Gensim 預設、初始化向量指紋、每 epoch loss、時間、實際規模、語料／tokenizer／句界／程式指紋、版本與模型／向量 SHA256；`sources/` 凍結訓練程式。所有檔案指紋列於 manifest，成功離線重載後才標 complete；Streamlit 只載入已完成檔案，rerun 不訓練。

Corpus SHA256：`{shared['corpus_sha256']}`。實際版本：`{shared['versions']}`。
"""
    (output / "REPORT.md").write_text(report, encoding="utf-8")
