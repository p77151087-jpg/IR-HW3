"""Append a sealed PubMed snapshot while retaining every base document.

Raw API responses and request evidence are cached for resumability. The final
snapshot.json is written last; incomplete acquisitions are never active corpora.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .corpus import ROOT, load_corpus, sha256
from .evaluation import atomic_json
from .pubmed import parse_article, parse_response, readable

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"


def utc():
    return datetime.now(timezone.utc).isoformat()


def cached_request(root, name, endpoint, params):
    path = root / "raw-batches" / name
    meta_path = path.with_name(path.name + ".json")
    url = endpoint + "?" + urlencode(params)
    if path.exists() and meta_path.exists():
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        if metadata["url"] != url or sha256(path) != metadata["sha256"]:
            raise ValueError("快取參數或指紋不符：" + name)
        return path.read_bytes(), metadata
    last_error = None
    for attempt in range(3):
        time.sleep(1 if attempt == 0 else 2 ** attempt)
        try:
            with urlopen(Request(url, headers={"User-Agent": "ir_hw3_course_snapshot/1.0"}), timeout=60) as response:
                raw = response.read(25 * 1024 * 1024 + 1)
            if len(raw) > 25 * 1024 * 1024:
                raise ValueError("API 回應超過 25 MiB。")
            # Validate before accepting a cache entry (rate-limit/error pages
            # remain retryable rather than becoming a permanent cached error).
            if name.endswith(".xml"):
                parse_response(raw)
            else:
                search = json.loads(raw)["esearchresult"]
                if search.get("errorlist") or search.get("ERROR"):
                    raise ValueError("PubMed 不接受查詢。")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            metadata = {"file": path.relative_to(root).as_posix(), "endpoint": endpoint,
                        "params": params, "url": url, "retrieved_at_utc": utc(),
                        "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
            atomic_json(meta_path, metadata)
            return raw, metadata
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"PubMed 下載失敗（已嘗試三次）：{name}: {last_error}") from last_error


def expand_snapshot(base: Path, output: Path, target=3000, progress=print):
    base, output = Path(base).resolve(), Path(output).resolve()
    if not output.is_relative_to((ROOT / "data/corpus").resolve()) or output == base:
        raise ValueError("新快照必須位於 HW3 data/corpus 下的獨立目錄。")
    documents, original = load_corpus(base)
    if type(target) is not int or not len(documents) < target <= 8000:
        raise ValueError("擴充目標必須大於原語料篇數且不超過 8,000。")
    configuration = {"base_sha256": original["sha256"], "query": original["query"],
                     "requested_count": target, "sort": "pub date", "batch_size": 100,
                     "candidate_page_size": min(10000, target * 2), "tool": "ir_hw3_course_snapshot"}
    if (output / "snapshot.json").exists():
        _, manifest = load_corpus(output)
        if manifest.get("configuration") != configuration:
            raise ValueError("已完成快照不可覆寫或變更參數。")
        return manifest
    output.mkdir(parents=True, exist_ok=True)
    state_path = output / "acquisition.json"
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state["configuration"] != configuration:
            raise ValueError("續傳參數不符，請使用獨立快照目錄。")
    else:
        if any(output.iterdir()):
            raise ValueError("新快照目錄非空且沒有可續傳紀錄。")
        state = {"configuration": configuration, "started_at_utc": utc(), "status": "in_progress"}
        atomic_json(state_path, state)
    # Copy only from HW3's existing sealed snapshot, never the HW2 active store.
    shutil.copytree(base / "raw-batches", output / "raw-batches", dirs_exist_ok=True)
    shutil.copyfile(base / "snapshot.json", output / "base-snapshot.json")
    raw_files = [dict(entry) for entry in original["raw_files"]]
    raw_files.append({"file": "base-snapshot.json", "sha256": sha256(output / "base-snapshot.json"),
                      "origin": base.relative_to(ROOT).as_posix()})
    outcomes = [{"pmid": doc_id, "status": "selected", "reason": "retained_from_base_snapshot",
                 "raw_file": document.raw_path} for doc_id, document in documents.items()]
    retained = len(documents)
    try:
        params = {"db": "pubmed", "tool": configuration["tool"], "term": configuration["query"],
                  "retmode": "json", "sort": "pub date", "retstart": 0,
                  "retmax": configuration["candidate_page_size"]}
        raw, meta = cached_request(output, "extension-search.json", EUTILS + "esearch.fcgi", params)
        raw_files.append(meta)
        search = json.loads(raw)["esearchresult"]
        candidates = list(dict.fromkeys(search["idlist"]))
        additions = [pmid for pmid in candidates if pmid not in documents]
        progress(f"原有 {retained} 篇已保留；PubMed 符合 {search['count']} 篇，取得 {len(candidates)} 個候選 PMID。", flush=True)
        fetched = 0
        for offset in range(0, len(additions), 100):
            batch = additions[offset:offset + 100]
            params = {"db": "pubmed", "tool": configuration["tool"], "id": ",".join(batch),
                      "rettype": "abstract", "retmode": "xml"}
            name = f"extension-efetch-{offset // 100:04d}.xml"
            raw, meta = cached_request(output, name, EUTILS + "efetch.fcgi", params)
            raw_files.append(meta)
            records = {}
            for article in parse_response(raw):
                pmid = readable(article.find("./MedlineCitation/PMID")) or readable(article.find("./BookDocument/PMID"))
                if pmid not in batch:
                    raise ValueError(f"EFetch 回傳非請求 PMID：{pmid}")
                if pmid in records:
                    raise ValueError(f"EFetch 回傳重複 PMID：{pmid}")
                records[pmid] = article
            for pmid in batch:
                row = {"pmid": pmid, "raw_file": meta["file"]}
                try:
                    if pmid not in records:
                        raise ValueError("missing_from_efetch")
                    document = parse_article(records[pmid])
                except ValueError as exc:
                    row.update(status="excluded", reason=str(exc))
                else:
                    if len(documents) < target:
                        document.acquired_at, document.raw_path, document.sha256 = meta["retrieved_at_utc"], meta["file"], meta["sha256"]
                        documents[pmid] = document
                        row.update(status="selected", reason="english_nonempty_abstract")
                    else:
                        row.update(status="not_needed", reason="eligible_after_target_reached")
                outcomes.append(row)
            fetched += len(batch)
            state.update(status="in_progress", selected_so_far=len(documents), fetched_additional=fetched, updated_at_utc=utc())
            atomic_json(state_path, state)
            progress(f"已納入 {len(documents)}/{target} 篇；本次已取得 {fetched} 篇原始紀錄。", flush=True)
            if len(documents) == target:
                break
        if len(documents) != target:
            raise ValueError(f"候選不足，僅 {len(documents)} 篇；未封存或切換語料。")
        # Keep every original JSONL byte, including the original document fields.
        encoded = base.joinpath("abstracts.jsonl").read_bytes()
        if not encoded.endswith(b"\n"):
            encoded += b"\n"
        encoded += ("\n".join(json.dumps(doc.to_dict(), ensure_ascii=False, separators=(",", ":"))
                              for doc in list(documents.values())[retained:]) + "\n").encode("utf-8")
        (output / "abstracts.jsonl").write_bytes(encoded)
        atomic_json(output / "selection.json", outcomes)
        counts = Counter(row["status"] for row in outcomes)
        manifest = {"schema_version": 1, "status": "complete", "query": original["query"],
                    "query_translation": search.get("querytranslation", ""), "configuration": configuration,
                    "requested_count": target, "started_at_utc": state["started_at_utc"], "completed_at_utc": utc(),
                    "counts": {"matched": int(search["count"]), "candidates": len(candidates), "selected": target,
                               "retained": retained, "added": target - retained, "fetched_additional": fetched,
                               "excluded": counts["excluded"], "eligible_not_selected": counts["not_needed"]},
                    "selected_pmids": list(documents), "sha256": sha256(output / "abstracts.jsonl"),
                    "selection_sha256": sha256(output / "selection.json"), "raw_files": raw_files,
                    "base_snapshot": {"path": base.relative_to(ROOT).as_posix(), "sha256": original["sha256"],
                                      "manifest_sha256": sha256(base / "snapshot.json"), "retained_byte_for_byte": True},
                    "exclusion_reasons": dict(Counter(row["reason"] for row in outcomes if row["status"] == "excluded")),
                    "sampling": "Original 1000 records retained unchanged; append first eligible new PMIDs in current PubMed pub-date order under the same query/cutoff. Not a random sample.",
                    "content": original["content"], "publication_date_note": original.get("publication_date_note", ""),
                    "rate_policy": {"requests_per_second": 1, "batch_size": 100, "max_attempts": 3, "api_key_used": False},
                    "sources": original["sources"], "copyright_notice": original["copyright_notice"]}
        atomic_json(output / "snapshot.json", manifest)
        load_corpus(output)
        state.update(status="complete", completed_at_utc=manifest["completed_at_utc"])
        state.pop("last_error", None)
        atomic_json(state_path, state)
        return manifest
    except Exception as exc:
        state.update(status="incomplete", last_error=str(exc), updated_at_utc=utc())
        atomic_json(state_path, state)
        raise
