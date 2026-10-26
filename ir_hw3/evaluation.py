"""Explicit relevance judgments and metrics. Unjudged is distinct from grade 0."""
from __future__ import annotations
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import tempfile
import threading

from .corpus import ROOT

JUDGMENTS = ROOT / "data/judgments/manual.json"
_LOCK = threading.Lock()

def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()

def load_queries(path: Path | None = None) -> list[dict]:
    path = path or ROOT / "data/queries.json"
    queries = json.loads(path.read_text(encoding="utf-8"))
    ids = [query["qid"] for query in queries]
    if len(ids) != len(set(ids)) or any(not qid for qid in ids):
        raise ValueError("查詢 ID 必須非空且唯一。")
    if any(not query["text"].strip() for query in queries):
        raise ValueError("查詢文字不可為空。")
    return queries

def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

def empty_judgments(corpus_sha: str, queries: list[dict]) -> dict:
    return {"schema_version": 1, "source": "human", "corpus_sha256": corpus_sha,
            "queries_sha256": fingerprint(queries), "judgments": {}}

def judgment_path(corpus_sha: str, queries: list[dict] | None = None) -> Path:
    """Keep old corpus/query judgments intact; never relabel reused Q01 IDs."""
    versioned = ROOT / "data/judgments/by-corpus" / corpus_sha / "manual.json"
    query_hash = fingerprint(queries) if queries is not None else None
    by_query = versioned.parent / "by-queries" / (query_hash or "unknown") / "manual.json"
    query_conflict = False
    for candidate in (JUDGMENTS, versioned):
        if candidate.exists():
            stored = json.loads(candidate.read_text(encoding="utf-8"))
            if stored.get("corpus_sha256") == corpus_sha:
                if query_hash is None or stored.get("queries_sha256") == query_hash:
                    return candidate
                query_conflict = True
    if query_hash and (query_conflict or by_query.exists() or
                       any(q.get("design_version") for q in queries)):
        return by_query
    if JUDGMENTS.exists():
        return versioned
    return versioned if versioned.exists() else JUDGMENTS

def validate_judgments(value: dict, corpus_sha: str, queries: list[dict], document_ids) -> None:
    if value.get("schema_version") != 1 or value.get("source") not in {"human", "weak_rules", "pubmed_hybrid"}:
        raise ValueError("不支援的標註格式或來源。")
    if value.get("corpus_sha256") != corpus_sha or value.get("queries_sha256") != fingerprint(queries):
        raise ValueError("標註的語料或查詢版本不符，請另存或重新標註。")
    qids, valid_ids = {q["qid"] for q in queries}, set(document_ids)
    for qid, judgments in value["judgments"].items():
        if qid not in qids:
            raise ValueError(f"未知查詢：{qid}")
        for doc_id, record in judgments.items():
            if doc_id not in valid_ids:
                raise ValueError(f"未知 PMID：{doc_id}")
            if type(record["grade"]) is not int or record["grade"] not in {0, 1, 2}:
                raise ValueError("相關性等級必須是 0、1 或 2。")
            if not isinstance(record.get("reason"), str) or not record["reason"].strip():
                raise ValueError("每筆標註都需要判斷依據。")

def load_judgments(corpus_sha: str, queries: list[dict], document_ids,
                   path: Path | None = None) -> dict:
    path = judgment_path(corpus_sha, queries) if path is None else Path(path)
    value = json.loads(path.read_text(encoding="utf-8")) if path.exists() else empty_judgments(corpus_sha, queries)
    validate_judgments(value, corpus_sha, queries, document_ids)
    if value["source"] != "human":
        raise ValueError("人工標註檔的來源必須是 human；規則弱標籤請另存。")
    return value

def save_judgments(corpus_sha: str, queries: list[dict], document_ids,
                   updates: list[dict], path: Path | None = None, *,
                   expected: dict[tuple[str, str], dict | None] | None = None) -> dict:
    """Merge latest data; optionally reject changes to records read by the editor.

    ``expected`` maps (qid, PMID) to the original record, or None when unjudged.
    All comparisons happen before applying updates; -1 removes a judgment.
    """
    with _LOCK:
        path = judgment_path(corpus_sha, queries) if path is None else Path(path)
        value = load_judgments(corpus_sha, queries, document_ids, path)
        for (qid, doc_id), original in (expected or {}).items():
            if value["judgments"].get(qid, {}).get(doc_id) != original:
                raise ValueError("標註已由其他操作變更，請重新載入最新資料後再儲存；本次沒有寫入。")
        qids, ids = {q["qid"] for q in queries}, set(document_ids)
        for row in updates:
            qid, doc_id = str(row["qid"]), str(row["pmid"])
            if qid not in qids or doc_id not in ids:
                raise ValueError("標註含未知的查詢或文件。")
            raw_grade = row["grade"]
            if isinstance(raw_grade, bool) or raw_grade is None:
                raise ValueError("相關性等級必須是整數。")
            try:
                grade = int(raw_grade)
            except (ValueError, TypeError, OverflowError) as exc:
                raise ValueError("相關性等級必須是整數。") from exc
            if float(raw_grade) != grade or grade not in {-1, 0, 1, 2}:
                raise ValueError("相關性等級必須是 -1、0、1 或 2。")
            records = value["judgments"].setdefault(qid, {})
            if grade == -1:
                records.pop(doc_id, None)
            else:
                reason = row.get("reason", "")
                records[doc_id] = {"grade": grade, "reason": reason.strip() if isinstance(reason, str) else ""}
        validate_judgments(value, corpus_sha, queries, document_ids)
        atomic_json(path, value)
        return value

def csv_rows(rows: list[dict]) -> bytes:
    stream = io.StringIO(newline="")
    if rows:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return stream.getvalue().encode("utf-8-sig")

def export_judgment_rows(rows: list[dict], corpus_sha: str, queries: list[dict]) -> list[dict]:
    """Attach human-source and dataset-version evidence to an annotation CSV."""
    metadata = {"source": "human", "corpus_sha256": corpus_sha,
                "queries_sha256": fingerprint(queries)}
    if any(row.get("source", "human") != "human" or
           row.get("judgment_source", "human") != "human" for row in rows):
        raise ValueError("不能將其他來源的標籤匯出為人工標註。")
    return [{**row, **metadata} for row in rows]

def parse_judgment_csv(data: bytes, corpus_sha: str, queries: list[dict], document_ids, *,
                       allow_legacy: bool = False) -> list[dict]:
    """Validate an entire import without writing or changing any judgments.

    Legacy opt-in applies only when all three metadata columns are absent.
    Existing but invalid source/version evidence can never be bypassed.
    """
    required = {"qid", "pmid", "grade", "reason"}
    metadata = {"source", "corpus_sha256", "queries_sha256"}
    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline=""), strict=True)
        fields = reader.fieldnames
        if not fields or len(fields) != len(set(fields)) or any(not field for field in fields):
            raise ValueError("CSV 必須有非空且不重複的欄位名稱。")
        if not required.issubset(fields):
            raise ValueError("CSV 缺少必要欄位：qid、pmid、grade、reason。")
        present = metadata.intersection(fields)
        if present and present != metadata:
            raise ValueError("CSV 版本欄位不完整，必須同時提供 source、corpus_sha256、queries_sha256。")
        if not present and not allow_legacy:
            raise ValueError("CSV 沒有來源與資料版本資訊；確認舊檔的來源及版本後，才可明確允許舊格式。")
        qids, ids = {query["qid"] for query in queries}, set(document_ids)
        queries_sha = fingerprint(queries)
        rows, seen = [], set()
        for line, row in enumerate(reader, 2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"CSV 第 {line} 列的欄位數不符。")
            if row.get("judgment_source", "human").strip() != "human":
                raise ValueError(f"CSV 第 {line} 列不是人工標註來源（human）。")
            if present:
                if row["source"].strip() != "human":
                    raise ValueError(f"CSV 第 {line} 列不是人工標註來源（human）。")
                if row["corpus_sha256"].strip() != corpus_sha or row["queries_sha256"].strip() != queries_sha:
                    raise ValueError(f"CSV 第 {line} 列的語料或查詢版本不符。")
            qid, doc_id = row["qid"].strip(), row["pmid"].strip()
            if qid not in qids or doc_id not in ids:
                raise ValueError(f"CSV 第 {line} 列含未知的查詢或 PMID。")
            if (qid, doc_id) in seen:
                raise ValueError(f"CSV 重複標註同一查詢與 PMID：{qid}、{doc_id}。")
            seen.add((qid, doc_id))
            try:
                grade = int(row["grade"].strip())
            except ValueError as exc:
                raise ValueError(f"CSV 第 {line} 列的相關性等級必須是整數。") from exc
            if grade not in {-1, 0, 1, 2}:
                raise ValueError(f"CSV 第 {line} 列的相關性等級必須是 -1、0、1 或 2。")
            reason = row["reason"].strip()
            if grade >= 0 and not reason:
                raise ValueError(f"CSV 第 {line} 列的人工判讀需要判斷依據。")
            if grade == -1 and reason:
                raise ValueError(f"CSV 第 {line} 列未標註卻含有理由；請評級或清空理由，避免遺失註記。")
            rows.append({"qid": qid, "pmid": doc_id, "grade": grade, "reason": reason})
    except (UnicodeError, csv.Error) as exc:
        raise ValueError(f"CSV 必須是有效的 UTF-8 CSV：{exc}") from exc
    if not rows:
        raise ValueError("CSV 沒有標註資料。")
    return rows

def metrics(ranking: list[str], judgments: dict[str, dict], k: int = 10) -> dict:
    if k < 1 or len(ranking) != len(set(ranking)):
        raise ValueError("k 必須為正整數，排名不可含重複文件。")
    relevant = {doc_id for doc_id, record in judgments.items() if record["grade"] > 0}
    head = ranking[:k]
    hits = sum(doc_id in relevant for doc_id in head)
    rr = next((1 / rank for rank, doc_id in enumerate(ranking, 1) if doc_id in relevant), 0.0)
    dcg = sum((2 ** judgments.get(doc_id, {"grade": 0})["grade"] - 1) / math.log2(rank + 1)
              for rank, doc_id in enumerate(head, 1))
    ideal = sorted((record["grade"] for record in judgments.values()), reverse=True)[:k]
    idcg = sum((2 ** grade - 1) / math.log2(rank + 1) for rank, grade in enumerate(ideal, 1))
    return {"precision_at_k": hits / k, "recall_at_k": hits / len(relevant) if relevant else 0.0,
            "reciprocal_rank": rr, "ndcg_at_k": dcg / idcg if idcg else 0.0,
            "judged_at_k": sum(doc_id in judgments for doc_id in head) / k,
            "known_relevant": len(relevant), "judged_documents": len(judgments), "retrieved": len(ranking)}

def query_status(queries: list[dict], judgments: dict) -> list[dict]:
    """Expose annotation coverage without treating unknown as a negative judgment.

    A query enters metric means only after at least one relevant document is
    known. A query with only grade-0 records may still have relevant documents
    elsewhere in the corpus; this helper makes no completeness claim.
    """
    rows = []
    for query in queries:
        records = judgments["judgments"].get(query["qid"], {})
        relevant = sum(record["grade"] > 0 for record in records.values())
        if relevant:
            status, reason = "has_known_relevant", ""
        elif records:
            status, reason = "judged_no_known_relevant", "no_known_relevant"
        else:
            status, reason = "unjudged", "unjudged"
        rows.append({"qid": query["qid"], "query": query["text"],
                     "judgment_source": judgments["source"], "status": status,
                     "judged_documents": len(records), "known_relevant": relevant,
                     "included_in_mean": bool(relevant), "exclusion_reason": reason})
    return rows

def evaluation_accounting(statuses: list[dict]) -> dict:
    """Shared query denominators for the UI, CSV summaries and run manifest."""
    evaluated = sum(row["included_in_mean"] for row in statuses)
    return {"queries_total": len(statuses), "queries_evaluated": evaluated,
            "queries_excluded": len(statuses) - evaluated,
            "queries_excluded_unjudged": sum(row["status"] == "unjudged" for row in statuses),
            "queries_excluded_no_known_relevant": sum(
                row["status"] == "judged_no_known_relevant" for row in statuses)}

def evaluate(engine, queries: list[dict], judgments: dict, k: int = 10) -> tuple[list[dict], list[dict]]:
    from .core import METHODS
    rows, summaries = [], []
    statuses = query_status(queries, judgments)
    accounting = evaluation_accounting(statuses)
    for method in METHODS:
        group = []
        for query, status in zip(queries, statuses):
            records = judgments["judgments"].get(query["qid"], {})
            if not status["included_in_mean"]:
                continue
            ranking = engine.rank(query["text"], method, limit=None)
            row = {"qid": query["qid"], "query": query["text"], "method": method, "k": k,
                   "judgment_source": judgments["source"],
                   **metrics([r["pmid"] for r in ranking], records, k)}
            rows.append(row)
            group.append(row)
        summaries.append({"method": method, **accounting, "k": k,
                          "judgment_source": judgments["source"],
                          **{key: sum(row[key] for row in group) / len(group) if group else None for key in
                             ("precision_at_k", "recall_at_k", "reciprocal_rank", "ndcg_at_k", "judged_at_k")}})
    return rows, summaries
