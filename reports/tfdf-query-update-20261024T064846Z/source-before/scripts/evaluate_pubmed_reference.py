"""Run frozen PubMed reference evaluation, repeatability and source sensitivity."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datetime import datetime, timezone
import json
from uuid import uuid4

from ir_hw3.core import Engine, METHODS, LOGARITHM_BASE, WEIGHTING_VERSION
from ir_hw3.corpus import ROOT, load_corpus, sha256, verify_hw2_unchanged
from ir_hw3.evaluation import atomic_json, csv_rows, fingerprint, load_queries
from ir_hw3.experiments import run_experiment
from ir_hw3.pubmed_reference import build_reference, coverage_rows


def main():
    documents, manifest = load_corpus()
    engine = Engine(documents)
    queries = load_queries()
    manual_before = {str(p.relative_to(ROOT)): sha256(p) for p in (ROOT / "data/judgments").rglob("*.json")}
    labels = build_reference(engine, queries, manifest)
    print("Reference labels ready; saving two independent runs...", flush=True)
    first = run_experiment(engine, manifest, judgments=labels)
    labels_again = build_reference(engine, queries, manifest)
    if fingerprint(labels_again) != fingerprint(labels):
        raise AssertionError("Fresh XML extraction and labeling are not deterministic")
    second = run_experiment(engine, manifest, judgments=labels_again)
    repeated = {name: sha256(Path(first["output"]) / name) == sha256(Path(second["output"]) / name)
                for name in first["manifest"]["outputs_sha256"]}
    if not all(repeated.values()) or not first["normalization_passed"]:
        raise AssertionError("Reference output repeatability or L2 check failed")
    print("Comparing pure weak-rule reference under identical retrieval settings...", flush=True)
    weak = run_experiment(engine, manifest)
    sensitivity = []
    metric_names = ("precision_at_k", "recall_at_k", "reciprocal_rank", "ndcg_at_k")
    for hybrid, baseline in zip(first["summary"], weak["summary"]):
        for name in metric_names:
            a, b = hybrid[name], baseline[name]
            sensitivity.append({"method": hybrid["method"], "metric": name, "pubmed_hybrid": a,
                                "weak_rules": b, "difference_hybrid_minus_weak": a - b if a is not None and b is not None else None,
                                "interpretation": "Reference-source sensitivity, not human validation or weighting-only comparison"})
    manual_after = {str(p.relative_to(ROOT)): sha256(p) for p in (ROOT / "data/judgments").rglob("*.json")}
    protected = verify_hw2_unchanged()
    if manual_before != manual_after or protected["changed"]:
        raise AssertionError("Protected manual/HW2 data changed")
    analysis = ROOT / "reports/pubmed_hybrid/analysis" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    analysis.mkdir(parents=True, exist_ok=False)
    (analysis / "source_sensitivity.csv").write_bytes(csv_rows(sensitivity))
    provenance = labels["reference_provenance"]
    coverage = coverage_rows(labels)
    verification = {"logarithm_base": LOGARITHM_BASE, "weighting_version": WEIGHTING_VERSION,
                    "documents": engine.n, "queries": len(queries), "query_document_labels": sum(len(r) for r in labels["judgments"].values()),
                    "source": labels["source"], "corpus_sha256": manifest["sha256"],
                    "queries_sha256": fingerprint(queries), "judgments_sha256": fingerprint(labels),
                    "rules_sha256": provenance["rules_sha256"], "metadata_sha256": provenance["metadata_sha256"],
                    "metadata_counts": provenance["counts"], "fresh_label_generation_identical": True, "repeatability": repeated,
                    "normalization_passed": first["normalization_passed"], "manual_before": manual_before,
                    "manual_after": manual_after, "manual_unchanged": True, "hw2_source": protected,
                    "runs": [{"output": run["output"], "run_id": run["manifest"]["run_id"],
                              "source": run["manifest"]["judgment_source"],
                              "manifest_sha256": sha256(Path(run["output"]) / "manifest.json")}
                             for run in (first, second, weak)]}
    lines = ["# PubMed 主題參考評估（自動規則，非人工真值）", "",
             f"固定 {engine.n:,} 篇、{len(queries)} 查詢、C 前處理、原五方法使用 log10 與 cosine，第六種 BM25 固定 k1=1.2、b=0.75 及自己的 log10 IDF，k=10。"
             f"平均納入 {first['manifest']['queries_evaluated']}／{len(queries)} 查詢。", "",
             "依原始 XML 主題詞、藥物、補充概念與關鍵字共同命中建立正例；缺少或不足時獨立回退摘要 weak rule。"
             "二元 0／1 表示規則結果，人工判讀沒有新增。完整規則與限制見 docs/PUBMED_REFERENCE.md。", "",
             "## 指標", "", "| 方法 | P@10 | 規則集合 Recall@10 | MRR | 二元 nDCG@10 |", "|---|---:|---:|---:|---:|"]
    for row in first["summary"]:
        values = [f"{row[k]:.4f}" if row[k] is not None else "未計算" for k in metric_names]
        lines.append(f"| {row['method']} | {' | '.join(values)} |")
    lines += ["", "## 逐查詢標籤來源", "", "| 查詢 | metadata 正例 | weak 回退 | 回退正例 | 參考正例總數 | metadata 新增正例 |", "|---|---:|---:|---:|---:|---:|"]
    for row in coverage:
        lines.append(f"| {row['qid']} | {row['metadata_positive']} | {row['weak_fallback']} | {row['fallback_positive']} | {row['rule_relevant']} | {row['metadata_additions_over_weak']} |")
    lines += ["", "metadata 與 weak 回退按查詢分流，同一篇文章在不同查詢可有不同來源。"
              "weak 回退包含完全沒有主題欄位及欄位不足兩種，細分見 reference_coverage.csv。", "",
              "## 標籤來源敏感度", "", "| 方法 | 混合 P@10 | 純 weak P@10 | 混合 nDCG@10 | 純 weak nDCG@10 |", "|---|---:|---:|---:|---:|"]
    for a, b in zip(first["summary"], weak["summary"]):
        values = [a["precision_at_k"], b["precision_at_k"], a["ndcg_at_k"], b["ndcg_at_k"]]
        lines.append(f"| {a['method']} | " + " | ".join(f"{v:.4f}" if v is not None else "未計算" for v in values) + " |")
    winners = lambda rows, key: [r["method"] for r in rows if r[key] is not None and r[key] == max(x[key] for x in rows if x[key] is not None)]
    if first["manifest"]["queries_evaluated"]:
        lines += ["", f"混合參考下 P@10 最高：{', '.join(winners(first['summary'], 'precision_at_k'))}；"
                  f"nDCG@10 最高：{', '.join(winners(first['summary'], 'ndcg_at_k'))}。"
                  f"純 weak 下對應最高：{', '.join(winners(weak['summary'], 'precision_at_k'))}／"
                  f"{', '.join(winners(weak['summary'], 'ndcg_at_k'))}。"
                  "這些結論限於各參考來源，不預設 TF-IDF 必勝，也不能視為獨立人工驗證。"]
    # A real retrieved document illustrates formulas without changing labels.
    query = queries[0]
    rank = engine.rank(query["text"], "tfidf", limit=1)
    lines += ["", "## RQ1–RQ5 與可查核例子", ""]
    if rank:
        pmid = rank[0]["pmid"]
        lines += [f"Q01 的 TF-IDF 第一名為 PMID {pmid}：{engine.documents[pmid].title}。"
                  "下表來自其摘要向量，TF 是文件內次數，IDF 來自固定 3,000 篇的 DF。", "",
                  "| 詞 | TF | Log TF | DF | IDF | TF-IDF |", "|---|---:|---:|---:|---:|---:|"]
        import math
        for item in engine.explain(query["text"], pmid, "tfidf"):
            term = item["term"]
            tf = engine.counts[pmid].get(term, 0)
            lines.append(f"| {term} | {tf} | {1 + math.log10(tf) if tf else 0:.4f} | {engine.df.get(term, 0)} | {engine.idf.get(term, 0):.4f} | {tf * engine.idf.get(term, 0):.4f} |")
        lines += ["", f"該篇參考標籤：{labels['judgments'][query['qid']][pmid]['reason']}。"]
    lines += ["", "- RQ1：原始 TF 線性增加；Log TF 壓縮重複次數，影響須由相同設定的排名觀察。",
              "- RQ2：IDF=log10(N/DF)，DF 越高權重越低；這是區辨力，不是醫學重要性。",
              "- RQ3：原五方法與第六種 BM25 的實際排名見主 run 的 rankings.csv，配合上表指標比較，不預設勝者。",
              "- RQ4：五方法十查詢顯式 L2 前後的 cosine 分數／排名等價通過；raw dot 是另一種 scoring。",
              "- RQ5：指標表與逐查詢檔衡量對參考規則的符合程度；來源敏感度表揭露改變標籤的影響。", "",
              "## 限制與重現證據", "",
              "所有 30,000 筆都跑過規則，不等於已人工完整判讀。主題共現不保證藥物–終點關係，"
              "metadata 標引與詞彙回退都可能偏向詞面方法。Recall 僅針對規則集合，nDCG 只有二元等級。"
              "真實相關性及醫學效度仍待獨立人工驗證。", "",
              f"主 run：`{first['output']}`。兩次 run 全部 {len(repeated)} 個輸出逐位元相同；"
              f"HW2 {protected['checked']} 個受保護原始檔未變，人工檔前後 hash 相同。", "",
              f"語料 SHA256：`{manifest['sha256']}`。", "",
              "重現：`.venv\\Scripts\\python.exe -B -X utf8 scripts\\evaluate_pubmed_reference.py`。"
              "此腳本會建立新的獨立 run 與 analysis，不覆寫舊實驗。", ""]
    (analysis / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    verification["analysis_outputs_sha256"] = {n: sha256(analysis / n) for n in ("REPORT.md", "source_sensitivity.csv")}
    atomic_json(analysis / "verification.json", verification)
    print(json.dumps({"analysis": str(analysis), "runs": verification["runs"], "summary": first["summary"],
                      "coverage": coverage, "metadata_counts": provenance["counts"],
                      "repeatability_passed": all(repeated.values())}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
