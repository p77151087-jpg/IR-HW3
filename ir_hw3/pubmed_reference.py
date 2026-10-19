"""Frozen PubMed metadata rules with explicit abstract-only weak fallback.

These are automatic reference labels, never human judgments. Metadata is read
from each selected document's exact archived XML, without a live PubMed request.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
import unicodedata

from .corpus import ROOT, SNAPSHOT, sha256
from .evaluation import fingerprint
from .pubmed import parse_response, readable

SOURCE = "pubmed_hybrid"
RULE_PATH = ROOT / "data/reference_rules/pubmed-v1.json"
LIMITATIONS = [
    "Automatic metadata/lexical proxy labels; not human judgments or official PubMed query relevance.",
    "MeSH indexing may be automated; author keywords, substances and indexing coverage are incomplete and heterogeneous.",
    "Topic co-occurrence does not establish a drug-outcome relationship, study focus, efficacy or clinical validity.",
    "Metadata misses abstain and trigger an independent abstract weak rule, not an automatic nonrelevance judgment.",
    "Fallback shares lexical signals with retrieval; the hybrid union can favor lexical methods and has no human validity guarantee.",
    "Binary labels do not distinguish relevance strength; nDCG uses only grades 0/1.",
    "Recall is recall against this rule-defined reference set, not complete true relevance in the corpus.",
    "Single-topic nonrandom abstract-only corpus; no MeSH tree expansion, negation or relation extraction.",
]


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.sub(r"[^\w]+", " ", value).split())


def load_rules(path: Path = RULE_PATH) -> dict:
    rules = json.loads(Path(path).read_text(encoding="utf-8"))
    if rules.get("schema_version") != 1 or not rules.get("queries"):
        raise ValueError("PubMed 參考規則版本或查詢設定不正確。")
    return rules


def concept_groups(rules: dict, qid: str) -> list[list[str]]:
    groups = rules["queries"][qid]["groups"]
    result = [rules["shared_groups"][g] if isinstance(g, str) else g for g in groups]
    if not result or any(not g or any(not isinstance(t, str) or not normalized(t) for t in g) for g in result):
        raise ValueError(f"{qid} 含空白或不合法的概念組。")
    return result


def extract_metadata(article) -> dict:
    citation = article.find("MedlineCitation")
    entries = []
    for heading in citation.findall("./MeshHeadingList/MeshHeading"):
        descriptor = heading.find("DescriptorName")
        if descriptor is not None and readable(descriptor):
            entries.append({"field": "mesh", "term": readable(descriptor), "ui": descriptor.get("UI", ""),
                            "major_topic": descriptor.get("MajorTopicYN", "N") == "Y",
                            "qualifiers": [{"term": readable(q), "ui": q.get("UI", ""),
                                            "major_topic": q.get("MajorTopicYN", "N") == "Y"}
                                           for q in heading.findall("QualifierName")]})
    for field, path in (("chemical", "./ChemicalList/Chemical/NameOfSubstance"),
                        ("supplementary_concept", "./SupplMeshList/SupplMeshName"),
                        ("keyword", "./KeywordList/Keyword")):
        for node in citation.findall(path):
            if readable(node):
                entries.append({"field": field, "term": readable(node), "ui": node.get("UI", ""),
                                "major_topic": node.get("MajorTopicYN", "N") == "Y"})
    return {"status": citation.get("Status", ""), "entries": entries,
            "publication_types": [readable(n) for n in citation.findall("./Article/PublicationTypeList/PublicationType")]}


def load_metadata(documents, manifest: dict, snapshot: Path = SNAPSHOT) -> dict:
    snapshot = Path(snapshot).resolve()
    if sha256(snapshot / "abstracts.jsonl") != manifest["sha256"] or list(documents) != manifest["selected_pmids"]:
        raise ValueError("PubMed 標籤的語料版本不符。")
    # Follow each document's raw_path, rather than selecting an arbitrary newer
    # duplicate PMID from another fetch batch.
    documents_json = [json.loads(s) for s in (snapshot / "abstracts.jsonl").read_text(encoding="utf-8").splitlines() if s.strip()]
    batches = {}
    for document in documents_json:
        batches.setdefault(document["raw_path"], set()).add(document["pmid"])
    expected = {record["file"]: record["sha256"] for record in manifest["raw_files"]}
    metadata, raw_hashes = {}, {}
    for relative, ids in sorted(batches.items()):
        path = (snapshot / relative).resolve()
        if not path.is_relative_to(snapshot) or relative not in expected or sha256(path) != expected[relative]:
            raise ValueError(f"PubMed 原始 XML 完整性驗證失敗：{relative}")
        raw_hashes[relative] = expected[relative]
        seen = set()
        for article in parse_response(path.read_bytes()).findall("PubmedArticle"):
            pmid = article.findtext("./MedlineCitation/PMID", "").strip()
            if pmid in ids:
                if pmid in seen:
                    raise ValueError(f"同一 XML 有重複 PMID：{pmid}")
                seen.add(pmid)
                metadata[pmid] = {**extract_metadata(article), "raw_path": relative,
                                  "raw_sha256": expected[relative]}
        if seen != ids:
            raise ValueError(f"原始 XML 缺少所選 PMID：{sorted(ids - seen)}")
    metadata = {pmid: metadata[pmid] for pmid in documents}
    counts = {field: sum(any(e["field"] == field for e in m["entries"]) for m in metadata.values())
              for field in ("mesh", "chemical", "supplementary_concept", "keyword")}
    counts["any_topic_metadata"] = sum(bool(m["entries"]) for m in metadata.values())
    counts["publication_types"] = sum(bool(m["publication_types"]) for m in metadata.values())
    return {"documents": metadata, "counts": counts, "raw_xml_sha256": raw_hashes,
            "metadata_sha256": fingerprint(metadata)}


def metadata_hits(entries: list[dict], groups: list[list[str]]) -> list[dict]:
    return _prepared_hits([(entry, " " + normalized(entry["term"]) + " ") for entry in entries],
                          [[(alias, " " + normalized(alias) + " ") for alias in group] for group in groups])


def _prepared_hits(entries, groups) -> list[dict]:
    """Normalize each metadata value/alias once, keeping identical boundaries."""
    hits = []
    for index, group in enumerate(groups, 1):
        for entry, text in entries:
            alias = next((term for term, needle in group if needle in text), None)
            if alias:
                hits.append({"group": index, "alias": alias, **entry})
    return hits


def reference_judgments(engine, queries: list[dict], corpus_sha: str, metadata: dict, rules: dict) -> dict:
    """Positive metadata evidence first; insufficient evidence abstains to weak.

    The fallback must independently match *all* original abstract concept groups.
    Partial metadata and partial abstract hits are never combined into a positive.
    """
    from .experiments import weak_judgments
    if set(metadata["documents"]) != set(engine.documents) or set(rules["queries"]) != {q["qid"] for q in queries}:
        raise ValueError("PubMed metadata／規則與語料或查詢 ID 不符。")
    weak = weak_judgments(engine, queries, corpus_sha)
    result = {"schema_version": 1, "source": SOURCE, "corpus_sha256": corpus_sha,
              "queries_sha256": fingerprint(queries), "judgments": {}, "limitations": LIMITATIONS,
              "reference_provenance": {"rule_version": rules["rule_version"], "rules_sha256": fingerprint(rules),
                                       "rules": rules, **metadata}}
    prepared = {pmid: [(entry, " " + normalized(entry["term"]) + " ") for entry in record["entries"]]
                for pmid, record in metadata["documents"].items()}
    for query in queries:
        groups = concept_groups(rules, query["qid"])
        prepared_groups = [[(alias, " " + normalized(alias) + " ") for alias in group] for group in groups]
        records = {}
        for pmid in engine.documents:
            entries = metadata["documents"][pmid]["entries"]
            hits = _prepared_hits(prepared[pmid], prepared_groups)
            matched = {hit["group"] for hit in hits}
            positive = len(matched) == len(groups)
            fallback = "" if positive else ("incomplete_metadata_concepts" if entries else "no_topic_metadata")
            base = weak["judgments"][query["qid"]][pmid]
            reason = ("PubMed 主題參考：" + "；".join(
                f"組{index} " + next(f"{h['field']}={h['term']}" for h in hits if h["group"] == index)
                for index in range(1, len(groups) + 1))) if positive else (
                "PubMed 主題依據不足，回退摘要 weak rule；" + base["reason"])
            records[pmid] = {"grade": 1 if positive else base["grade"], "reason": reason,
                             "label_source": "pubmed_metadata" if positive else "weak_rules_fallback",
                             "fallback_reason": fallback, "metadata_available": bool(entries),
                             "metadata_groups_matched": sorted(matched), "metadata_evidence": hits,
                             "weak_rule_grade": base["grade"]}
        result["judgments"][query["qid"]] = records
    return result


def build_reference(engine, queries: list[dict], manifest: dict, snapshot: Path = SNAPSHOT) -> dict:
    return reference_judgments(engine, queries, manifest["sha256"],
                               load_metadata(engine.documents, manifest, snapshot), load_rules())


def coverage_rows(judgments: dict) -> list[dict]:
    rows = []
    for qid, records in judgments["judgments"].items():
        sources = Counter(r["label_source"] for r in records.values())
        fallback = Counter(r["fallback_reason"] for r in records.values())
        rows.append({"qid": qid, "documents": len(records), "metadata_positive": sources["pubmed_metadata"],
                     "weak_fallback": sources["weak_rules_fallback"],
                     "fallback_no_metadata": fallback["no_topic_metadata"],
                     "fallback_insufficient_metadata": fallback["incomplete_metadata_concepts"],
                     "fallback_positive": sum(r["grade"] > 0 and r["label_source"] == "weak_rules_fallback" for r in records.values()),
                     "rule_relevant": sum(r["grade"] > 0 for r in records.values()),
                     "rule_nonrelevant": sum(r["grade"] == 0 for r in records.values()),
                     "metadata_additions_over_weak": sum(r["grade"] > r["weak_rule_grade"] for r in records.values())})
    return rows


def reference_outputs(judgments: dict, rankings: list[dict], k: int) -> dict:
    labels = [{"qid": qid, "pmid": pmid, "source": SOURCE,
               "corpus_sha256": judgments["corpus_sha256"],
               "queries_sha256": judgments["queries_sha256"], **record,
               "metadata_groups_matched": json.dumps(record["metadata_groups_matched"]),
               "metadata_evidence": json.dumps(record["metadata_evidence"], ensure_ascii=False)}
              for qid, records in judgments["judgments"].items() for pmid, record in records.items()]
    sources = []
    for qid, records in judgments["judgments"].items():
        from .core import METHODS
        for method in METHODS:
            top = [r for r in rankings if r["qid"] == qid and r["method"] == method][:k]
            selected = [records[r["pmid"]] for r in top]
            sources.append({"qid": qid, "method": method, "k": k, "retrieved_at_k": len(top),
                            "metadata_positive_at_k": sum(r["label_source"] == "pubmed_metadata" for r in selected),
                            "fallback_positive_at_k": sum(r["grade"] > 0 and r["label_source"] == "weak_rules_fallback" for r in selected),
                            "fallback_negative_at_k": sum(r["grade"] == 0 for r in selected)})
    return {"reference_labels.csv": labels, "reference_coverage.csv": coverage_rows(judgments),
            "reference_topk_sources.csv": sources}
