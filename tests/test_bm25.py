"""BM25 is the sixth model, with a separate score and no cosine normalization."""
from copy import deepcopy
import json
import math
from pathlib import Path

import pytest

from ir_hw3.core import BM25_PARAMETERS, Engine, METHODS, VECTOR_METHODS, Settings, term_weight
from ir_hw3 import experiments
from ir_hw3.corpus import ROOT, sha256
from test_core import documents


def test_bm25_hand_calculation_length_effect_and_linear_query_tf():
    # N=3, DF(alpha)=2, lengths=2/4/0, avgdl=2. Title is never counted.
    docs = documents("alpha alpha", "alpha beta beta beta", "")
    docs["3"].title = "alpha titleonly"
    engine = Engine(docs, Settings("B"))
    idf = math.log10(1 + 1.5 / 2.5)
    expected = {"1": idf * (2 * 2.2) / (2 + 1.2),
                "2": idf * 2.2 / (1 + 1.2 * (0.25 + 0.75 * 2))}
    ranked = engine.rank("alpha", "bm25", limit=None)
    assert [r["pmid"] for r in ranked] == ["1", "2"]
    assert engine.avgdl == 2
    assert "titleonly" not in engine.df
    for row in ranked:
        assert row["score"] == pytest.approx(expected[row["pmid"]])
        explanation = engine.explain("alpha unknown", row["pmid"], "bm25")
        assert sum(r["bm25_contribution"] for r in explanation) == pytest.approx(row["score"])
        assert explanation[-1]["bm25_contribution"] == 0
        assert "cosine_contribution" not in explanation[0]
    doubled = engine.rank("alpha alpha unknown", "bm25")
    assert [r["score"] for r in doubled] == pytest.approx([2 * r["score"] for r in ranked])


@pytest.mark.parametrize("condition", ["B", "C", "D"])
def test_bm25_uses_own_idf_in_every_preprocessing_condition(condition):
    docs = documents("the therapies alpha", "the therapy beta", "")
    standard = Engine(docs, Settings(condition, "standard"))
    smooth = Engine(docs, Settings(condition, "smooth"))
    assert standard.rank("the therapies alpha", "bm25") == smooth.rank("the therapies alpha", "bm25")
    assert standard.query("the therapies alpha", "bm25")[1].keys() <= standard.df.keys()


def test_bm25_empty_oov_ubiquitous_terms_and_scores_over_one():
    empty = Engine(documents("", ""))
    assert empty.rank("alpha", "bm25") == []
    assert empty.explain("alpha", "1", "bm25")[0]["bm25_contribution"] == 0
    engine = Engine(documents("alpha", "alpha"), Settings("B"))
    for query in ("", "???", "unknownword"):
        assert engine.rank(query, "bm25") == []
    assert engine.rank("alpha", "bm25")  # DF=N retains positive BM25 IDF.
    assert engine.rank("alpha " * 30, "bm25")[0]["score"] > 1  # Never clip.
    assert [r["pmid"] for r in engine.rank("alpha", "bm25")] == ["1", "2"]


def test_bm25_never_masquerades_as_cosine_or_standalone_vector_weights():
    engine = Engine(documents("alpha beta"))
    assert list(METHODS) == [*VECTOR_METHODS, "bm25"]
    for kwargs in ({"scoring": "cosine"}, {"scoring": "dot"}, {"normalize": True}):
        with pytest.raises(ValueError):
            engine.rank("alpha", "bm25", **kwargs)
    with pytest.raises(ValueError):
        engine.normalization_check("alpha", "bm25")
    with pytest.raises(ValueError):
        engine.vectors("bm25")
    with pytest.raises(ValueError):
        term_weight(2, 1, "bm25")
    with pytest.raises(ValueError):
        engine.rank("a" * 2001, "bm25")


def test_six_method_manifest_and_bm25_parameter_comparison(tmp_path, monkeypatch):
    queries = [{"qid": "Q1", "text": "alpha", "groups": [["alpha"]]}]
    monkeypatch.setattr(experiments, "ROOT", tmp_path)
    monkeypatch.setattr(experiments, "load_queries", lambda: queries)
    monkeypatch.setattr(experiments, "_source_hashes", lambda: {"fixture.py": "source"})
    engine = Engine(documents("alpha beta", "alpha", "gamma"), Settings("B"))
    run = experiments.run_experiment(engine, {"sha256": "corpus"})
    config = run["manifest"]
    assert config["methods"] == list(METHODS)
    assert config["bm25_parameters"] == BM25_PARAMETERS
    assert config["scoring"]["bm25"] == "bm25"
    assert config["normalization_methods"] == list(VECTOR_METHODS)
    assert run["normalization_passed"]
    assert experiments.compare_runs(run, run)["controlled_comparison"]
    other = experiments.run_experiment(engine, {"sha256": "corpus"})
    config = deepcopy(other["manifest"])
    config["bm25_parameters"]["b"] = 0
    (Path(other["output"]) / "manifest.json").write_text(json.dumps(config), encoding="utf-8")
    comparison = experiments.compare_runs(run, other)
    assert not comparison["controlled_comparison"]
    assert "bm25_parameters" in {r["field"] for r in comparison["mismatches"]}


def test_existing_five_method_history_stays_visible_and_unchanged():
    old = ROOT / "reports/pubmed_hybrid/runs/20261016T071423.657393Z-fe052825"
    before = sha256(old / "manifest.json")
    read = experiments._read_run(old)
    assert [r["method"] for r in read["summary"]] == list(VECTOR_METHODS)
    assert sha256(old / "manifest.json") == before


def test_bm25_cli_sixth_option(capsys, monkeypatch):
    from ir_hw3 import cli
    monkeypatch.setattr(cli, "load_corpus", lambda: (documents("alpha beta", "beta"), {}))
    monkeypatch.setattr("sys.argv", ["ir_hw3.cli", "search", "alpha", "--method", "bm25"])
    cli.main()
    result = json.loads(capsys.readouterr().out)
    assert len(result) == 1 and result[0]["pmid"] == "1"
