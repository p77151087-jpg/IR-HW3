"""Reproducible controlled runs; weak judgments are always labeled as such."""
from __future__ import annotations
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import version
import csv
import json
import math
from pathlib import Path
import platform
import re
import tempfile
import time
from uuid import uuid4

from .core import (BM25_FORMULA, BM25_PARAMETERS, CONDITIONS, IDF_MODES,
                   LOGARITHM_BASE, WEIGHTING_VERSION, Engine, METHODS, VECTOR_METHODS)
from .corpus import ROOT, abstract_text, sha256
from .evaluation import (atomic_json, csv_rows, evaluate, evaluation_accounting,
                         fingerprint, load_queries, query_status)

def matches_concept(text: str, term: str) -> bool:
    """Trailing alphabetic fragments allow declared prefixes neuroprotect*, etc."""
    # Every expression below contains this exact literal. A C-level substring
    # miss avoids scanning the whole abstract with a leading lookbehind.
    if term not in text:
        return False
    prefix = term in {"neuroprotect", "neurodegenerat"}
    pattern = r"(?<!\w)" + re.escape(term) + (r"\w*" if prefix else r"(?!\w)")
    return re.search(pattern, text) is not None

def weak_judgments(engine: Engine, queries: list[dict], corpus_sha: str) -> dict:
    """All concept groups must match the abstract; never consult a ranking."""
    from ir_hw1.preprocessing import normalize
    result = {"schema_version": 1, "source": "weak_rules", "corpus_sha256": corpus_sha,
              "queries_sha256": fingerprint(queries), "judgments": {},
              "limitations": "Lexical concept co-occurrence is a weak label, not human relevance. "
                              "It favors lexical retrieval and cannot establish clinical relevance."}
    texts = {doc_id: normalize(abstract_text(doc)) for doc_id, doc in engine.documents.items()}
    for query in queries:
        records = {}
        for doc_id, text in texts.items():
            matched = [next((term for term in group if matches_concept(text, term)), "")
                       for group in query["groups"]]
            grade = int(all(matched))
            reason = ("規則弱標籤：摘要同時出現 " + "；".join(matched)) if grade else (
                "規則弱標籤：缺少概念組 " + ",".join(str(i + 1) for i, hit in enumerate(matched) if not hit))
            records[doc_id] = {"grade": grade, "reason": reason}
        result["judgments"][query["qid"]] = records
    return result

def candidate_pool(engine: Engine, query: str, per_method: int = 20) -> list[str]:
    ids = dict.fromkeys(row["pmid"] for method in METHODS
                        for row in engine.rank(query, method, limit=per_method))
    return list(ids)

def _source_hashes() -> dict[str, str]:
    paths = [ROOT / "app.py", ROOT / "ir_hw1/preprocessing.py", ROOT / "ir_hw1/models.py", ROOT / "resources/stopwords.json",
             ROOT / "README.md", ROOT / "docs/ANNOTATION_GUIDE.md", ROOT / "docs/DEMO.md",
             ROOT / "requirements.txt", ROOT / "requirements-lock.txt", ROOT / "pyproject.toml",
             ROOT / "scripts/test_hw3.ps1", ROOT / "scripts/verify_hw3.py"]
    paths.append(ROOT / "scripts/expand_corpus.py")
    paths.extend(sorted((ROOT / "data/reference_rules").glob("*.json")))
    if (ROOT / "docs/PUBMED_REFERENCE.md").is_file():
        paths.append(ROOT / "docs/PUBMED_REFERENCE.md")
    if (ROOT / "docs/BM25.md").is_file():
        paths.append(ROOT / "docs/BM25.md")
    paths.extend(sorted((ROOT / "ir_hw3").glob("*.py")))
    paths.extend(sorted((ROOT / "tests").glob("test_*.py")))
    if (ROOT / "scripts/profile_hw3.py").is_file():
        paths.append(ROOT / "scripts/profile_hw3.py")
    if (ROOT / "scripts/evaluate_pubmed_reference.py").is_file():
        paths.append(ROOT / "scripts/evaluate_pubmed_reference.py")
    if (ROOT / "scripts/build_hw3_report.py").is_file():
        paths.append(ROOT / "scripts/build_hw3_report.py")
    return {path.relative_to(ROOT).as_posix(): sha256(path) for path in paths}


def _require_available_output(output: Path) -> None:
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise FileExistsError(f"實驗輸出已存在且非空，請指定新的目錄；沒有覆寫：{output}")


def _publish_run(staging: Path, output: Path) -> None:
    """Windows scanners can briefly hold a just-written directory open.

    Retry only documented Windows access/sharing/lock failures. Permanent
    failures retain the pending directory, and a competing output is protected.
    """
    for attempt in range(4):
        _require_available_output(output)
        try:
            staging.rename(output)
            return
        except PermissionError as exc:
            if getattr(exc, "winerror", None) not in {5, 32, 33} or attempt == 3:
                raise
            time.sleep(0.1 * (attempt + 1))


def run_experiment(engine: Engine, manifest: dict, *, output: Path | None = None,
                   judgments: dict | None = None, k: int = 10) -> dict:
    if type(k) is not int or k < 1:
        raise ValueError("k 必須為正整數。")
    queries = load_queries()
    source = "weak_rules" if judgments is None else judgments["source"]
    if judgments is None:
        judgments = weak_judgments(engine, queries, manifest["sha256"])
    from .evaluation import validate_judgments
    validate_judgments(judgments, manifest["sha256"], queries, engine.documents)
    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid4().hex[:8]
    output = Path(output) if output is not None else ROOT / "reports" / source / "runs" / run_id
    output = output.resolve()
    _require_available_output(output)
    per_query, summary = evaluate(engine, queries, judgments, k)
    statuses = query_status(queries, judgments)
    rankings, normalization, pools = [], [], []
    for query in queries:
        for method in METHODS:
            ranking = engine.rank(query["text"], method, limit=None)
            rankings.extend({"qid": query["qid"], "method": method, **row} for row in ranking)
            if method in VECTOR_METHODS:
                normalization.append({"qid": query["qid"], "method": method,
                                      **engine.normalization_check(query["text"], method)})
        for doc_id in candidate_pool(engine, query["text"]):
            pools.append({"qid": query["qid"], "pmid": doc_id, "grade": -1, "reason": "",
                          "title": engine.documents[doc_id].title})
    outputs = {"metrics_per_query.csv": per_query, "metrics_summary.csv": summary,
               "query_status.csv": statuses,
               "rankings.csv": rankings, "normalization.csv": normalization,
               "annotation_pool.csv": pools, "term_statistics.csv": engine.term_statistics()}
    if source == "pubmed_hybrid":
        from .pubmed_reference import reference_outputs
        outputs.update(reference_outputs(judgments, rankings, k))
    # Publish only after every file and its hashes are ready. A failed write
    # leaves a hidden pending directory, never a successful history entry.
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".pending-" + run_id + "-", dir=output.parent))
    for name, rows in outputs.items():
        (staging / name).write_bytes(csv_rows(rows))
    atomic_json(staging / "judgments.json", judgments)
    atomic_json(staging / "queries.json", queries)
    reference_files = []
    if source == "pubmed_hybrid":
        provenance = judgments["reference_provenance"]
        atomic_json(staging / "reference_rules.json", provenance["rules"])
        atomic_json(staging / "pubmed_metadata.json", {key: value for key, value in provenance.items() if key != "rules"})
        reference_files = ["reference_rules.json", "pubmed_metadata.json"]
    configuration = {"schema_version": 2, "status": "complete", "run_id": run_id,
                     "created_at_utc": now.isoformat().replace("+00:00", "Z"),
                     "settings": asdict(engine.settings), "methods": list(METHODS),
                     "documents": engine.n, "vocabulary": len(engine.df),
                     "tokens": sum(engine.cf.values()), "corpus_sha256": manifest["sha256"],
                     "queries_sha256": fingerprint(queries), "judgments_sha256": fingerprint(judgments),
                     "judgment_source": source, **evaluation_accounting(statuses), "k": k,
                     "evaluation_policy": "Only queries with known relevant documents enter metric means; "
                                          "unjudged and judged-with-no-known-relevant queries are excluded separately.",
                     "query_status_counts": {status: sum(row["status"] == status for row in statuses) for status in
                                             ("unjudged", "judged_no_known_relevant", "has_known_relevant")},
                     "python": platform.python_version(),
                     "dependencies": {name: version(name) for name in ("regex", "nltk", "streamlit", "altair", "pandas", "numpy", "defusedxml")},
                     "source_sha256": _source_hashes(),
                     "logarithm_base": LOGARITHM_BASE, "weighting_version": WEIGHTING_VERSION,
                     "bm25_parameters": dict(BM25_PARAMETERS),
                     "scoring": {method: "bm25" if method == "bm25" else "cosine" for method in METHODS},
                     "normalization_methods": list(VECTOR_METHODS),
                     "normalization_excluded": {"bm25": "Not a cosine model; explicit L2 comparison does not apply."},
                     "formulas": {"tf": "f", "log_tf": "1 + log10(f), f > 0", "idf": "binary presence * IDF",
                                  "tfidf": "f * IDF", "log_tfidf": "(1 + log10(f)) * IDF",
                                  "standard_idf": "log10(N / DF)", "smooth_idf": "log10((N+1)/(DF+1)) + 1",
                                  "bm25": BM25_FORMULA, "bm25_idf": BM25_PARAMETERS["idf"]},
                     "tie_break": "score rounded to 12 decimal places, then PMID ascending",
                     "zero_vectors": "no retrieval; zero norm never divides by zero",
                     "query_tf": "actual term count; OOV terms excluded from vector norm",
                     "limitations": ["Single-topic nonrandom PubMed snapshot; abstract body only.",
                                     "Unjudged documents count as nonrelevant in ranking metrics; judged@k is reported.",
                                     "Recall uses the known relevant set; incomplete human annotation does not give full-corpus recall.",
                                     "Metric means exclude queries without known relevant documents; query_status.csv records every query and exclusion reason.",
                                     "Weak labels use lexical co-occurrence and are not human or clinical ground truth."]}
    if source == "pubmed_hybrid":
        from .pubmed_reference import LIMITATIONS
        configuration["reference_provenance"] = {key: value for key, value in judgments["reference_provenance"].items()
                                                   if key not in {"documents", "rules"}}
        configuration["limitations"].extend(LIMITATIONS)
    (staging / "RQ_DISCUSSION.md").write_text(rq_discussion(configuration, summary), encoding="utf-8")
    configuration["outputs_sha256"] = {
        name: sha256(staging / name) for name in [*outputs, "judgments.json", "queries.json", "RQ_DISCUSSION.md", *reference_files]}
    atomic_json(staging / "manifest.json", configuration)
    _require_available_output(output)
    if output.exists():
        output.rmdir()  # Only the verified empty destination.
    _publish_run(staging, output)
    return {"output": str(output), "manifest": configuration, "summary": summary, "query_status": statuses,
            "normalization_passed": all(row["same_ranking"] and row["max_score_difference"] < 1e-10 for row in normalization)}

def _read_run(output: Path, *, legacy: bool = False) -> dict:
    output = Path(output).resolve()
    configuration = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(configuration, dict):
        raise ValueError("實驗 manifest 必須是物件。")
    legacy = legacy and configuration.get("schema_version") == 1
    if not legacy and (configuration.get("schema_version") != 2 or configuration.get("status") != "complete"):
        raise ValueError("實驗未完成或 manifest 版本不支援。")
    settings = configuration.get("settings")
    if (not isinstance(settings, dict) or settings.get("condition") not in CONDITIONS or
            settings.get("idf") not in IDF_MODES):
        raise ValueError("實驗設定格式不正確。")
    if configuration.get("judgment_source") not in {"human", "weak_rules", "pubmed_hybrid"}:
        raise ValueError("實驗標註來源不正確。")
    if type(configuration.get("k")) is not int or configuration["k"] < 1:
        raise ValueError("實驗 k 必須為正整數。")
    total = configuration.get("queries_total")
    if type(total) is not int or total < 1:
        raise ValueError("實驗查詢母數不正確。")
    hashes = configuration.get("outputs_sha256", {})
    sources = configuration.get("source_sha256")
    if (not isinstance(hashes, dict) or not isinstance(sources, dict) or not sources or
            any(not isinstance(name, str) or not isinstance(digest, str) or not digest
                for name, digest in sources.items())):
        raise ValueError("實驗指紋格式不正確。")
    required = {"metrics_summary.csv", "rankings.csv", "judgments.json", "queries.json"}
    if not required.issubset(hashes):
        raise ValueError("實驗缺少必要的輸出指紋。")
    for name, expected in hashes.items():
        path = (output / name).resolve()
        if not path.is_relative_to(output) or not path.is_file() or sha256(path) != expected:
            raise ValueError(f"實驗輸出完整性驗證失敗：{name}")
    for name in ("queries", "judgments"):
        value = json.loads((output / f"{name}.json").read_text(encoding="utf-8"))
        if fingerprint(value) != configuration[f"{name}_sha256"]:
            raise ValueError(f"實驗資料版本指紋不符：{name}")
    with (output / "metrics_summary.csv").open(encoding="utf-8-sig", newline="") as stream:
        summary = list(csv.DictReader(stream))
    integers = {"k", "queries_total", "queries_evaluated", "queries_excluded",
                "queries_excluded_unjudged", "queries_excluded_no_known_relevant"}
    metric_keys = {"precision_at_k", "recall_at_k", "reciprocal_rank", "ndcg_at_k", "judged_at_k"}
    declared_methods = configuration.get("methods", list(VECTOR_METHODS))
    if (declared_methods not in (list(VECTOR_METHODS), list(METHODS)) or
            [row.get("method") for row in summary] != declared_methods or
            any(not (metric_keys | {"queries_evaluated", "k", "judgment_source"}).issubset(row) for row in summary)):
        raise ValueError("實驗摘要與宣告的方法不符，或缺少必要指標欄位。")
    for row in summary:
        for key in integers & row.keys():
            row[key] = int(row[key])
        for key in metric_keys & row.keys():
            row[key] = float(row[key]) if row[key] else None
    evaluated = configuration.get("queries_evaluated", summary[0]["queries_evaluated"])
    if type(evaluated) is not int or not 0 <= evaluated <= total:
        raise ValueError("實驗納入查詢數不正確。")
    for key in ("queries_excluded", "queries_excluded_unjudged", "queries_excluded_no_known_relevant"):
        if key in configuration and (type(configuration[key]) is not int or not 0 <= configuration[key] <= total):
            raise ValueError("實驗排除查詢數不正確。")
    if configuration.get("queries_excluded", total - evaluated) != total - evaluated:
        raise ValueError("實驗查詢母數與排除數不一致。")
    for row in summary:
        if (row["queries_evaluated"] != evaluated or row["k"] != configuration["k"] or
                row["judgment_source"] != configuration["judgment_source"] or
                row.get("queries_total", total) != total):
            raise ValueError("實驗摘要與 manifest 的母數或來源不一致。")
        for key in metric_keys:
            value = row[key]
            if ((evaluated == 0 and value is not None) or
                    (evaluated > 0 and (value is None or not math.isfinite(value) or not 0 <= value <= 1))):
                raise ValueError("實驗摘要的指標必須是有限的 0–1 數值；只有零母數可留空。")
    return {"output": str(output), "run_id": configuration.get("run_id", "legacy"),
            "created_at_utc": configuration.get("created_at_utc"), "legacy": legacy,
            "judgment_source": configuration["judgment_source"], "settings": configuration["settings"],
            "k": configuration["k"], "queries_total": configuration["queries_total"],
            "queries_evaluated": evaluated,
            "hashes": {"corpus": configuration["corpus_sha256"],
                       "queries": configuration["queries_sha256"],
                       "judgments": configuration["judgments_sha256"],
                       "source": fingerprint(configuration["source_sha256"]),
                       "manifest": sha256(output / "manifest.json"), "outputs": hashes},
            "summary": summary, "manifest": configuration}


def list_runs(source: str | None = None, *, root: Path | None = None) -> list[dict]:
    """Read intact completed history; root is the reports directory.

    Old source-root results remain available as a labeled legacy entry. Pending,
    malformed or damaged directories never appear as successful runs.
    """
    if source not in {None, "human", "weak_rules", "pubmed_hybrid"}:
        raise ValueError("標註來源必須為 human、weak_rules 或 pubmed_hybrid。")
    root = Path(root) if root is not None else ROOT / "reports"
    history = []
    for label in ([source] if source else ["human", "weak_rules", "pubmed_hybrid"]):
        base = root / label
        candidates = [(base, True)] if (base / "manifest.json").is_file() else []
        runs = base / "runs"
        if runs.is_dir():
            candidates.extend((path, False) for path in runs.iterdir()
                              if path.is_dir() and not path.name.startswith("."))
        for path, legacy in candidates:
            try:
                run = _read_run(path, legacy=legacy)
                if run["judgment_source"] == label:
                    history.append(run)
            except (OSError, ValueError, KeyError, TypeError):
                continue
    return sorted(history, key=lambda row: (row["created_at_utc"] or "", row["run_id"]), reverse=True)


def compare_runs(left: Path | dict, right: Path | dict) -> dict:
    """Check evidence before comparison. Delta = right minus left.

    Mismatched evidence returns an explanation and no metric deltas that could
    be mistaken for a controlled comparison.
    """
    def read(value):
        path = Path(value["output"]) if isinstance(value, dict) else Path(value)
        return _read_run(path, legacy=True)

    left, right = read(left), read(right)
    a, b = left["manifest"], right["manifest"]
    fields = ("judgment_source", "corpus_sha256", "queries_sha256", "judgments_sha256", "k",
              "source_sha256", "formulas", "logarithm_base", "weighting_version", "bm25_parameters",
              "scoring", "tie_break", "python", "dependencies")
    mismatches = [{"field": key, "left": a.get(key), "right": b.get(key)}
                  for key in fields if a.get(key) != b.get(key)]
    left_methods = [row["method"] for row in left["summary"]]
    right_methods = [row["method"] for row in right["summary"]]
    if left_methods != right_methods:
        mismatches.append({"field": "methods", "left": left_methods, "right": right_methods})
    settings_differences = {key: {"left": a["settings"].get(key), "right": b["settings"].get(key)}
                            for key in a["settings"].keys() | b["settings"].keys()
                            if a["settings"].get(key) != b["settings"].get(key)}
    if set(settings_differences) - {"condition", "idf"}:
        mismatches.append({"field": "unsupported_settings", "left": a["settings"], "right": b["settings"]})
    differences = []
    if not mismatches:
        for first, second in zip(left["summary"], right["summary"]):
            differences.append({"method": first["method"], **{
                key: second[key] - first[key] if first[key] is not None and second[key] is not None else None
                for key in ("precision_at_k", "recall_at_k", "reciprocal_rank", "ndcg_at_k", "judged_at_k")}})
    return {"controlled_comparison": not mismatches, "mismatches": mismatches,
            "settings_differences": settings_differences, "metric_differences": differences,
            "left": left, "right": right}


def rq_discussion(configuration: dict, summary: list[dict]) -> str:
    k = configuration["k"]
    source = {"weak_rules": "規則弱標籤示範，不能代替人工相關性評估",
              "pubmed_hybrid": "PubMed 主題參考＋摘要弱規則回退；自動二元參考標籤，非人工或官方查詢標準答案",
              "human": "人工標註；仍須檢查標註覆蓋率"}[configuration["judgment_source"]]
    lines = ["# HW3 RQ1–RQ5 實驗解讀", "", f"標註來源：{source}。", "",
             f"固定查詢共 {configuration['queries_total']} 個；平均指標納入 {configuration['queries_evaluated']} 個，"
             f"排除 {configuration['queries_excluded']} 個。"
             f"其中尚未標註 {configuration['queries_excluded_unjudged']} 個；"
             f"已判讀但尚無已知相關文件 {configuration['queries_excluded_no_known_relevant']} 個。", "",
             "只有已有相關文件的查詢納入平均；排除查詢並未被當成零分，也不能將少數查詢的平均解讀為已完成全部查詢。"
             "已判讀但未找到相關文件，不代表整個語料沒有相關文件。逐查詢狀態及排除原因見 query_status.csv。", "",
             "## RQ1：原始 TF 與 Log TF", "",
             "原始 TF 隨重複次數線性增加；Log TF 使用 1+log10(f)，將 f=1、2、10 轉成 1、1.301、2，抑制大量重複。"
             "文件與查詢使用同一公式，不能只改文件權重。", "",
             "## RQ2：IDF", "",
             "標準 IDF=log10(N/DF)。DF 越大、IDF 越小；出現在所有文件的詞 IDF=0。"
             "平滑版額外加 1，使這類詞保留權重。IDF 衡量區辨力，不等於醫學重要性。", "",
             "## RQ3：TF、IDF 與 TF-IDF 的排名", "",
             "TF 反映重複，僅 IDF 使用詞項出現與否，TF-IDF 同時使用文件內頻率與跨文件區辨力。"
             "控制語料、前處理、查詢、IDF 形式與 cosine 後，再比較逐查詢排名；沒有預設最佳方法。", "",
             "## RQ4：L2 normalization", "",
             "對非零向量，cos(q,d)=q·d/(||q||||d||)，等於兩個 L2 單位向量的點積。"
             "所以正確 cosine 在顯式正規化前後分數與排名相同（容許浮點誤差）。"
             "raw dot 與 normalized dot 的差異另列為補充對照，不能將 raw dot 稱作 cosine。"
             "完整檢查見 normalization.csv，僅含原五種向量方法；第六種 BM25 不適用此 L2 等價檢查。", "",
             "## RQ5：評估指標", "",
             "P@k 的分母固定為 k；MRR 為完整返回排名的第一個已知相關結果倒數；"
             "nDCG@k 使用 gain=2^grade−1；Recall@k 的分母是已知相關文件數。"
             "未標註不同於人工判為不相關，但此處評分時先按 0 處理，同時報告 judged@k。", "",
             f"| 方法 | P@{k} | Recall@{k} | MRR | nDCG@{k} | 查詢數 |", "|---|---:|---:|---:|---:|---:|"]
    for row in summary:
        values = ["未計算" if row[key] is None else f"{row[key]:.4f}" for key in
                  ("precision_at_k", "recall_at_k", "reciprocal_rank", "ndcg_at_k")]
        lines.append(f"| {row['method']} | {' | '.join(values)} | {row['queries_evaluated']} / {row['queries_total']} |")
    lines.extend(["", "## 第六種方法：BM25", "",
                  "原五種方法保留 log10 向量權重與 cosine。BM25 是另一種 scoring 模型，並非 cosine 或第六種對稱向量權重。",
                  f"固定參數 k1={BM25_PARAMETERS['k1']}、b={BM25_PARAMETERS['b']}，未針對參考標籤調參。",
                  f"BM25_IDF={BM25_PARAMETERS['idf']}；score={BM25_FORMULA}。",
                  "dl 是前處理後的摘要 token 數，avgdl 含所有 N 篇；查詢重複詞按實際 TF 線性累加，OOV 忽略。",
                  "BM25 使用自己的固定 IDF，不受 standard／smooth 選項影響；不做顯式 L2、不裁切至 0–1。",
                  "只比較排名指標，不能將 BM25 原始分數直接與 cosine 大小比較。BM25 也屬詞彙方法，仍受自動標籤偏差影響。"])
    if configuration["judgment_source"] == "pubmed_hybrid":
        lines.extend(["", "## PubMed 參考標籤的規則與限制", "",
                      "每個查詢的兩組概念均須由 MeSH、藥物／化學物質、補充概念或關鍵字支持，才記為 metadata 正例。"
                      "缺少欄位或概念依據不足時，獨立套用原摘要 weak rule；不是把缺少 MeSH 當作不相關。"
                      "所有規則先於比較固定，不使用排名或分數。0／1 是規則結果，沒有人工確認的 2 級相關性。", "",
                      "reference_rules.json 保存完整詞表；reference_labels.csv 保存逐筆來源、理由與欄位依據；"
                      "reference_coverage.csv 與 reference_topk_sources.csv 揭露回退比例及前 k 名來源。"
                      "pubmed_metadata.json 保存原始欄位、XML hash 與抽取指紋。", "",
                      "Recall 僅為規則參考集合 Recall；nDCG 採二元 gain。主題共現不保證研究關係、主要終點或醫學效度。"
                      "MeSH 不全為人工標引；關鍵字及回退仍可能偏向詞彙方法。參考 docs/PUBMED_REFERENCE.md。"])
    lines.extend(["", "若使用自動參考或弱標籤，數字只驗證實驗流程與此規則下的表現，不能聲稱已證明真實檢索品質。"
                  "人工標註可由多方法 Top 20 的聯集起步，但需交代 pooling 偏差，並補查池外文件。", ""])
    return "\n".join(lines)
