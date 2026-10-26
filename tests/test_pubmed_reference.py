from copy import deepcopy
import json
from pathlib import Path

import pytest

from ir_hw3.core import Engine, Settings
from ir_hw3.corpus import sha256
from ir_hw3.evaluation import csv_rows, fingerprint, load_judgments, parse_judgment_csv, validate_judgments
from ir_hw3 import experiments
from ir_hw3.pubmed import parse_response
from ir_hw3.pubmed_reference import (coverage_rows, extract_metadata, load_metadata,
    LEGACY_RULE_PATH, load_rules, metadata_hits, reference_judgments, reference_outputs)
from test_core import documents


def entry(term, field="mesh"):
    return {"field": field, "term": term, "ui": "", "major_topic": False}


def fixture():
    engine = Engine(documents("nothing", "semaglutide obesity", "semaglutide obesity", "obesity", "semaglutide obesity"), Settings("B"))
    query = [{"qid": "Q01", "text": "semaglutide weight loss obesity",
              "groups": [["semaglutide"], ["obesity", "weight loss"]]}]
    rules = load_rules(LEGACY_RULE_PATH)
    rules["queries"] = {"Q01": rules["queries"]["Q01"]}
    metadata = {"documents": {"1": {"entries": [entry("Semaglutide", "chemical"), entry("Obesity")]},
                              "2": {"entries": []},
                              "3": {"entries": [entry("Journal Article", "keyword")]},
                              "4": {"entries": [entry("Semaglutide", "chemical")]},
                              "5": {"entries": [entry("Semaglutide and weight loss", "keyword")]}},
                "counts": {}, "raw_xml_sha256": {"fixture.xml": "raw-sha"}}
    metadata["metadata_sha256"] = fingerprint(metadata["documents"])
    return engine, query, rules, metadata


def test_metadata_precedence_fallback_and_no_partial_evidence_merging(monkeypatch):
    engine, queries, rules, metadata = fixture()
    monkeypatch.setattr(engine, "rank", lambda *a, **k: pytest.fail("Labeling must never read ranking"))
    labels = reference_judgments(engine, queries, "corpus", metadata, rules)
    records = labels["judgments"]["Q01"]
    assert records["1"]["grade"] == 1 and records["1"]["weak_rule_grade"] == 0
    assert records["1"]["label_source"] == records["5"]["label_source"] == "pubmed_metadata"
    assert records["2"]["fallback_reason"] == "no_topic_metadata" and records["2"]["grade"] == 1
    assert records["3"]["fallback_reason"] == "incomplete_metadata_concepts" and records["3"]["grade"] == 1
    # Metadata semaglutide + abstract obesity alone cannot manufacture a hit.
    assert records["4"]["metadata_groups_matched"] == [1] and records["4"]["grade"] == 0
    assert all(r["grade"] in {0, 1} and r["reason"] for r in records.values())
    row = coverage_rows(labels)[0]
    assert row["metadata_positive"] == 2 and row["weak_fallback"] == 3
    assert row["fallback_positive"] == 2 and row["metadata_additions_over_weak"] == 1
    assert row["rule_relevant"] == 4 and row["rule_nonrelevant"] == 1
    assert fingerprint(labels) == fingerprint(reference_judgments(engine, queries, "corpus", metadata, rules))
    validate_judgments(labels, "corpus", queries, engine.documents)


def test_metadata_boundaries_and_punctuation_do_not_confuse_glp2():
    rules = load_rules(LEGACY_RULE_PATH)
    group = rules["shared_groups"]["glp1"]
    assert metadata_hits([entry("GLP–1 receptor agonists")], [group])
    assert not metadata_hits([entry("Glucagon-Like Peptide 2"), entry("glucagon")], [group])
    assert not metadata_hits([entry("presemaglutide")], [["semaglutide"]])
    assert metadata_hits([entry("Insulin-Secreting Cells")], [["insulin secreting cells"]])


def test_extract_retains_exact_sources_major_topics_qualifiers_and_types():
    xml = b'''<PubmedArticleSet><PubmedArticle><MedlineCitation Status="MEDLINE"><PMID>1</PMID>
    <Article><PublicationTypeList><PublicationType>Review</PublicationType></PublicationTypeList></Article>
    <MeshHeadingList><MeshHeading><DescriptorName UI="D1" MajorTopicYN="Y">Obesity</DescriptorName>
    <QualifierName UI="Q1" MajorTopicYN="N">drug therapy</QualifierName></MeshHeading></MeshHeadingList>
    <ChemicalList><Chemical><NameOfSubstance UI="C1">Semaglutide</NameOfSubstance></Chemical></ChemicalList>
    <KeywordList><Keyword>weight loss</Keyword></KeywordList><SupplMeshList><SupplMeshName UI="C2">test drug</SupplMeshName></SupplMeshList>
    </MedlineCitation></PubmedArticle></PubmedArticleSet>'''
    metadata = extract_metadata(parse_response(xml)[0])
    assert metadata["status"] == "MEDLINE" and metadata["publication_types"] == ["Review"]
    assert {e["field"] for e in metadata["entries"]} == {"mesh", "chemical", "keyword", "supplementary_concept"}
    mesh = metadata["entries"][0]
    assert mesh["major_topic"] and mesh["ui"] == "D1" and mesh["qualifiers"][0]["term"] == "drug therapy"


def test_raw_binding_checks_hash_missing_pmid_and_ignores_unselected(tmp_path):
    xml = tmp_path / "batch.xml"
    xml.write_text('<PubmedArticleSet><PubmedArticle><MedlineCitation Status="Publisher"><PMID>1</PMID><Article/></MedlineCitation></PubmedArticle></PubmedArticleSet>', encoding="utf-8")
    corpus = tmp_path / "abstracts.jsonl"
    corpus.write_text(json.dumps({"pmid": "1", "raw_path": "batch.xml"}), encoding="utf-8")
    manifest = {"sha256": sha256(corpus), "selected_pmids": ["1"], "raw_files": [{"file": "batch.xml", "sha256": sha256(xml)}]}
    metadata = load_metadata({"1": object()}, manifest, tmp_path)
    assert metadata["counts"]["any_topic_metadata"] == 0
    assert metadata["documents"]["1"]["raw_sha256"] == sha256(xml)
    xml.write_text(xml.read_text().replace("<PMID>1", "<PMID>2"), encoding="utf-8")
    with pytest.raises(ValueError, match="完整性"):
        load_metadata({"1": object()}, manifest, tmp_path)
    manifest["raw_files"][0]["sha256"] = sha256(xml)
    with pytest.raises(ValueError, match="缺少"):
        load_metadata({"1": object()}, manifest, tmp_path)


def test_hybrid_cannot_be_loaded_as_manual_and_version_mismatch_fails(tmp_path):
    engine, queries, rules, metadata = fixture()
    labels = reference_judgments(engine, queries, "corpus", metadata, rules)
    path = tmp_path / "manual.json"
    path.write_text(json.dumps(labels), encoding="utf-8")
    with pytest.raises(ValueError, match="human"):
        load_judgments("corpus", queries, engine.documents, path)
    with pytest.raises(ValueError, match="版本"):
        validate_judgments(labels, "other-corpus", queries, engine.documents)
    bad = deepcopy(rules); bad["queries"]["Q11"] = bad["queries"]["Q01"]
    with pytest.raises(ValueError, match="ID"):
        reference_judgments(engine, queries, "corpus", metadata, bad)


def test_reference_csv_cannot_be_reimported_as_human_even_with_legacy_opt_in():
    engine, queries, rules, metadata = fixture()
    labels = reference_judgments(engine, queries, "corpus", metadata, rules)
    rows = reference_outputs(labels, [], 10)["reference_labels.csv"]
    assert all(r["source"] == "pubmed_hybrid" and r["queries_sha256"] == fingerprint(queries) for r in rows)
    for legacy in (False, True):
        with pytest.raises(ValueError, match="人工標註來源"):
            parse_judgment_csv(csv_rows(rows), "corpus", queries, engine.documents, allow_legacy=legacy)


def test_hybrid_runs_preserve_evidence_and_source_separation(tmp_path, monkeypatch):
    engine, queries, rules, metadata = fixture()
    labels = reference_judgments(engine, queries, "corpus", metadata, rules)
    monkeypatch.setattr(experiments, "ROOT", tmp_path)
    monkeypatch.setattr(experiments, "load_queries", lambda: queries)
    monkeypatch.setattr(experiments, "_source_hashes", lambda: {"fixture.py": "source-hash"})
    first = experiments.run_experiment(engine, {"sha256": "corpus"}, judgments=labels)
    second = experiments.run_experiment(engine, {"sha256": "corpus"}, judgments=labels)
    assert Path(first["output"]).parent == tmp_path / "reports/pubmed_hybrid/runs"
    for name in ("reference_rules.json", "pubmed_metadata.json", "reference_labels.csv", "reference_coverage.csv", "reference_topk_sources.csv"):
        assert name in first["manifest"]["outputs_sha256"]
        assert (Path(first["output"])/name).read_bytes() == (Path(second["output"])/name).read_bytes()
    assert len(experiments.list_runs("pubmed_hybrid")) == 2
    assert experiments.compare_runs(first, second)["controlled_comparison"]
    weak = experiments.run_experiment(engine, {"sha256": "corpus"})
    assert not experiments.compare_runs(first, weak)["controlled_comparison"]
    assert not (tmp_path / "data/judgments/manual.json").exists()
