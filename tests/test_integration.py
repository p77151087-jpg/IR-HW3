import json
from pathlib import Path
import pytest
from ir_hw3.corpus import ROOT, ORIGINAL_SNAPSHOT, SNAPSHOT, load_corpus, sha256
from ir_hw3.core import Engine, METHODS, VECTOR_METHODS, Settings
from ir_hw3.evaluation import evaluate, load_queries, validate_judgments
from ir_hw3.experiments import weak_judgments

def test_sealed_corpus_all_queries_and_methods():
    documents, manifest = load_corpus()
    queries = load_queries()
    assert len(documents) == 3000
    assert len(queries) >= 10
    engine = Engine(documents)
    qrels = weak_judgments(engine, queries, manifest["sha256"])
    validate_judgments(qrels, manifest["sha256"], queries, documents)
    assert all(any(row["grade"] for row in records.values()) for records in qrels["judgments"].values())
    detail, summary = evaluate(engine, queries, qrels)
    assert len(detail) == len(queries) * len(METHODS)
    assert len(summary) == len(METHODS)
    for query in queries:
        for method in METHODS:
            ranking = engine.rank(query["text"], method)
            assert len(ranking) == 10
            if method in VECTOR_METHODS:
                assert engine.normalization_check(query["text"], method)["same_ranking"]
    assert all(0 <= row[metric] <= 1 for row in summary
               for metric in ("precision_at_k", "recall_at_k", "reciprocal_rank", "ndcg_at_k"))

def test_expanded_snapshot_preserves_every_original_document_and_query():
    original, old = load_corpus(ORIGINAL_SNAPSHOT)
    expanded, new = load_corpus()
    assert len(original) == 1000 and len(expanded) == 3000
    assert list(expanded)[:1000] == list(original)
    assert all(expanded[pmid].to_dict() == doc.to_dict() for pmid, doc in original.items())
    assert (SNAPSHOT / "abstracts.jsonl").read_bytes().startswith((ORIGINAL_SNAPSHOT / "abstracts.jsonl").read_bytes())
    assert new["query"] == old["query"]
    assert new["base_snapshot"]["manifest_sha256"] == sha256(ORIGINAL_SNAPSHOT / "snapshot.json")
    assert new["counts"]["added"] == 2000

def test_corrupt_corpus_rejected(tmp_path):
    from ir_hw1.models import Document, TextBlock
    document = Document(pmcid="PMID1", pmid="1", title="t", language="eng",
                        blocks=[TextBlock("b0", "abstract", "abstract", "alpha")])
    abstracts = tmp_path / "abstracts.jsonl"
    abstracts.write_text(json.dumps(document.to_dict()), encoding="utf-8")
    (tmp_path / "selection.json").write_text("{}", encoding="utf-8")
    manifest = {"status": "complete", "schema_version": 1, "sha256": sha256(abstracts),
                "selection_sha256": sha256(tmp_path / "selection.json"), "raw_files": [],
                "selected_pmids": ["1"], "counts": {"selected": 1}}
    (tmp_path / "snapshot.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert len(load_corpus(tmp_path)[0]) == 1
    abstracts.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="完整性"):
        load_corpus(tmp_path)
