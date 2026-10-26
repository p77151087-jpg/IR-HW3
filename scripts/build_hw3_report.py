"""Build the course report from frozen runs, without changing labels or runs.

This is a report derivation, not another relevance-annotation procedure. The
default destination must not exist; use --report for a separate reproduction.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ir_hw3.core import Engine, METHODS as ALL_METHODS, VECTOR_METHODS, Settings, LOGARITHM_BASE, BM25_PARAMETERS, BM25_FORMULA
from ir_hw3.corpus import load_corpus
from ir_hw3.evaluation import fingerprint, load_queries




def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def table(headers, rows) -> str:
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ")
    return "\n".join(["| " + " | ".join(map(cell, headers)) + " |",
                      "| " + " | ".join("---" for _ in headers) + " |"] +
                     ["| " + " | ".join(map(cell, row)) + " |" for row in rows])


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def independent_metrics(ranking: list[dict], labels: dict, k: int) -> dict:
    # Recompute saved observations, without calling evaluation.metrics.
    positive = {pid for pid, record in labels.items() if record["grade"] == 1}
    gains = [int(row["pmid"] in positive) for row in ranking]
    hit_count = sum(gains[:k])
    first = next((i + 1 for i, gain in enumerate(gains) if gain), None)
    ideal = sum(1 / math.log2(i + 2) for i in range(min(k, len(positive))))
    return {"precision_at_k": hit_count / k,
            "recall_at_k": hit_count / len(positive),
            "reciprocal_rank": 1 / first if first else 0.0,
            "ndcg_at_k": sum(g / math.log2(i + 2) for i, g in enumerate(gains[:k])) / ideal}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--analysis", type=Path, help="固定的 log10 analysis 目錄；省略時選最新相容來源。")
    args = parser.parse_args()
    analysis = args.analysis
    if analysis is None:
        candidates = sorted((ROOT / "reports/pubmed_hybrid/analysis").glob("*/verification.json"), reverse=True)
        active_hash = fingerprint(load_queries())
        analysis = next((p.parent for p in candidates if read_json(p).get("logarithm_base") == LOGARITHM_BASE
                         and read_json(p).get("queries_sha256") == active_hash), None)
    if analysis is None:
        raise ValueError("請先執行 evaluate_pubmed_reference.py 產生 log10 實驗。")
    analysis = analysis.resolve()
    evidence = read_json(analysis / "verification.json")
    if not analysis.is_relative_to(ROOT) or evidence.get("logarithm_base") != LOGARITHM_BASE:
        raise ValueError("報告 analysis 的底數或路徑不符。")
    MAIN, REPEAT, WEAK = [Path(r["output"]).resolve() for r in evidence["runs"]]
    if any(not p.is_relative_to(ROOT) for p in (MAIN, REPEAT, WEAK)):
        raise ValueError("引用的 run 必須位於本專案內。")
    is_tfdf = read_json(MAIN / "manifest.json").get("query_design_version") == "tfdf-v1"
    report = (args.report or ROOT / "reports" / ("HW3_REPORT_TFDF.md" if is_tfdf else "HW3_REPORT_BM25.md")).resolve()
    if is_tfdf:
        from ir_hw3.query_design import build_design_report
        print(json.dumps(build_design_report(analysis, report), ensure_ascii=False))
        return
    assets = report.with_name(report.stem + "_assets")
    if not report.is_relative_to(ROOT) or not assets.is_relative_to(ROOT):
        raise ValueError("報告輸出必須位於 HW3 專案內。")
    if report.exists() or assets.exists():
        raise FileExistsError("保留既有報告；請用 --report 指定新的檔名。")

    manual_before = {p.relative_to(ROOT).as_posix(): sha(p)
                     for p in (ROOT / "data/judgments").rglob("*.json")}
    inputs = {(analysis / "verification.json").relative_to(ROOT).as_posix(): sha(analysis / "verification.json")}
    manifests = []
    for directory in (MAIN, REPEAT, WEAK):
        manifest = read_json(directory / "manifest.json")
        if manifest["status"] != "complete":
            raise ValueError("只能引用完整實驗。")
        for filename, expected in manifest["outputs_sha256"].items():
            path = directory / filename
            if sha(path) != expected:
                raise ValueError(f"實驗輸出指紋不符：{path}")
            inputs[path.relative_to(ROOT).as_posix()] = expected
        inputs[(directory / "manifest.json").relative_to(ROOT).as_posix()] = sha(directory / "manifest.json")
        manifests.append(manifest)
    manifest, repeat, weak_manifest = manifests
    declared = manifest.get("methods", list(VECTOR_METHODS))
    if declared not in (list(VECTOR_METHODS), list(ALL_METHODS)):
        raise ValueError("不支援的報告方法清單。")
    METHODS = {key: ALL_METHODS[key] for key in declared}
    if (manifest["judgment_source"] != "pubmed_hybrid" or
            weak_manifest["judgment_source"] != "weak_rules" or
            manifest["settings"] != {"condition": "C", "idf": "standard"} or
            manifest["documents"] != 3000 or manifest["queries_evaluated"] != 10 or manifest["k"] != 10 or manifest.get("logarithm_base") != LOGARITHM_BASE):
        raise ValueError("這份報告的範圍為固定 3000 篇、十查詢、C、標準 IDF、k=10。")
    for key in ("settings", "corpus_sha256", "queries_sha256", "source_sha256", "methods", "k", "logarithm_base", "weighting_version"):
        if manifest[key] != weak_manifest[key] or manifest[key] != repeat[key]:
            raise ValueError(f"來源對照的控制條件不符：{key}")
    if any(sha(MAIN / name) != sha(REPEAT / name) for name in manifest["outputs_sha256"]):
        raise ValueError("兩次混合參考實驗的輸出不一致。")
    if sha(MAIN / "rankings.csv") != sha(WEAK / "rankings.csv"):
        raise ValueError("標籤敏感度比較必須使用相同排名。")

    # An edited README does not change the frozen mathematical implementation.
    changed_source = [name for name, expected in manifest["source_sha256"].items()
                      if sha(ROOT / name) != expected]
    if set(changed_source) - {"README.md"}:
        raise ValueError(f"實驗程式／規則已有變更，須重新核對：{changed_source}")
    data = read_json(MAIN / "judgments.json")
    queries = read_json(MAIN / "queries.json")
    rules = read_json(MAIN / "reference_rules.json")
    metrics = read_csv(MAIN / "metrics_per_query.csv")
    summary = read_csv(MAIN / "metrics_summary.csv")
    weak_summary = {r["method"]: r for r in read_csv(WEAK / "metrics_summary.csv")}
    rankings = read_csv(MAIN / "rankings.csv")
    by_rank = {(q["qid"], m): [] for q in queries for m in METHODS}
    for row in rankings:
        by_rank[row["qid"], row["method"]].append(row)
    for rows in by_rank.values():
        rows.sort(key=lambda r: int(r["rank"]))
    maximum_error = 0.0
    for row in metrics:
        expected = independent_metrics(by_rank[row["qid"], row["method"]], data["judgments"][row["qid"]], 10)
        maximum_error = max(maximum_error, *(abs(float(row[key]) - value) for key, value in expected.items()))
    for row in summary:
        subset = [r for r in metrics if r["method"] == row["method"]]
        for key in ("precision_at_k", "recall_at_k", "reciprocal_rank", "ndcg_at_k"):
            maximum_error = max(maximum_error, abs(float(row[key]) - sum(float(r[key]) for r in subset) / 10))
    if maximum_error > 1e-12 or len(metrics) != len(queries) * len(METHODS):
        raise ValueError("報告指標重算失敗。")

    coverage = read_csv(MAIN / "reference_coverage.csv")
    normal = read_csv(MAIN / "normalization.csv")
    if len(normal) != 50 or any(r["same_ranking"] != "True" for r in normal):
        raise ValueError("L2 等價性未通過。")
    maximum_normal_error = max(float(r["max_score_difference"]) for r in normal)
    documents, snapshot = load_corpus(ROOT / "data/corpus/glp1-3000-20261015")
    if snapshot["sha256"] != manifest["corpus_sha256"]:
        raise ValueError("語料版本不符。")
    engine = Engine(documents, Settings("C", "standard"))
    q01 = queries[0]["text"]
    example_id = by_rank["Q01", "tfidf"][0]["pmid"]
    explanation = engine.explain(q01, example_id, "tfidf")
    for method in METHODS:
        actual = engine.rank(q01, method, limit=10)
        saved = by_rank["Q01", method][:10]
        if [r["pmid"] for r in actual] != [r["pmid"] for r in saved]:
            raise ValueError("Q01 重算排名與保存結果不同。")
        if any(abs(a["score"] - float(s["score"])) > 1e-12 for a, s in zip(actual, saved)):
            raise ValueError("Q01 重算分數不同。")
    raw = engine.rank(q01, "tfidf", scoring="dot", limit=None)
    cosine = engine.rank(q01, "tfidf", limit=None)
    normalized_dot = engine.rank(q01, "tfidf", scoring="dot", normalize=True, limit=None)
    raw_map = {r["pmid"]: r for r in raw}
    cosine_map = {r["pmid"]: r for r in cosine}
    normalized_map = {r["pmid"]: r for r in normalized_dot}
    selected = list(dict.fromkeys(r["pmid"] for r in raw[:3] + cosine[:3]))
    _, norms = engine.vectors("tfidf")
    dot_rows = [{"pmid": pid, "tokens_C": sum(engine.counts[pid].values()), "vector_norm": norms[pid],
                 "raw_dot_rank": raw_map[pid]["rank"], "raw_dot": raw_map[pid]["score"],
                 "cosine_rank": cosine_map[pid]["rank"], "cosine": cosine_map[pid]["score"],
                 "normalized_dot": normalized_map[pid]["score"]} for pid in selected]
    metadata_positive = sum(int(r["metadata_positive"]) for r in coverage)
    fallback_positive = sum(int(r["fallback_positive"]) for r in coverage)
    positives = metadata_positive + fallback_positive
    fallback_count = sum(int(r["weak_fallback"]) for r in coverage)
    added = sum(int(r["metadata_additions_over_weak"]) for r in coverage)
    values = {(r["qid"], r["method"]): r for r in metrics}
    per_query = [[q["qid"], *[f"{float(values[q['qid'], m]['precision_at_k']):.2f}" for m in METHODS]] for q in queries]
    per_ndcg = [[q["qid"], *[f"{float(values[q['qid'], m]['ndcg_at_k']):.4f}" for m in METHODS]] for q in queries]
    link = lambda path: Path(os.path.relpath(path, report.parent)).as_posix()
    label_name = {"pubmed_metadata": "PubMed 主題依據", "weak_rules_fallback": "weak rule 回退"}
    metadata_counts = manifest["reference_provenance"]["counts"]

    chunks = [r"""# 生醫資訊檢索第三次作業報告

## 摘要

本研究以固定的 3,000 篇 GLP-1 英文 PubMed 摘要，實作原始 TF、Log TF、IDF-only、TF-IDF 與 Log TF-IDF 的向量空間檢索，固定前處理與 IDF 定義，比較十個查詢的排名及評估指標。@@BM25_ABSTRACT@@相關集合採用 PubMed 主題資料與摘要 weak rule 建立的自動參考標籤，未進行獨立人工相關性驗證。

@@ABSTRACT_RESULTS@@

報告日期為 2026/10/16；作業截止日期為 2026/10/27。

## 1 研究目的與作業範圍

本作業探討詞頻、文件頻率與向量長度如何影響搜尋排名，並用可重現的實驗回答 RQ1～RQ5。原題任務五允許在缺乏既有相關性標籤時，根據文件主題標籤或人工判讀建立簡單相關集合並說明限制。本研究採自動主題參考方案；摘要 weak rule 是額外的詞彙代理判準，於方法與限制中單獨揭露，沒有將其視為人工真值。

系統維持四頁：語料與設定、搜尋與排名、方法比較、效能評估。文件以 PMID 識別，僅摘要正文參與計分，標題供閱讀。介面提供前十名及分數、摘要命中高亮、逐詞權重貢獻、來源分流、實驗保存與歷史查核。HW3 使用獨立環境；HW2 原始成品維持唯讀。

## 2 固定語料與前處理

語料保留原 1,000 篇，於 2026/10/15 以相同 PubMed 搜尋條件增加 2,000 篇，限制英文、非空摘要與 PMID 去重。出版日期搜尋截止仍為 2026/09/29。新增階段取得 2,100 筆原始紀錄，排除 11 筆書籍類紀錄及 15 筆空摘要，另有 74 筆合格但未納入。這是保留舊快照後的擴充聯集，不是隨機樣本，也不是當日查詢純粹的前 3,000 名。原始 XML、搜尋回應、排除理由及 SHA256 均保存。

PubMed 出版日期搜尋涵蓋電子與紙本日期。快照中兩筆期刊卷期年份為 2027、電子出版日期在查詢期間內；文件年份保留卷期年份，不以該欄另做人工日期篩選。

```text
@@CORPUS_QUERY@@
```

本版的 Log TF 與 IDF 統一使用 log10，與先前 ln 版本分開保存；[原 ln 報告](HW3_REPORT.md)保留原數字與指紋。nDCG 的排名折扣仍使用 log₂。標準 IDF 的改底數是整體常數縮放，對相同非零向量的 cosine 理論上抵消；Log TF 的加一使改底數不再只是整體縮放，排名須重新實驗。

本實驗共 3,000 篇，C 前處理後有 539,158 個 tokens、31,662 個不同詞項。支援 B（切詞與文字正規化）、C（B 加停用詞移除）、D（C 加 Porter）；本文實驗全部固定 C。DF 是包含詞項的文件數，CF 是全語料出現次數，TF 是單篇文件或單一查詢的實際次數，三者不混用。

## 3 向量權重與控制條件

令 f 為某詞在文件或查詢中的次數，N=3,000，DF(t) 為包含 t 的文件數。f=0 時以下權重皆為零；f>0 時：

| 方法 | 權重 |
| --- | --- |
| 原始 TF | f |
| Log TF | 1 + log10(f) |
| IDF-only | IDF(t)，只記出現，不使用重複次數 |
| TF-IDF | f × IDF(t) |
| Log TF-IDF | (1 + log10(f)) × IDF(t) |

標準 IDF 為 `log10(N / DF)`；平滑選項為 `log10((N+1)/(DF+1)) + 1`。本文使用標準式，沒有將平滑 IDF 或 B／D 設定的效果混入五方法比較。

文件與查詢使用同一詞彙空間、前處理、IDF 及 weighting；查詢重複詞保留實際 TF，OOV 不加入向量與 norm。分數為 `cos(q,d) = Σt w(t,q)w(t,d) / (||q||₂ ||d||₂)`；文件 norm 使用完整文件向量，不只計算命中詞。空白、全停用詞、全 OOV 或零向量安全返回無結果，不以零分文件湊滿十篇。

原五種向量方法固定同一語料、十查詢、同一參考標籤、C、標準 IDF、cosine 與 k=10，主要比較因素為 weighting。第六種 BM25 共用語料、查詢、標籤、C 與 k，計分模型另依下節明列。排序先依分數取 12 位小數降序，再依數字 PMID 升序處理同分；畫面顯示 6 位小數，CSV 保存原始精度。不同方法的分數尺度不能直接當作相關性強弱或正確率比較。

@@BM25_SECTION@@

## 4 查詢與自動參考標籤

### 4.1 十個資訊需求

@@QUERY_TABLE@@

研究範圍不額外排除人體、動物或細胞研究；自動規則沒有逐篇確認研究類型、設計或臨床適用性。全文也沒有納入計分或相關性裁決。

### 4.2 PubMed 主題依據

從每篇保存的 exact raw_path XML 依 PMID 抽取 MeSH DescriptorName、ChemicalList 的 NameOfSubstance、SupplMeshName 與 Keyword，並核對原始 XML SHA256。MeSH UI、主題重要性標記、qualifier、文章類型及標引狀態供追溯；qualifier 和文章類型不獨立參與概念命中，MajorTopic 不自動轉成高度相關。MeSH 與關鍵字的欄位意義依 [NLM PubMed 說明](https://pubmed.ncbi.nlm.nih.gov/help/#mesh-terms-mh)，查詢與標籤的對應則是本專案規則，並非 NLM 的查詢答案。MeSH 也不能一律稱為人工專家標註。

每個查詢有兩組概念；組內採 OR、組間採 AND。同一文章允許分別從不同主題欄位支持兩組概念，全部命中時給 grade=1、來源 pubmed_metadata。字串採 NFKC、casefold、標點與連字號轉空白後的完整詞序列比對，不做 MeSH 階層展開、線上翻譯或隱含同義詞推理。Q04～Q10 的共享概念組明列 GLP-1、受體／致效劑及若干藥名，不包含單獨 glucagon 或 GLP-2。完整固定別名列於附錄 A。

### 4.3 摘要 weak rule 回退

當主題欄位完全缺少，或存在但不足以支持該查詢全部概念組時，獨立套用摘要 weak rule。回退不將部分主題命中與部分摘要命中拼成正例；摘要本身須支持全部概念組才為 1，否則為 0。規則直接檢查正規化原摘要，不使用檢索的停用詞設定、Porter、TF、DF、分數或排名。英文 casefold，少數彎引號／連字號統一，完整詞／詞組邊界匹配；僅 neuroprotect 與 neurodegenerat 允許已明列的字尾延伸。

@@WEAK_TABLE@@

上表的 G 指 `glp-1`、`glucagon-like peptide-1`、`glucagon-like peptide 1`。weak rule 的 G 不會因只出現 semaglutide 等藥名就自動成立，與較寬的 metadata 別名組不同。`*` 是對該兩個指定前綴的說明符號，不是所有詞都做詞幹擴展。

例如 Q01 必須同時出現 semaglutide，以及 weight loss／weight reduction／obesity／obese 中至少一詞。這是詞面共現，不保證主要研究問題是 semaglutide 減重。系統逐筆保存來源、命中詞、metadata 證據、回退原因及原 weak_rule_grade；0 表示規則證據不足，不能稱為人工確認不相關。全程只產生自動二元 0／1，沒有自動等級 2，也沒有新增人工判讀。

### 4.4 實際涵蓋與標籤來源

@@METADATA_COUNTS@@

各欄位篇數可重疊。有任何主題資料的 2,846 篇不代表對每個查詢都有足夠依據；完全沒有主題資料的文章為 154 篇。以下以「查詢－文章」為單位，不能解讀成互不重複的文章數：

@@COVERAGE_TABLE@@

@@COVERAGE_TOTAL@@

每個查詢都有 3,000 筆自動結果。沒有主題欄位造成的回退每查詢均為 154 筆，其餘回退是概念支持不足。人工標註完成數為 0；30,000 筆規則結果與人工判讀進度完全不同。

## 5 評估方法

令 Rq 為參考標籤為 1 的文件集合，Top10 為前十名；相關一詞在本節僅指此自動參考。P@10=`|Top10 ∩ Rq|/10`，即使結果不足十篇分母仍固定為十。參考 Recall@10=`|Top10 ∩ Rq|/|Rq|`，分母不是已完整人工判讀的真實相關集合。

每查詢 RR 為完整非零返回排名中第一個參考正例的倒數名次，沒有正例則為零；MRR 為十查詢 RR 平均，不限於前十名。DCG@10 使用 `Σi (2^grade_i−1)/log₂(i+1)`，nDCG 為 DCG 除以依全部參考標籤排出的 IDCG；目前 grade 只有 0／1，故是二元 nDCG，沒有利用人工相關程度。評估依資訊需求與相關集合進行，與單純包含查詢詞不同，見 [IR 評估原理](https://nlp.stanford.edu/IR-book/html/htmledition/information-retrieval-system-evaluation-1.html)與[排名評估](https://nlp.stanford.edu/IR-book/html/htmledition/evaluation-of-ranked-retrieval-results-1.html)。

平均採查詢等權的 macro mean；每查詢至少有一個參考正例才納入。本文固定十查詢全部有正例，因此實際納入 10／10、排除 0，沒有以少數查詢冒充全部。judged@10 均為 1，只表示前十名都有自動規則結果，不表示人工覆蓋率為 100%。@@METRIC_ROWS@@ 組結果的完整指標見附錄 B。

## 6 實驗結果

### 6.1 @@METHOD_COUNT@@ 種方法平均

@@SUMMARY_TABLE@@

@@SUMMARY_RESULTS@@

Recall@10 約 0.03～0.05 不代表程式漏掉 95% 的真實相關文章：每查詢參考正例有 101～770 筆，前十名最多只取十筆。且 macro Recall 先按每查詢的不同分母計算，再平均，不能由平均 P@10 直接換算。

### 6.2 逐查詢 P@10 與 nDCG@10

@@PER_QUERY_P@@

@@PER_QUERY_N@@

@@QUERY_RESULTS@@

### 6.3 標籤來源敏感度

@@SENSITIVITY_TABLE@@

此表固定完整排名、查詢、語料、程式與設定，只改評估參考來源，故是標籤敏感度分析，不是搜尋演算法改善實驗。混合規則較純 weak rule 多 184 組正例，且不移除原 weak 正例；所有方法的排名檔逐位元相同。所有查詢正例均超過十筆，二元 IDCG@10 不變，新增命中的參考正例即可提高 P@10／nDCG@10，不能將分數增加解讀為更接近人工真值。Recall 則還會受到正例分母增加的影響。

@@SOURCE_RESULTS@@

## 7 RQ1～RQ5 實驗結論

### RQ1 原始 TF 與 Log TF 如何影響權重

原始 TF 隨出現次數線性增加，Log TF 在 f>0 時以 1+log10(f) 壓縮重複。以 Q01 的 TF-IDF 第一名 PMID @@EXAMPLE_ID@@ 為例，文件標題為「@@EXAMPLE_TITLE@@」。其實際摘要詞項如下：

@@TERM_EXAMPLE@@

loss 與 semaglutide 的原始 TF 比值為 21/6=3.50，Log TF 比值約為 @@TF_RATIO@@；重複較多的 loss 因此不再保有原來的相對倍數。權重壓縮不保證每篇分數都下降或每個查詢改善，因為 cosine 的分子與完整文件 norm 都會改變。

@@RQ1_RESULTS@@

### RQ2 IDF 為何能降低常見詞的重要性

在固定 N 下，標準 IDF=log10(N/DF)，DF 越大，單詞權重越低。高文件頻率表示區辨文件的能力較弱，不代表該詞在醫學上不重要。以實際集合統計代入：

@@IDF_EXAMPLE@@

上表的平滑值僅為同一 DF 的公式代入，沒有新增平滑 IDF 排名實驗。當 DF=N 時，標準 IDF 為零，平滑式為一。文件與查詢都使用 IDF 時，未正規化點積中的單詞乘積含 IDF²，最後仍由兩向量 norm 調整；不能只看單詞 IDF 就斷言最終排名。

@@RQ2_RESULTS@@

### RQ3 TF-IDF 相較 TF-only 與 IDF-only 的排名表現

@@RQ3_RESULTS@@

以固定 Q01 的實際 Top 10 比較：

@@Q01_TOP10@@

@@Q01_RESULTS@@

Q01 TF-IDF 十篇的分數、標題與參考來源列於附錄 C。以上是可查核的排名差異與規則符合程度，不是逐篇人工內容評鑑。

### RQ4 L2 normalization 前後有何差異

對非零向量，令 q̂=q/||q||₂、d̂=d/||d||₂，則 `cos(q,d)=q̂·d̂=cos(q̂,d̂)`。標準 cosine 本來就除以向量長度，顯式 L2 前後應理論等價。固定五方法、十查詢的 50 組檢查全部排名一致，最大分數差為 @@NORMAL_ERROR@@，屬浮點運算差異。這不是 L2 沒有作用，而是比較的兩邊已經具有相同長度校正。

另外以 Q01、TF-IDF 比較 raw dot 與 normalized dot，選兩種排序各前三名聯集作補充：

@@DOT_EXAMPLE@@

raw dot 沒有除以 norm，normalized dot 等於 cosine；兩者是不同 scoring，分數尺度不可直接比較。表中 token 數與 norm 顯示文件長度及權重組成不同；這個例子不能單獨分離字數與詞項分布的因果效果，也不把 raw dot 當作第六種 weighting 納入主要品質比較。

### RQ5 不同 weighting 對評估指標有何影響

@@RQ5_RESULTS@@

@@RQ5_DIFFERENCE@@本研究只有十個固定查詢，沒有顯著性檢定或獨立人工效度證據，故此差距僅作描述性結果。若使用情境重視前十名比例、第一個可用結果或整體前十排序，應分別看 P@10、MRR、nDCG；不能只選對某方法最有利的指標。這些適用性判斷限於本資料與規則代理任務。

## 8 偏差與限制

1. **詞彙共同訊號。** weak rule 與本次詞項檢索方法共享字詞訊號，容易偏好明列詞表的文件。標籤不讀排名可避免直接由排名反推答案，仍不能消除參考標準對詞彙搜尋的偏向。所有比較法皆依賴詞彙訊號，結果不能推論到未測試的模型；BM25 也無法消除這類參考偏差。
2. **主題共現不等於資訊需求成立。** 背景提及、不同藥物與不同終點同時出現、研究計畫或次要討論都可能命中；系統沒有抽取關係或判定研究焦點。負面療效研究本身仍可能與查詢相關，不應將「沒有效果」一概當作不相關。Q03 的糖尿病標籤不保證第二型或血糖控制，Q04／Q05 的疾病與器官詞不證實保護效果。
3. **有限詞表造成漏判。** 同義詞、變形、縮寫與隱含概念未必涵蓋；完整邊界與 metadata 正規化也無法取代語義理解。缺少標引不代表不相關，weak 0 也不是人工負例。
4. **欄位來源不均。** MeSH、化學物質、補充概念與作者／供應者關鍵字的完整性與產生方式不同，不能把全部 metadata 一律稱為人工專家判讀。主題欄位 94.9% 的篇數涵蓋，不等於任一查詢有相同比例的有效相關性證據。
5. **混合來源與二元標籤。** 正例多數來自 weak 回退；兩類正例聯集可能增加指標，並不等於標籤更準確。二元 nDCG 不能反映高度與部分相關的差異，judged@10=1 也不是人工驗證。
6. **語料、查詢與摘要範圍。** 單一 GLP-1 主題、保留舊資料的非隨機擴充、十個固定查詢與摘要正文限制外推；不能視為完整 PubMed 或全文檢索表現。未讀取全文確認研究設計或療效。
7. **Recall 與人工驗證。** 全 30,000 組都執行過規則，只能證明規則覆蓋完整，不能證明真實相關集合完整。本報告沒有獨立人工驗證。人工候選池各方法 Top 20 聯集仍可供未來查核，但未在本研究當作人工答案；若之後判讀候選池，須保留池外補查與 pooling bias 的說明。

## 9 重現與可靠性

### 9.1 本報告引用的實驗

@@RUN_TABLE@@

主實驗與重複實驗的 15 個輸出逐位元一致。純 weak 對照與主實驗使用相同語料、查詢、程式、weighting、設定與完整排名，只有參考標籤不同。原 run 保持不變，文件更新不回寫其 manifest。每個 manifest 保存當時程式、規則、資料、環境與輸出 hash；資料指紋的 canonical JSON 與檔案位元組 SHA256 定義不同，不能混用。

@@HASH_TABLE@@

@@SOURCE_LINKS@@

### 9.2 數值核對的範圍

@@TEST_RESULTS@@

@@NUMERIC_RESULTS@@

本報告再對保存排名與標籤獨立重算 @@METRIC_ROWS@@ 組指標及 @@METHOD_COUNT@@ 方法平均、核對所有輸出 hash，並以目前相同計分程式重算 Q01 Top 10、詞項及 raw dot 補充例子。衍生資料與核對結果位於本報告附件，這些檢查均未新增人工標籤。

### 9.3 操作與重現指令

```powershell
Set-Location -LiteralPath 'C:\成大專案\IR-HW3'
& '.\.venv\Scripts\python.exe' -B -X utf8 -m ir_hw3.cli verify
& '.\.venv\Scripts\python.exe' -B -X utf8 -m ir_hw3.cli verify --source
& '.\.venv\Scripts\python.exe' -B -X utf8 scripts\verify_hw3.py
& '.\.venv\Scripts\python.exe' -B -X utf8 -m ir_hw3.cli experiment --source pubmed
& '.\.venv\Scripts\python.exe' -B -X utf8 scripts\evaluate_pubmed_reference.py
# 從本報告固定的歷史 run 重建文字與附件；新位置避免覆寫本報告
& '.\.venv\Scripts\python.exe' -B -X utf8 scripts\build_hw3_report.py --analysis @@ANALYSIS_PATH@@ --report reports\reproduced\HW3_REPORT_BM25.md
```

PubMed 自動參考與 weak rule 實驗使用獨立 run 目錄，不覆寫 human 或歷史輸出。重跑 evaluate_pubmed_reference 會新增實驗，時間／run_id 可以不同；應核對語料、查詢、標籤、設定及輸出，不以新 run_id 當作結果改變。重建本報告的腳本固定引用上列歷史 run，並拒絕覆寫已存在的報告。

環境為 Python 3.12.14；主要依賴為 Streamlit 1.66.0、NumPy 2.5.4、pandas 3.0.6、NLTK 3.9.2、regex 2026.9.29、Altair 6.3.0、defusedxml 0.7.1，依實驗 manifest 記錄。HW3 使用自己的 .venv；不依賴 HW2 的執行環境。來源摘要可能有著作權，不宣稱全部是開放授權。

## 10 操作展示與結論

展示約六分鐘：先在語料與設定說明固定 3,000 篇、C、標準 IDF 與 TF／DF／CF；接著搜尋 Q01，查看 Top 10、原摘要與逐詞權重；在方法比較固定查詢切換 weighting，說明排名改變與 L2 等價。最後於效能評估選「PubMed 主題參考＋弱規則回退」、k=10，展示十查詢納入數、來源涵蓋、逐筆依據與並排 0～1 指標圖，再指向獨立 run、完整報告與來源敏感度對照。人工頁保留其實際進度，不為 demo 虛填人工等級。

此實驗顯示詞頻壓縮與 IDF 會改變排名及對自動參考集合的符合程度；標準 cosine 的顯式 L2 前後保持等價。@@SUMMARY_RESULTS@@ 結論應同時依查詢、指標與標籤來源解讀，不能將某次平均勝出視為普遍優越，更不能將此自動參考評估寫成已經人工驗證。

## 附錄 A 完整 metadata 別名與判據

共享 Gm 的完整別名：@@SHARED_GROUP@@。

@@METADATA_RULES@@

組內 OR、組間 AND；文字正規化、允許欄位與回退規則依第 4 節。下列固定 JSON 及原 run 的副本是可機器重現的規則來源，不採線上自動映射。

## 附錄 B @@METHOD_COUNT@@ 種方法十查詢完整指標

@@ALL_METRICS@@

RR 是單一查詢的 reciprocal rank；前述 MRR 為這些 RR 的平均。參考標籤全覆蓋，因此各列 judged@10 皆為 1，沒有宣稱人工已完成。

## 附錄 C Q01 的 TF-IDF 前十名與標籤來源

@@TOP_TITLES@@

逐筆參考來源與判定依據：

@@TOP_EVIDENCE@@

標題為閱讀資訊，未加入檢索向量；來源與理由來自自動規則保存紀錄，不是本報告作者對各篇內容的人工裁決。前十名以外的完整非零排名、全部 30,000 筆標籤、來源比例與原始 metadata 另附於主 run。

## 參考資料

1. [作業原題 Homework 3](../docs/Homework-3.pdf)，完整兩頁，任務五及 RQ1～RQ5。
2. NLM，[PubMed MeSH Terms](https://pubmed.ncbi.nlm.nih.gov/help/#mesh-terms-mh) 與 [Other Term](https://pubmed.ncbi.nlm.nih.gov/help/#other-term-ot)，欄位意義與限制；查閱日期 2026/10/16。
3. Manning, Raghavan, Schütze，[Information retrieval system evaluation](https://nlp.stanford.edu/IR-book/html/htmledition/information-retrieval-system-evaluation-1.html)，相關性依資訊需求判定。
4. 同書，[Evaluation of ranked retrieval results](https://nlp.stanford.edu/IR-book/html/htmledition/evaluation-of-ranked-retrieval-results-1.html)，排名評估指標。
"""]
    replacements = {
        "CORPUS_QUERY": snapshot["query"],
        "QUERY_TABLE": table(["查詢", "搜尋文字", "資訊需求"], [[q["qid"], q["text"], q["intent"]] for q in queries]),
        "WEAK_TABLE": table(["查詢", "摘要概念組一", "摘要概念組二 任一詞"],
                            [[q["qid"], "G" if i >= 3 else "、".join(q["groups"][0]),
                              "、".join(t + ("*" if t in {"neuroprotect", "neurodegenerat"} else "") for t in q["groups"][1])]
                             for i, q in enumerate(queries)]),
        "METADATA_COUNTS": table(["主題欄位", "有該欄位的篇數"], [[name, metadata_counts[key]] for name, key in
                                  [("MeSH", "mesh"), ("藥物／化學物質", "chemical"), ("補充概念", "supplementary_concept"),
                                   ("關鍵字", "keyword"), ("任一主題欄位", "any_topic_metadata")]]),
        "COVERAGE_TABLE": table(["查詢", "metadata 正例", "weak 回退筆數", "回退正例", "參考正例總數", "較純 weak 新增正例"],
                                [[r[k] for k in ["qid", "metadata_positive", "weak_fallback", "fallback_positive", "rule_relevant", "metadata_additions_over_weak"]] for r in coverage]),
        "COVERAGE_TOTAL": f"總計 30,000 組中，{metadata_positive:,} 組由 metadata 給正例，{fallback_count:,} 組（{fallback_count/30000:.1%}）走摘要回退；其中 {fallback_positive:,} 組為回退正例。參考正例合計 {positives:,} 組，回退正例占 {fallback_positive/positives:.1%}。metadata 比純 weak 多 {added} 組正例。",
        "SUMMARY_TABLE": table(["方法", "P@10", "參考 Recall@10", "MRR", "二元 nDCG@10"],
                               [[METHODS[r["method"]], *[f"{float(r[k]):.4f}" for k in ["precision_at_k", "recall_at_k", "reciprocal_rank", "ndcg_at_k"]]] for r in summary]),
        "PER_QUERY_P": "逐查詢 P@10：\n\n" + table(["查詢", *METHODS.values()], per_query),
        "PER_QUERY_N": "逐查詢 nDCG@10：\n\n" + table(["查詢", *METHODS.values()], per_ndcg),
        "SENSITIVITY_TABLE": table(["方法", "混合 P@10", "純 weak P@10", "混合 nDCG@10", "純 weak nDCG@10"],
                                   [[METHODS[r["method"]], f"{float(r['precision_at_k']):.4f}", f"{float(weak_summary[r['method']]['precision_at_k']):.4f}",
                                     f"{float(r['ndcg_at_k']):.4f}", f"{float(weak_summary[r['method']]['ndcg_at_k']):.4f}"] for r in summary]),
        "EXAMPLE_ID": example_id, "EXAMPLE_TITLE": documents[example_id].title,
        "TERM_EXAMPLE": table(["詞項", "文件 TF", "Log TF", "DF", "標準 IDF", "TF-IDF", "cosine 貢獻"],
                              [[r["term"], r["document_tf"], f"{1+math.log10(r['document_tf']) if r['document_tf'] else 0:.4f}", r["df"],
                                f"{r['idf']:.4f}", f"{r['document_weight']:.4f}", f"{r['cosine_contribution']:.6f}"] for r in explanation]),
        "IDF_EXAMPLE": table(["詞項", "CF", "DF", "標準 IDF", "平滑 IDF 公式代入"],
                             [[t, engine.cf[t], engine.df[t], f"{engine.idf[t]:.4f}", f"{math.log10((engine.n+1)/(engine.df[t]+1))+1:.4f}"]
                              for t in ["glp-1", "weight", "semaglutide"]]),
        "Q01_TOP10": table(["名次", *METHODS.values()], [[i+1, *[by_rank["Q01", m][i]["pmid"] for m in METHODS]] for i in range(10)]),
        "NORMAL_ERROR": f"{maximum_normal_error:.16g}",
        "DOT_EXAMPLE": table(["PMID", "C tokens", "文件 norm", "raw dot 名次", "raw dot", "cosine 名次", "cosine／normalized dot"],
                             [[r["pmid"], r["tokens_C"], f"{r['vector_norm']:.4f}", r["raw_dot_rank"], f"{r['raw_dot']:.4f}", r["cosine_rank"], f"{r['cosine']:.6f}"] for r in dot_rows]),
        "RUN_TABLE": table(["用途", "來源", "run_id", "manifest SHA256"],
                           [[name, m["judgment_source"], m["run_id"], sha(d / "manifest.json")] for name, d, m in zip(["主要混合實驗", "獨立重複", "同排名純 weak 對照"], [MAIN, REPEAT, WEAK], manifests)]),
        "HASH_TABLE": table(["內容", "指紋定義", "SHA256"], [["語料 abstracts.jsonl", "檔案位元組", manifest["corpus_sha256"]],
                           ["查詢", "canonical JSON", manifest["queries_sha256"]], ["參考標籤及來源", "canonical JSON", manifest["judgments_sha256"]],
                           ["規則", "canonical JSON", manifest["reference_provenance"]["rules_sha256"]], ["原始 metadata", "canonical JSON", manifest["reference_provenance"]["metadata_sha256"]]]),
        "SOURCE_LINKS": "資料入口：[主實驗 manifest](" + link(MAIN / "manifest.json") + ")、[平均指標](" + link(MAIN / "metrics_summary.csv") + ")、[逐查詢指標](" + link(MAIN / "metrics_per_query.csv") + ")、[全部參考標籤與理由](" + link(MAIN / "reference_labels.csv") + ")、[來源涵蓋](" + link(MAIN / "reference_coverage.csv") + ")、[Top k 來源](" + link(MAIN / "reference_topk_sources.csv") + ")、[完整規則副本](" + link(MAIN / "reference_rules.json") + ")、[PubMed metadata](" + link(MAIN / "pubmed_metadata.json") + ")。",
        "SHARED_GROUP": "、".join(rules["shared_groups"]["glp1"]),
        "METADATA_RULES": table(["查詢", "metadata 概念組一", "metadata 概念組二 任一詞"],
                                [[q["qid"], "Gm" if isinstance(rules["queries"][q["qid"]]["groups"][0], str) else "、".join(rules["queries"][q["qid"]]["groups"][0]),
                                  "、".join(rules["queries"][q["qid"]]["groups"][1])] for q in queries]),
        "ALL_METRICS": table(["查詢", "方法", "P@10", "參考 Recall@10", "RR", "nDCG@10"],
                             [[q["qid"], METHODS[m], *[f"{float(values[q['qid'], m][k]):.4f}" for k in ["precision_at_k", "recall_at_k", "reciprocal_rank", "ndcg_at_k"]]] for q in queries for m in METHODS]),
        "TOP_TITLES": table(["名次", "PMID", "cosine", "標題"],
                            [[r["rank"], r["pmid"], f"{float(r['score']):.6f}", r["title"]] for r in by_rank["Q01", "tfidf"][:10]]),
        "TOP_EVIDENCE": table(["PMID", "參考等級", "來源", "規則理由"],
                              [[r["pmid"], data["judgments"]["Q01"][r["pmid"]]["grade"],
                                label_name[data["judgments"]["Q01"][r["pmid"]]["label_source"]], data["judgments"]["Q01"][r["pmid"]]["reason"]] for r in by_rank["Q01", "tfidf"][:10]]),
    }
    summary_by_method = {r["method"]: r for r in summary}
    def score(method, key, source=None):
        return float((source or summary_by_method)[method][key])
    def best(source, key):
        highest = max(float(r[key]) for r in source.values())
        return "、".join(METHODS[m] for m in METHODS if abs(float(source[m][key])-highest) < 1e-12)
    def avg_description(source):
        return (f"P@10 最高為 {best(source, 'precision_at_k')}；nDCG@10 最高為 {best(source, 'ndcg_at_k')}。"
                f"TF-IDF 的 MRR={score('tfidf', 'reciprocal_rank', source):.4f}，Log TF-IDF 的 MRR={score('log_tfidf', 'reciprocal_rank', source):.4f}。")
    metric = lambda m,k: f"{score(m,k):.4f}"
    query_descriptions = []
    perfect_queries = [q["qid"] for q in queries
                       if all(float(values[q["qid"], m]["precision_at_k"]) == 1 for m in METHODS)]
    for qid in ("Q02", "Q03", "Q08"):
        observations = "；".join(f"{METHODS[m]} 的 P@10={float(values[qid,m]['precision_at_k']):.2f}、nDCG@10={float(values[qid,m]['ndcg_at_k']):.4f}" for m in ("log_tf", "tfidf", "log_tfidf"))
        query_descriptions.append(f"{qid}：{observations}。")
    import xml.etree.ElementTree as ET
    test_suites = ET.parse(ROOT / "reports/pytest.xml").getroot()
    suites = [test_suites] if test_suites.tag == "testsuite" else list(test_suites.iter("testsuite"))
    test_count = sum(int(x.attrib.get("tests", 0)) for x in suites)
    if any(int(x.attrib.get(k,0)) for x in suites for k in ("failures", "errors")):
        raise ValueError("完整測試有失敗，不能產生通過宣告。")
    numeric = read_json(ROOT / "reports/verification.json")
    if numeric.get("logarithm_base") != LOGARITHM_BASE or len(numeric.get("settings_checked", [])) != 6:
        raise ValueError("必須先通過 log10 六設定數值驗證。")
    replacements.update({
        "ABSTRACT_RESULTS": "在 C 前處理、log10 的標準 IDF 與 Log TF、cosine 與 k=10 下，" + avg_description(summary_by_method) + "這些數字衡量對規則參考集合的符合程度。" + "純 weak 對照的 nDCG@10 最高為 " + best(weak_summary, "ndcg_at_k") + "，方法結論須同時考慮標籤來源，不能宣稱普遍最佳。",
        "SUMMARY_RESULTS": avg_description(summary_by_method) + "不同指標各自比較，不相加或疊加。",
        "QUERY_RESULTS": ("、".join(perfect_queries) + " 的各方法 P@10 均為 1，表示前十名都符合自動參考，不能據此推論各方法排序相同或都已回答醫學問題。" if perfect_queries else "沒有查詢在各方法中同時取得 P@10=1。") + "\n\n" + "\n\n".join(query_descriptions) + "總平均不能代替逐查詢分析。",
        "SOURCE_RESULTS": "純 weak 下 nDCG@10 最高為 " + best(weak_summary, "ndcg_at_k") + "；混合來源最高為 " + best(summary_by_method, "ndcg_at_k") + "。來源可能改變絕對分數或相對名次，不能反過來證明任何一套標籤比較正確。",
        "TF_RATIO": f"{(1+math.log10(21))/(1+math.log10(6)):.2f}",
        "RQ1_RESULTS": f"TF 改 Log TF，平均 P@10 從 {metric('tf','precision_at_k')} 變為 {metric('log_tf','precision_at_k')}，nDCG@10 從 {metric('tf','ndcg_at_k')} 變為 {metric('log_tf','ndcg_at_k')}。逐查詢結果見第 6 節，不能將平均變化視為所有查詢均改善。",
        "RQ2_RESULTS": f"相同原始 TF 下，加入 IDF 後平均 P@10 從 {metric('tf','precision_at_k')}（TF）變為 {metric('tfidf','precision_at_k')}（TF-IDF），nDCG@10 從 {metric('tf','ndcg_at_k')} 變為 {metric('tfidf','ndcg_at_k')}。這是本控制設定與規則參考下的描述結果，不代表醫學重要性。",
        "RQ3_RESULTS": f"TF-IDF 結合重複次數與集合區辨力；IDF-only 忽略文件內重複。TF-IDF 的 P@10={metric('tfidf','precision_at_k')}、nDCG@10={metric('tfidf','ndcg_at_k')}、MRR={metric('tfidf','reciprocal_rank')}；IDF-only 分別為 {metric('idf','precision_at_k')}、{metric('idf','ndcg_at_k')}、{metric('idf','reciprocal_rank')}。各指標衡量不同面向，不能只憑單一指標宣稱普遍勝出。",
        "Q01_RESULTS": "各欄為 PMID，由上而下表示該方法的名次；不在某欄不代表整份排名未檢出。" + "；".join(f"{METHODS[m]} 第一名 PMID {by_rank['Q01',m][0]['pmid']}、P@10={float(values['Q01',m]['precision_at_k']):.2f}、nDCG@10={float(values['Q01',m]['ndcg_at_k']):.4f}" for m in METHODS) + "。",
        "RQ5_RESULTS": avg_description(summary_by_method) + "P@10 看前十名正例比例，MRR 只看第一個參考正例的名次，nDCG@10 同時反映前十名正例的位置，因此同一方法未必在各指標同時最佳。",
        "RQ5_DIFFERENCE": f"Log TF-IDF 減 TF-IDF 的平均 nDCG@10 差為 {score('log_tfidf','ndcg_at_k')-score('tfidf','ndcg_at_k'):+.4f}；差異方向與逐查詢結果、標籤來源都應一起解讀。",
        "TEST_RESULTS": f"log10 版完整測試共 {test_count} 項通過；舊 ln 版的測試紀錄保留，沒有把重跑數量加總。測試與重現性不構成人工相關性證據。",
        "NUMERIC_RESULTS": f"獨立 NumPy 核對 B／C／D × 標準／平滑 IDF 六設定，每設定 3,000×10×5=150,000 個分數，合計 {numeric['independent_cosine_scores_checked']:,} 個 cosine 分數；最大誤差 {numeric['maximum_cosine_error']:.16g}。主設定五方法十查詢的 L2 等價檢查通過。HW2 {numeric['hw2_source']['checked']} 個受保護檔案核對未改變。此擴大核對屬 log10 版本，不回寫成舊 ln 版已驗證六設定。",
        "ANALYSIS_PATH": str(analysis.relative_to(ROOT)),
    })
    replacements.update({
        "METHOD_COUNT": str(len(METHODS)), "METRIC_ROWS": str(len(metrics)),
        "BM25_ABSTRACT": "另加入第六種 BM25 作為獨立 scoring 模型，與原五方法使用相同語料、查詢及標籤。" if "bm25" in METHODS else "",
        "BM25_SECTION": ("### 3.1 第六種方法 BM25\n\n"
            + "BM25_IDF=`" + BM25_PARAMETERS["idf"] + "`；score=`" + BM25_FORMULA + "`。"
            + "固定 k1=1.2、b=0.75，未依本次參考標籤調參。dl 為前處理後摘要 token 數，avgdl 包含全部 N 篇；查詢 TF 線性累加，OOV 忽略。\n\n"
            + "BM25 使用自己的固定 IDF，不受側欄標準／平滑 IDF 影響，不做顯式 L2，不裁切分數至 0–1。"
            + "它改變了 TF 飽和、IDF、長度校正與 scoring，不能將與原五方法的差異僅歸因於 weighting。"
            + "下文的 cosine／L2 推導限原五種向量方法；六方法以相同標籤比較排名指標，原始分數不可直接比大小。"
            + "公式來源及完整契約見 [BM25 說明](" + link(ROOT / "docs/BM25.md") + ")。") if "bm25" in METHODS else "",
    })
    if "bm25" in METHODS:
        replacements["ABSTRACT_RESULTS"] = replacements["ABSTRACT_RESULTS"].replace("在 C 前處理、log10 的標準 IDF 與 Log TF、cosine 與 k=10 下，", "在 C 前處理與 k=10 下，原五方法使用 log10 與 cosine，BM25 使用獨立公式；")
        replacements["NUMERIC_RESULTS"] += (f" 第六種 BM25 另以 NumPy 核對 {numeric['independent_bm25_scores_checked']:,} 個分數，"
            f"最大誤差 {numeric['maximum_bm25_error']:.16g}；BM25 未納入 L2 等價檢查。")
    text = chunks[0]
    for key, value in replacements.items():
        text = text.replace("@@" + key + "@@", str(value))
    if re.search(r"@@[A-Z_]+@@", text):
        raise ValueError("報告仍有未填欄位。")
    if len(explanation) != 4 or engine.counts[example_id]["loss"] != 21 or engine.counts[example_id]["semaglutide"] != 6:
        raise ValueError("固定詞項例子已改變。")
    manual_after = {p.relative_to(ROOT).as_posix(): sha(p)
                    for p in (ROOT / "data/judgments").rglob("*.json")}
    if manual_after != manual_before:
        raise ValueError("人工檔案在報告建立期間有變更，請重新核對。")
    report.parent.mkdir(parents=True, exist_ok=True)
    assets.mkdir()
    write_csv(assets / "rq1_term_example.csv", explanation)
    write_csv(assets / "rq4_dot_example.csv", dot_rows)
    text += f"\n附件：[詞項明細]({link(assets / 'rq1_term_example.csv')})、[點積與長度對照]({link(assets / 'rq4_dot_example.csv')})、[報告來源與核對紀錄]({link(assets / 'audit.json')})。\n"
    # A reproduced report may live deeper in the repository.
    text = text.replace("(../docs/Homework-3.pdf)", "(" + link(ROOT / "docs/Homework-3.pdf") + ")")
    text = text.replace("(HW3_REPORT.md)", "(" + link(ROOT / "reports/HW3_REPORT.md") + ")")
    report.write_text(text, encoding="utf-8")
    for name in ["README.md", "docs/Homework-3.pdf", "data/corpus/glp1-3000-20261015/snapshot.json",
                 "scripts/build_hw3_report.py", "reports/verification.json", "reports/pytest.xml", "docs/BM25.md"]:
        inputs[name] = sha(ROOT / name)
    audit = {"report_sha256": sha(report), "input_sha256": inputs, "logarithm_base": LOGARITHM_BASE,
             "main_run": MAIN.relative_to(ROOT).as_posix(), "independently_recomputed_metric_rows": len(metrics),
             "maximum_metric_error": maximum_error, "normalization_checks": len(normal),
             "maximum_normalization_error": maximum_normal_error,
             "repeat_outputs_identical": True, "rankings_identical_across_reference_sources": True,
             "main_run_source_changes": changed_source, "manual_before": manual_before, "manual_after": manual_after,
             "metadata_positive_pairs": metadata_positive, "fallback_positive_pairs": fallback_positive,
             "all_positive_pairs": positives, "fallback_decision_pairs": fallback_count,
             "derived_outputs_sha256": {p.name: sha(p) for p in assets.iterdir() if p.is_file()}}
    (assets / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(report), "characters": len(text), "audit": str(assets / 'audit.json'),
                      "recomputed_metrics": len(metrics), "max_error": maximum_error}, ensure_ascii=False))


if __name__ == "__main__":
    main()
