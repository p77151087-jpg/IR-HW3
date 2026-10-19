"""Saved runs preserve prior work and compare only matching evidence."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from ir_hw3.core import Engine, METHODS, Settings
from ir_hw3.evaluation import empty_judgments
from ir_hw3 import experiments
from test_core import documents


@pytest.fixture
def example(tmp_path, monkeypatch):
    queries = [{"qid": "Q1", "text": "alpha beta", "groups": [["alpha"], ["beta"]]},
               {"qid": "Q2", "text": "gamma", "groups": [["gamma"]]}]
    engine = Engine(documents("alpha alpha beta", "alpha gamma", "beta gamma"), Settings("B"))
    monkeypatch.setattr(experiments, "ROOT", tmp_path)
    monkeypatch.setattr(experiments, "load_queries", lambda: queries)
    monkeypatch.setattr(experiments, "_source_hashes", lambda: {"fixture.py": "source-hash"})
    return tmp_path, engine, queries


def saved_bytes(path):
    return {item.name: item.read_bytes() for item in path.iterdir() if item.is_file()}


def test_default_runs_are_unique_reproducible_and_preserve_legacy_results(example):
    root, engine, _ = example
    legacy = root / "reports/weak_rules"
    legacy.mkdir(parents=True)
    (legacy / "kept.txt").write_text("Earlier valuable experiment", encoding="utf-8")
    before = saved_bytes(legacy)
    first = experiments.run_experiment(engine, {"sha256": "corpus"})
    second = experiments.run_experiment(engine, {"sha256": "corpus"})
    assert first["output"] != second["output"]
    assert Path(first["output"]).parent == legacy / "runs"
    assert saved_bytes(legacy) == before
    assert first["manifest"]["run_id"] != second["manifest"]["run_id"]
    assert first["manifest"]["created_at_utc"].endswith("Z")
    assert "RQ_DISCUSSION.md" in first["manifest"]["outputs_sha256"]
    for name in first["manifest"]["outputs_sha256"]:
        assert (Path(first["output"]) / name).read_bytes() == (Path(second["output"]) / name).read_bytes()
    history = experiments.list_runs("weak_rules")
    assert len(history) == 2
    assert history[0]["summary"] == second["summary"]
    assert history[0]["queries_evaluated"] == history[0]["queries_total"] == 2
    assert history[0]["hashes"]["corpus"] == "corpus"
    assert history[0]["hashes"]["outputs"] == second["manifest"]["outputs_sha256"]
    comparison = experiments.compare_runs(first, second)
    assert comparison["controlled_comparison"]
    assert comparison["settings_differences"] == {}
    assert all(row["precision_at_k"] == 0 for row in comparison["metric_differences"])


def test_explicit_nonempty_output_is_rejected_without_any_changes(example):
    root, engine, _ = example
    output = root / "valuable"
    first = experiments.run_experiment(engine, {"sha256": "corpus"}, output=output)
    before = saved_bytes(output)
    with pytest.raises(FileExistsError, match="沒有覆寫"):
        experiments.run_experiment(engine, {"sha256": "corpus"}, output=output)
    assert saved_bytes(output) == before
    assert first["output"] == str(output.resolve())


def test_failed_write_never_becomes_a_successful_history_entry(example, monkeypatch):
    root, engine, _ = example
    original = experiments.atomic_json

    def fail_query_write(path, value):
        if path.name == "queries.json":
            raise OSError("simulated disk write failure")
        original(path, value)

    monkeypatch.setattr(experiments, "atomic_json", fail_query_write)
    with pytest.raises(OSError, match="simulated"):
        experiments.run_experiment(engine, {"sha256": "corpus"})
    assert experiments.list_runs() == []
    pending = list((root / "reports/weak_rules/runs").iterdir())
    assert len(pending) == 1 and pending[0].name.startswith(".pending-")
    assert not (pending[0] / "manifest.json").exists()


def test_history_excludes_corrupt_runs_and_compare_rejects_them(example):
    _, engine, _ = example
    good = experiments.run_experiment(engine, {"sha256": "corpus"})
    broken = experiments.run_experiment(engine, {"sha256": "corpus"})
    (Path(broken["output"]) / "rankings.csv").write_text("damaged", encoding="utf-8")
    assert [row["output"] for row in experiments.list_runs()] == [good["output"]]
    with pytest.raises(ValueError, match="完整性"):
        experiments.compare_runs(good, broken)


def test_publish_failure_with_finished_manifest_still_stays_out_of_history(example, monkeypatch):
    root, engine, _ = example

    def fail_publish(self, target):
        raise OSError("simulated publish failure")

    monkeypatch.setattr(Path, "rename", fail_publish)
    with pytest.raises(OSError, match="publish"):
        experiments.run_experiment(engine, {"sha256": "corpus"})
    assert experiments.list_runs() == []
    pending = list((root / "reports/weak_rules/runs").iterdir())
    assert len(pending) == 1 and pending[0].name.startswith(".pending-")
    assert (pending[0] / "manifest.json").is_file()


@pytest.mark.parametrize("field,value", [
    ("settings", []), ("judgment_source", "unknown"), ("k", 0),
    ("queries_total", -1), ("queries_evaluated", 99), ("source_sha256", {})])
def test_history_rejects_malformed_manifest_even_when_output_hashes_are_valid(example, field, value):
    _, engine, _ = example
    run = experiments.run_experiment(engine, {"sha256": "corpus"})
    path = Path(run["output"]) / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest[field] = value
    path.write_text(json.dumps(manifest), encoding="utf-8")
    assert experiments.list_runs() == []
    with pytest.raises(ValueError):
        experiments.compare_runs(run, run)


def test_history_rejects_nonfinite_summary_even_when_its_hash_is_current(example):
    _, engine, _ = example
    run = experiments.run_experiment(engine, {"sha256": "corpus"})
    output = Path(run["output"])
    rows = deepcopy(run["summary"])
    rows[0]["precision_at_k"] = float("nan")
    (output / "metrics_summary.csv").write_bytes(experiments.csv_rows(rows))
    manifest = run["manifest"]
    manifest["outputs_sha256"]["metrics_summary.csv"] = experiments.sha256(output / "metrics_summary.csv")
    (output / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert experiments.list_runs() == []
    with pytest.raises(ValueError, match="有限"):
        experiments.compare_runs(run, run)


def test_empty_human_run_keeps_null_metrics_and_never_creates_weak_labels(example):
    root, engine, queries = example
    judgments = empty_judgments("corpus", queries)
    result = experiments.run_experiment(engine, {"sha256": "corpus"}, judgments=judgments)
    assert Path(result["output"]).parent == root / "reports/human/runs"
    assert result["manifest"]["judgment_source"] == "human"
    assert result["manifest"]["queries_evaluated"] == 0
    assert all(row["precision_at_k"] is None for row in result["summary"])
    actual = json.loads((Path(result["output"]) / "judgments.json").read_text(encoding="utf-8"))
    assert actual == judgments
    assert len(experiments.list_runs("human")) == 1
    assert experiments.list_runs("weak_rules") == []


def test_controlled_comparison_allows_settings_changes_and_shows_them(example):
    _, engine, _ = example
    first = experiments.run_experiment(engine, {"sha256": "corpus"})
    other = Engine(engine.documents, Settings("C", "smooth"))
    second = experiments.run_experiment(other, {"sha256": "corpus"})
    result = experiments.compare_runs(first, second)
    assert result["controlled_comparison"]
    assert result["settings_differences"] == {
        "condition": {"left": "B", "right": "C"}, "idf": {"left": "standard", "right": "smooth"}}
    assert [row["method"] for row in result["metric_differences"]] == list(METHODS)


@pytest.mark.parametrize("change", ["labels", "source", "corpus", "queries", "k", "code"])
def test_mismatched_evidence_is_never_a_controlled_comparison(example, monkeypatch, change):
    _, engine, queries = example
    labels = empty_judgments("corpus", queries)
    labels["judgments"] = {"Q1": {"1": {"grade": 1, "reason": "Matches query concepts"}}}
    first = experiments.run_experiment(engine, {"sha256": "corpus"}, judgments=labels)
    other_labels = deepcopy(labels)
    corpus, k = "corpus", 10
    expected_field = "judgments_sha256"
    if change == "labels":
        other_labels["judgments"]["Q1"]["1"]["grade"] = 2
    elif change == "source":
        other_labels["source"] = "weak_rules"
        expected_field = "judgment_source"
    elif change == "corpus":
        corpus = other_labels["corpus_sha256"] = "other-corpus"
        expected_field = "corpus_sha256"
    elif change == "queries":
        changed_queries = deepcopy(queries)
        changed_queries[0]["text"] = "different query"
        monkeypatch.setattr(experiments, "load_queries", lambda: changed_queries)
        other_labels["queries_sha256"] = experiments.fingerprint(changed_queries)
        expected_field = "queries_sha256"
    elif change == "k":
        k, expected_field = 5, "k"
    elif change == "code":
        monkeypatch.setattr(experiments, "_source_hashes", lambda: {"fixture.py": "changed-source"})
        expected_field = "source_sha256"
    second = experiments.run_experiment(engine, {"sha256": corpus}, judgments=other_labels, k=k)
    result = experiments.compare_runs(first, second)
    assert not result["controlled_comparison"]
    assert expected_field in {row["field"] for row in result["mismatches"]}
    assert result["metric_differences"] == []


def test_legacy_manifest_remains_readable_without_rewriting_it(example):
    root, engine, _ = example
    output = root / "reports/weak_rules"
    result = experiments.run_experiment(engine, {"sha256": "corpus"}, output=output)
    manifest = result["manifest"]
    manifest["schema_version"] = 1
    for name in ("status", "run_id", "created_at_utc", "queries_evaluated"):
        manifest.pop(name)
    (output / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    before = saved_bytes(output)
    history = experiments.list_runs()
    assert len(history) == 1
    assert history[0]["legacy"]
    assert history[0]["queries_evaluated"] == 2
    assert saved_bytes(output) == before


def test_cli_history_does_not_require_corpus_loading(example, monkeypatch, capsys):
    from ir_hw3 import cli
    root, engine, _ = example
    result = experiments.run_experiment(engine, {"sha256": "corpus"})
    monkeypatch.setattr(cli, "load_corpus", lambda: pytest.fail("history should read saved manifests"))
    monkeypatch.setattr("sys.argv", ["ir_hw3.cli", "history", "--root", str(root / "reports")])
    cli.main()
    history = json.loads(capsys.readouterr().out)
    assert [row["output"] for row in history] == [result["output"]]
