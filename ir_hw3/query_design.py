"""Versioned TF/DF teaching queries; classification never reads ranking scores."""
from __future__ import annotations

import json
from pathlib import Path
from statistics import mean, median

from .core import terms
from .corpus import ROOT
from .evaluation import fingerprint

DESIGN_PATH = ROOT / "data/query_design/tfdf-v1.json"
VERSION = "tfdf-v1"
CASE_ORDER = [(1,), (2,), (3,), (4,), (1, 2), (1, 3), (1, 4), (2, 3), (2, 4), (3, 4)]


def load_design(queries: list[dict]) -> dict | None:
    versions = {q.get("design_version") for q in queries}
    if versions == {None}:
        return None
    if versions != {VERSION}:
        raise ValueError("查詢設計版本不一致或不支援。")
    design = json.loads(DESIGN_PATH.read_text(encoding="utf-8"))
    if design.get("queries_sha256") != fingerprint(queries):
        raise ValueError("TF/DF 查詢設計與查詢版本不符，請同步更新設計證據。")
    return design


def term_profile(engine, text: str) -> dict:
    processed = terms(text, engine.settings.condition)
    if len(processed) != 1:
        raise ValueError("代表詞必須在目前前處理下對應一個詞項。")
    term = processed[0]
    values = list(engine.postings.get(term, {}).values())
    return {"term": text, "indexed_term": term, "df": len(values),
            "df_fraction": len(values) / engine.n,
            "mean_positive_tf": mean(values) if values else 0,
            "median_positive_tf": median(values) if values else 0,
            "min_positive_tf": min(values) if values else 0,
            "max_positive_tf": max(values) if values else 0,
            "cf": sum(values), "idf": engine.idf.get(term, 0)}


def classify(profile: dict) -> str:
    tf = "高" if profile["mean_positive_tf"] >= 3 else "低" if profile["mean_positive_tf"] <= 1.6 else "中"
    df = "高" if profile["df_fraction"] >= 0.2 else "低" if profile["df_fraction"] <= 0.05 else "中"
    return f"{tf} TF／{df} DF"


def design_markdown(queries: list[dict], engine=None) -> str:
    design = load_design(queries)
    if design is None:
        return "此查詢集未使用 TF/DF 四類設計。"
    lines = ["四類代表詞＋六種兩兩搭配；分類基準為固定 3,000 篇、C 前處理。",
             "TF 是單篇文件詞頻；本表用『命中文件平均 TF』摘要分布，不以 CF 當作文件 TF。",
             "高 TF ≥3、低 TF ≤1.6；高 DF ≥20%、低 DF ≤5%。未命中文件不計入平均 TF，DF 則以全部文件為分母。", "",
             "| 類型 | 基準類別 | 代表詞 | DF | 命中文件平均 TF | TF 中位數 |",
             "|---|---|---|---:|---:|---:|"]
    for item in design["anchors"]:
        lines.append(f"| {item['type']} | {item['category']} | {item['term']} | {item['df']} | {item['mean_positive_tf']:.3f} | {item['median_positive_tf']:g} |")
    lines += ["", "| 查詢 | 圖中配置 | 預設文字 |", "|---|---|---|"]
    for query in queries:
        lines.append(f"| {query['qid']} | {query['case']} | {query['text']} |")
    if engine is not None and engine.settings.condition != "C":
        lines += ["", "目前已切換前處理，以上類別仍標示原 C 基準；實際詞頻與詞形依目前設定重新計算：", "",
                  "| 代表詞 | 當前詞形 | DF | 平均 TF | 當前分類 |", "|---|---|---:|---:|---|"]
        for item in design["anchors"]:
            row = term_profile(engine, item["term"])
            lines.append(f"| {item['term']} | {row['indexed_term']} | {row['df']} | {row['mean_positive_tf']:.3f} | {classify(row)} |")
    lines += ["", "配對查詢各含一個代表詞；查詢中每個詞只輸入一次。高／低 TF 描述語料中的分布，不保證每篇文件都相同。",
              "本設計沒有依評估分數選詞；自動相關標籤依公開概念規則另建，並非 TF 高低的人工判斷。"]
    return "\n".join(lines)


def build_design_report(analysis: Path, report: Path) -> dict:
    """Derive the new report from sealed runs; independently recalculate metrics."""
    import csv
    import math
    import os
    from .corpus import sha256

    def read(path):
        return json.loads(path.read_text(encoding="utf-8"))

    def rows(path):
        with path.open(encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))

    def table(headers, values):
        return "\n".join(["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"] +
                         ["| " + " | ".join(str(v).replace("|", "\\|") for v in row) + " |" for row in values])

    analysis, report = Path(analysis).resolve(), Path(report).resolve()
    if not analysis.is_relative_to(ROOT) or not report.is_relative_to(ROOT) or report.exists() or report.with_suffix(".audit.json").exists():
        raise ValueError("報告須另存 HW3 專案中的新檔案；保留既有成果。")
    evidence = read(analysis / "verification.json")
    directories = [Path(run["output"]).resolve() for run in evidence["runs"]]
    inputs, manifests = {}, []
    for directory in directories:
        if not directory.is_relative_to(ROOT):
            raise ValueError("實驗來源必須位於 HW3 專案內。")
        manifest = read(directory / "manifest.json")
        if manifest.get("status") != "complete":
            raise ValueError("不能引用未完成實驗。")
        for name, expected in manifest["outputs_sha256"].items():
            path = (directory / name).resolve()
            if not path.is_relative_to(directory) or sha256(path) != expected:
                raise ValueError("實驗輸出指紋不符。")
            inputs[path.relative_to(ROOT).as_posix()] = expected
        inputs[(directory / "manifest.json").relative_to(ROOT).as_posix()] = sha256(directory / "manifest.json")
        manifests.append(manifest)
    main, repeat, weak = directories
    config = manifests[0]
    if config.get("query_design_version") != VERSION or config["judgment_source"] != "pubmed_hybrid":
        raise ValueError("本報告僅適用 TF/DF 查詢的 PubMed 自動參考實驗。")
    for other in manifests[1:]:
        for key in ("queries_sha256", "corpus_sha256", "methods", "settings", "source_sha256", "formulas", "k"):
            if config[key] != other[key]:
                raise ValueError(f"來源敏感度的控制條件不符：{key}")
    if any(sha256(main / name) != sha256(repeat / name) for name in config["outputs_sha256"]):
        raise ValueError("重複實驗不一致。")
    if sha256(main / "rankings.csv") != sha256(weak / "rankings.csv"):
        raise ValueError("標籤來源比較必須固定排名。")
    changes = [name for name, expected in config["source_sha256"].items() if sha256(ROOT / name) != expected]
    if changes:
        raise ValueError(f"來源已變更，請先重新產生獨立實驗：{changes}")
    queries = read(main / "queries.json")
    labels = read(main / "judgments.json")["judgments"]
    rankings = rows(main / "rankings.csv")
    per_query = rows(main / "metrics_per_query.csv")
    summary = rows(main / "metrics_summary.csv")
    metric_names = ("precision_at_k", "recall_at_k", "reciprocal_rank", "ndcg_at_k")
    maximum_error = 0.0
    for row in per_query:
        selected = [r["pmid"] for r in rankings if r["qid"] == row["qid"] and r["method"] == row["method"]]
        records, k = labels[row["qid"]], int(row["k"])
        positive = {pid for pid, value in records.items() if value["grade"] > 0}
        hit = sum(pid in positive for pid in selected[:k])
        rr = next((1/(i+1) for i, pid in enumerate(selected) if pid in positive), 0)
        ideal = sum(1/math.log2(i+2) for i in range(min(k, len(positive))))
        dcg = sum(int(pid in positive)/math.log2(i+2) for i, pid in enumerate(selected[:k]))
        expected = [hit/k, hit/len(positive), rr, dcg/ideal if ideal else 0]
        maximum_error = max(maximum_error, *(abs(float(row[name])-value) for name, value in zip(metric_names, expected)))
    for row in summary:
        group = [r for r in per_query if r["method"] == row["method"]]
        maximum_error = max(maximum_error, *(abs(float(row[name])-sum(float(r[name]) for r in group)/len(group)) for name in metric_names))
    if maximum_error > 1e-12:
        raise ValueError("獨立指標重算不一致。")
    relative = lambda path: Path(os.path.relpath(path, report.parent)).as_posix()
    numeric = read(ROOT / "reports/verification.json")
    numeric_run = read(Path(numeric["runs"][0]["output"]) / "manifest.json")
    if numeric_run["queries_sha256"] != config["queries_sha256"]:
        raise ValueError("數值驗證仍屬於舊查詢，請先執行 verify_hw3.py。")
    coverage = rows(main / "reference_coverage.csv")
    lines = ["# HW3：TF/DF 四類與六種搭配的十查詢評估", "",
             "依使用者於 2026/10/24 提供的圖片重新設計查詢。原十個疾病／藥物查詢、人工資料及其歷史報告另存，沒有將舊 Q01 的答案套用至新 Q01。", "",
             design_markdown(queries), "", "## 控制條件與評估來源", "",
             "固定 3,000 篇英文 PubMed 摘要、C 前處理、k=10。原五方法使用 log10 標準 IDF 與 cosine；BM25 固定 k1=1.2、b=0.75 與自己的正值 log10 IDF。僅摘要正文計分，查詢與文件共用前處理及詞彙表。",
             "單詞查詢參考規則要求一個概念組；配對要求兩組均成立。優先使用保存 XML 的 MeSH、化學物質、補充概念或關鍵字，不足時獨立套用摘要全部概念組。規則不讀排名，未以評估分數調整選詞或標籤。",
             "這是自動二元參考標籤，非人工判讀或醫學真值；概念共現不能證明研究關係。詞彙回退及 metadata 別名仍偏向詞彙搜尋。分類使用精確查詢 token 的 TF/DF，相關性規則可含公開的複數／全名別名，兩者的統計範圍不同。",
             "P@k 分母固定 k；Recall 只相對於規則集合；MRR 使用完整非零排名；二元 nDCG 的折扣仍為 log2。未標註與不相關分開。", "",
             f"平均納入 {config['queries_evaluated']}/{config['queries_total']} 個查詢。查詢變更後人工檔依 corpus＋query fingerprint 分流，沒有新增人工答案。", "",
             "## 六方法平均指標", "",
             table(["方法", "P@10", "參考 Recall@10", "MRR", "nDCG@10"], [[r['method'], *[f"{float(r[name]):.4f}" for name in metric_names]] for r in summary]), "",
             "## 逐查詢參考集合與小樣本限制", "",
             table(["查詢", "metadata 正例", "weak 回退正例", "參考正例總數"], [[r['qid'], r['metadata_positive'], r['fallback_positive'], r['rule_relevant']] for r in coverage]), "",
             "少數配對的正例可能少於十篇；P@10 即使找回全部正例也未必等於 1。不能為湊滿十篇製造標籤。", "",
             "## RQ1–RQ5", "",
             "**RQ1。** 原始 TF 隨文件內次數線性增加；Log TF=1+log10(f) 壓縮重複詞，例如 f=1、3、10 對應 1、1.4771、2。四類依命中文件平均 TF 選詞，各文件仍按自己的實際次數計分。",
             "**RQ2。** IDF=log10(N/DF)。GLP-1／receptor 的高 DF 導致較低 IDF；MASLD／hypertension 的低 DF 導致較高 IDF。這表示詞項區辨力，不能當成醫學重要性。",
             "**RQ3。** 比較下表逐查詢 TF、IDF-only、TF-IDF 的排名與指標，不能預設 TF-IDF 必勝。單詞的查詢權重正比例會在 cosine 分子／分母抵消；文件端權重與完整 norm 仍會改變。六個配對可觀察不同 DF 的相對權重。BM25 的 scoring 同時改變，須另行解讀。",
             "**RQ4。** 原五方法的 cosine 已除完整向量 L2 norm，顯式 L2 前後應等價；normalization.csv 仍只含五方法十查詢。raw dot 與 cosine 是不同 scoring。BM25 不適用顯式 L2 等價檢查。",
             "**RQ5。** 平均與逐查詢表衡量對這一份固定參考規則的符合程度。單詞／配對代表不同資訊需求，兩者指標差異不能單獨歸因於查詢長度；需同時看參考集合大小與標籤來源。", "",
             "## 六方法十查詢完整指標", "",
             table(["查詢", "方法", "P@10", "參考 Recall@10", "RR", "nDCG@10"], [[r['qid'], r['method'], *[f"{float(r[name]):.4f}" for name in metric_names]] for r in per_query]), "",
             "## 重現與驗證", "",
             f"兩次主實驗全部 {len(config['outputs_sha256'])} 個輸出逐位元一致。獨立重算 {len(per_query)} 組指標，最大誤差 {maximum_error:g}。",
             f"NumPy 核對六設定共 {numeric['independent_cosine_scores_checked']:,} 個 cosine 與 {numeric['independent_bm25_scores_checked']:,} 個 BM25 分數；最大誤差分別為 {numeric['maximum_cosine_error']:.3g}、{numeric['maximum_bm25_error']:.3g}。",
             f"語料 SHA256：`{config['corpus_sha256']}`。查詢 SHA256：`{config['queries_sha256']}`。",
             "[主實驗 manifest](" + relative(main / 'manifest.json') + ")、[完整排名](" + relative(main / 'rankings.csv') + ")、[逐筆參考標籤](" + relative(main / 'reference_labels.csv') + ")、[分類證據](" + relative(main / 'query_design.json') + ")。",
             "重現：執行 `scripts/design_tfdf_queries.py` 驗證設計、`scripts/test_hw3.ps1`、`scripts/verify_hw3.py`、`scripts/evaluate_pubmed_reference.py`，再用 `scripts/build_hw3_report.py --analysis <固定 analysis> --report <新檔名>` 衍生報告。每次建立獨立 run，不覆寫舊成果。", ""]
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n\n".join(lines), encoding="utf-8")
    audit = {"report_sha256": sha256(report), "input_sha256": inputs,
             "main_run": main.relative_to(ROOT).as_posix(), "independently_recomputed_metric_rows": len(per_query),
             "maximum_metric_error": maximum_error, "source_changes": changes}
    audit_path = report.with_suffix(".audit.json")
    if audit_path.exists():
        raise ValueError("報告核對檔已存在，請另存新檔名。")
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"report": str(report), "audit": str(audit_path), "recomputed_metrics": len(per_query), "max_error": maximum_error}
