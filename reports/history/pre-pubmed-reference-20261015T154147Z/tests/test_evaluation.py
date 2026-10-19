import math
import json
import csv
import pytest
from ir_hw3.evaluation import (metrics, save_judgments, load_judgments, validate_judgments,
                               empty_judgments, evaluate, evaluation_accounting, query_status,
                               csv_rows, export_judgment_rows, parse_judgment_csv, fingerprint)
from ir_hw3.experiments import matches_concept, weak_judgments, run_experiment
from ir_hw3.core import Engine, Settings, METHODS
from test_core import documents

def test_metrics_against_hand_graded_example():
    qrels = {"r1": {"grade": 2}, "r2": {"grade": 1}, "r3": {"grade": 1}, "n": {"grade": 0}}
    result = metrics(["n", "r2", "r1"], qrels, 2)
    assert result["precision_at_k"] == 0.5
    assert result["recall_at_k"] == pytest.approx(1 / 3)
    assert result["reciprocal_rank"] == 0.5
    assert result["ndcg_at_k"] == pytest.approx((1 / math.log2(3)) / (3 + 1 / math.log2(3)))
    assert result["judged_at_k"] == 1

def test_short_list_and_unjudged_denominators():
    result = metrics(["r"], {"r": {"grade": 1}}, 10)
    assert result["precision_at_k"] == 0.1
    assert result["judged_at_k"] == 0.1
    assert result["recall_at_k"] == 1
    assert metrics([], {}, 10)["ndcg_at_k"] == 0
    with pytest.raises(ValueError):
        metrics(["r", "r"], {}, 10)

def test_manual_round_trip_merge_remove_and_version_check(tmp_path):
    queries = [{"qid": "Q1", "text": "alpha"}]
    path = tmp_path / "manual.json"
    save_judgments("hash", queries, ["1", "2"], [{"qid": "Q1", "pmid": "1", "grade": 1, "reason": "讀過摘要，符合主題"}], path)
    result = save_judgments("hash", queries, ["1", "2"], [{"qid": "Q1", "pmid": "2", "grade": 0, "reason": "不符查詢意圖"}], path)
    assert len(result["judgments"]["Q1"]) == 2
    assert result["source"] == "human"
    save_judgments("hash", queries, ["1", "2"], [{"qid": "Q1", "pmid": "2", "grade": -1}], path)
    assert "2" not in load_judgments("hash", queries, ["1", "2"], path)["judgments"]["Q1"]
    with pytest.raises(ValueError, match="版本"):
        load_judgments("different", queries, ["1", "2"], path)

def test_manual_loader_rejects_weak_label_file_without_overwriting(tmp_path):
    queries = [{"qid": "Q1", "text": "alpha"}]
    value = empty_judgments("hash", queries)
    value["source"] = "weak_rules"
    path = tmp_path / "manual.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="human"):
        load_judgments("hash", queries, ["1"], path)
    assert path.read_bytes() == before

def test_legacy_import_cannot_ignore_explicit_weak_source():
    from ir_hw3.evaluation import parse_judgment_csv
    data = b"qid,pmid,grade,reason,judgment_source\nQ1,1,1,rule,weak_rules\n"
    with pytest.raises(ValueError, match="human"):
        parse_judgment_csv(data, "hash", [{"qid": "Q1", "text": "alpha"}], ["1"], allow_legacy=True)


def test_manual_conflict_rejects_entire_write_but_preserves_unrelated_changes(tmp_path):
    queries = [{"qid": "Q1", "text": "alpha"}]
    path = tmp_path / "manual.json"
    original = {"grade": 1, "reason": "第一版判斷"}
    save_judgments("hash", queries, ["1", "2"], [
        {"qid": "Q1", "pmid": "1", **original}], path,
        expected={("Q1", "1"): None})
    save_judgments("hash", queries, ["1", "2"], [
        {"qid": "Q1", "pmid": "2", "grade": 0, "reason": "另一篇的判斷"}], path)
    # An unrelated new record does not block an editor's existing draft.
    save_judgments("hash", queries, ["1", "2"], [
        {"qid": "Q1", "pmid": "1", "grade": 2, "reason": "更新判斷"}], path,
        expected={("Q1", "1"): original})
    before = path.read_bytes()
    # Another editor still holds the old record. Neither row may commit.
    with pytest.raises(ValueError, match="重新載入"):
        save_judgments("hash", queries, ["1", "2"], [
            {"qid": "Q1", "pmid": "2", "grade": -1},
            {"qid": "Q1", "pmid": "1", "grade": 0, "reason": "過期判斷"}], path,
            expected={("Q1", "1"): original})
    assert path.read_bytes() == before

@pytest.mark.parametrize("row", [
    {"qid": "Q1", "pmid": "1", "grade": 1, "reason": ""},
    {"qid": "bad", "pmid": "1", "grade": 1, "reason": "x"},
    {"qid": "Q1", "pmid": "bad", "grade": 1, "reason": "x"},
    {"qid": "Q1", "pmid": "1", "grade": 1.5, "reason": "x"},
    {"qid": "Q1", "pmid": "1", "grade": True, "reason": "x"},
])
def test_invalid_labels_never_commit(row, tmp_path):
    path = tmp_path / "labels.json"
    with pytest.raises(ValueError):
        save_judgments("hash", [{"qid": "Q1", "text": "alpha"}], ["1"], [row], path)
    assert not path.exists()

def test_weak_rules_use_text_not_ranking_and_respect_word_boundaries():
    engine = Engine(documents("alpha beta", "alpha betamax", "beta only"), Settings("B"))
    queries = [{"qid": "Q1", "text": "unrelated ranking input", "groups": [["alpha"], ["beta"]]}]
    judgments = weak_judgments(engine, queries, "hash")
    assert judgments["source"] == "weak_rules"
    assert [r["grade"] for r in judgments["judgments"]["Q1"].values()] == [1, 0, 0]
    assert matches_concept("neuroprotective", "neuroprotect")
    assert not matches_concept("betamax", "beta")


def mixed_annotation_example():
    queries = [{"qid": f"Q{i}", "text": "alpha"} for i in range(1, 4)]
    judgments = empty_judgments("hash", queries)
    judgments["judgments"] = {
        "Q2": {"1": {"grade": 0, "reason": "不符意圖"}},
        "Q3": {"1": {"grade": 1, "reason": "符合意圖"},
               "2": {"grade": 0, "reason": "不符意圖"}},
    }
    return queries, judgments


def test_query_status_distinguishes_unknown_negative_only_and_known_relevant():
    queries, judgments = mixed_annotation_example()
    statuses = query_status(queries, judgments)
    assert [row["status"] for row in statuses] == [
        "unjudged", "judged_no_known_relevant", "has_known_relevant"]
    assert [row["exclusion_reason"] for row in statuses] == ["unjudged", "no_known_relevant", ""]
    assert [row["judged_documents"] for row in statuses] == [0, 1, 2]
    assert [row["known_relevant"] for row in statuses] == [0, 0, 1]
    assert [row["included_in_mean"] for row in statuses] == [False, False, True]
    assert all(row["judgment_source"] == "human" for row in statuses)
    assert evaluation_accounting(statuses) == {
        "queries_total": 3, "queries_evaluated": 1, "queries_excluded": 2,
        "queries_excluded_unjudged": 1, "queries_excluded_no_known_relevant": 1}


def test_evaluation_means_reveal_exclusions_without_diluting_included_queries():
    queries, judgments = mixed_annotation_example()
    engine = Engine(documents("alpha beta", "beta only"), Settings("B"))
    rows, summary = evaluate(engine, queries, judgments, 10)
    assert len(rows) == len(summary) == len(METHODS)
    assert {row["qid"] for row in rows} == {"Q3"}
    for row in summary:
        assert row["queries_total"] == 3
        assert row["queries_evaluated"] == 1
        assert row["queries_excluded"] == 2
        assert row["queries_excluded_unjudged"] == 1
        assert row["queries_excluded_no_known_relevant"] == 1
        assert row["precision_at_k"] == 0.1
        assert row["recall_at_k"] == 1


def test_no_evaluable_queries_have_null_means_and_explicit_denominators():
    queries, judgments = mixed_annotation_example()
    judgments["judgments"].pop("Q3")
    engine = Engine(documents("alpha beta", "beta only"), Settings("B"))
    rows, summary = evaluate(engine, queries, judgments)
    assert rows == []
    assert len(summary) == len(METHODS)
    for row in summary:
        assert row["queries_evaluated"] == 0
        assert row["queries_total"] == row["queries_excluded"] == 3
        assert row["queries_excluded_unjudged"] == 2
        assert row["queries_excluded_no_known_relevant"] == 1
        assert all(row[key] is None for key in (
            "precision_at_k", "recall_at_k", "reciprocal_rank", "ndcg_at_k", "judged_at_k"))


def test_experiment_exports_all_query_states_and_accounts_for_missing_means(tmp_path, monkeypatch):
    queries, judgments = mixed_annotation_example()
    judgments["judgments"].pop("Q3")
    monkeypatch.setattr("ir_hw3.experiments.load_queries", lambda: queries)
    engine = Engine(documents("alpha beta", "beta only"), Settings("B"))
    result = run_experiment(engine, {"sha256": "hash"}, output=tmp_path, judgments=judgments)
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["queries_total"] == 3
    assert manifest["queries_evaluated"] == 0
    assert manifest["queries_excluded_unjudged"] == 2
    assert manifest["queries_excluded_no_known_relevant"] == 1
    assert manifest["query_status_counts"] == {
        "unjudged": 2, "judged_no_known_relevant": 1, "has_known_relevant": 0}
    assert "query_status.csv" in manifest["outputs_sha256"]
    with (tmp_path / "query_status.csv").open(encoding="utf-8-sig", newline="") as stream:
        statuses = list(csv.DictReader(stream))
    assert len(statuses) == 3
    assert {row["qid"] for row in statuses} == {"Q1", "Q2", "Q3"}
    assert statuses[1]["exclusion_reason"] == "no_known_relevant"
    assert len(result["query_status"]) == 3
    discussion = (tmp_path / "RQ_DISCUSSION.md").read_text(encoding="utf-8")
    assert "平均指標納入 0 個，排除 3 個" in discussion
    assert "已判讀但尚無已知相關文件 1 個" in discussion
    assert "未計算" in discussion


def test_annotation_csv_round_trip_preserves_source_and_dataset_versions():
    queries = [{"qid": "Q1", "text": "alpha"}]
    rows = [{"qid": "Q1", "pmid": str(index), "grade": grade,
             "reason": "  依據摘要判讀  " if grade >= 0 else "", "title": "閱讀輔助欄位"}
            for index, grade in enumerate((-1, 0, 1, 2), 1)]
    exported = export_judgment_rows(rows, "hash", queries)
    assert all(row["source"] == "human" and row["corpus_sha256"] == "hash" and
               row["queries_sha256"] == fingerprint(queries) for row in exported)
    assert all("source" not in row for row in rows)
    parsed = parse_judgment_csv(csv_rows(exported), "hash", queries, ["1", "2", "3", "4"])
    assert parsed == [{"qid": row["qid"], "pmid": row["pmid"], "grade": row["grade"],
                       "reason": row["reason"].strip()} for row in rows]
    with pytest.raises(ValueError, match="其他來源"):
        export_judgment_rows([{**rows[1], "source": "weak_rules"}], "hash", queries)


@pytest.mark.parametrize("change, message", [
    ({"source": "weak_rules"}, "人工標註來源"),
    ({"source": ""}, "人工標註來源"),
    ({"corpus_sha256": "old-corpus"}, "版本不符"),
    ({"queries_sha256": "old-queries"}, "版本不符"),
    ({"qid": "unknown"}, "未知"),
    ({"pmid": "unknown"}, "未知"),
    ({"grade": "1.5"}, "整數"),
    ({"grade": "True"}, "整數"),
    ({"grade": "NaN"}, "整數"),
    ({"grade": "3"}, "-1、0、1 或 2"),
    ({"grade": "0", "reason": "  "}, "判斷依據"),
    ({"grade": "-1", "reason": "未完成的閱讀筆記"}, "避免遺失註記"),
])
def test_annotation_csv_rejects_bad_rows_even_with_legacy_opt_in(change, message):
    queries = [{"qid": "Q1", "text": "alpha"}]
    valid = export_judgment_rows([{"qid": "Q1", "pmid": "1", "grade": 1, "reason": "摘要證據"}], "hash", queries)[0]
    with pytest.raises(ValueError, match=message):
        parse_judgment_csv(csv_rows([{**valid, **change}]), "hash", queries, ["1"], allow_legacy=True)


def test_annotation_csv_legacy_requires_explicit_opt_in_and_no_metadata_columns():
    queries = [{"qid": "Q1", "text": "alpha"}]
    rows = [{"qid": "Q1", "pmid": "1", "grade": 0, "reason": "摘要不符意圖"}]
    with pytest.raises(ValueError, match="沒有來源與資料版本"):
        parse_judgment_csv(csv_rows(rows), "hash", queries, ["1"])
    assert parse_judgment_csv(csv_rows(rows), "hash", queries, ["1"], allow_legacy=True) == rows
    for partial in ({"source": "human"}, {"corpus_sha256": "hash", "queries_sha256": fingerprint(queries)}):
        with pytest.raises(ValueError, match="版本欄位不完整"):
            parse_judgment_csv(csv_rows([{**rows[0], **partial}]), "hash", queries, ["1"], allow_legacy=True)


def test_annotation_csv_rejects_duplicate_query_document_pairs():
    queries = [{"qid": "Q1", "text": "alpha"}]
    rows = [{"qid": "Q1", "pmid": "1", "grade": 1, "reason": "摘要證據"},
            {"qid": " Q1 ", "pmid": "1 ", "grade": -1, "reason": ""}]
    with pytest.raises(ValueError, match="重複標註"):
        parse_judgment_csv(csv_rows(export_judgment_rows(rows, "hash", queries)), "hash", queries, ["1"])


@pytest.mark.parametrize("data", [
    b"", b"qid,pmid,grade,reason\n", b"qid,pmid,grade\nQ1,1,1\n",
    b"qid,pmid,grade,reason,reason\nQ1,1,1,x,x\n",
    b"qid,pmid,grade,reason\nQ1,1,1\n",
    b"qid,pmid,grade,reason\nQ1,1,1,x,extra\n",
    b'\xff', b'qid,pmid,grade,reason\nQ1,1,1,"unfinished',
])
def test_annotation_csv_rejects_empty_malformed_or_incomplete_content(data):
    with pytest.raises(ValueError):
        parse_judgment_csv(data, "hash", [{"qid": "Q1", "text": "alpha"}], ["1"], allow_legacy=True)
