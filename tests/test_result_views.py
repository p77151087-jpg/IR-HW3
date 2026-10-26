from collections import Counter
from copy import deepcopy
from types import SimpleNamespace

import pytest

from ir_hw3.core import METHODS, VECTOR_METHODS, Engine
from ir_hw3.result_views import ranking_details, ranking_overview, overview_html, top10_changes, normalization_comparison


def ranking(*doc_ids):
    return [{"rank": rank, "pmid": doc_id, "score": 1 / rank, "title": "Article " + doc_id}
            for rank, doc_id in enumerate(doc_ids, 1)]


def documents(*doc_ids):
    return {doc_id: SimpleNamespace(title="Article " + doc_id) for doc_id in doc_ids}


def overview_engine(*doc_ids):
    counts = {doc_id: Counter(alpha=int(doc_id), beta=2) for doc_id in doc_ids}
    return SimpleNamespace(documents=documents(*doc_ids), counts=counts,
                           lengths={doc_id: sum(row.values()) for doc_id, row in counts.items()})


def test_details_count_unique_query_terms_and_preserve_raw_ranking():
    engine = SimpleNamespace(counts={"1": Counter(alpha=2, beta=1), "2": Counter(beta=3, gamma=2)},
                             lengths={"1": 3, "2": 5})
    original = ranking("1", "2")
    saved = deepcopy(original)
    rows = ranking_details(engine, ["alpha", "alpha", "beta", "unknown"], original)
    assert [row["query_term_hits"] for row in rows] == [3, 3]
    assert [row["abstract_length_tokens"] for row in rows] == [3, 5]
    assert original == saved
    for row, raw in zip(rows, original):
        assert {key: row[key] for key in raw} == raw
    assert ranking_details(engine, [], original)[0]["query_term_hits"] == 0
    assert ranking_details(engine, ["alpha"], []) == []


def test_overview_aligns_documents_and_shows_only_rank_or_outside_marker():
    rankings = {method: ranking("1", "2") for method in METHODS}
    rankings["bm25"] = ranking("3", "1")
    original = deepcopy(rankings)
    rows = ranking_overview(rankings, overview_engine("1", "2", "3"), ["alpha", "alpha", "unknown"])
    assert [row["pmid"] for row in rows] == ["1", "2", "3"]
    assert all("Top 10 方法數" not in row for row in rows)
    assert [row["query_term_hits"] for row in rows] == [1, 2, 3]
    assert [row["abstract_length_tokens"] for row in rows] == [3, 4, 5]
    assert rankings == original
    assert rows[0]["原始 TF"] == "1" and rows[0]["BM25"] == "2"
    assert rows[1]["BM25"] == "—" and rows[2]["原始 TF"] == "—"
    assert all(row[label] == "—" or row[label].isdigit() for row in rows for label in METHODS.values())
    assert ranking_overview({method: [] for method in METHODS}, overview_engine(), []) == []


def test_overview_ties_use_numeric_pmid_and_omit_documents_beyond_tenth():
    rows = ranking_overview({"tf": ranking("10", "20"), "bm25": ranking("2", "20")}, overview_engine("2", "10", "20"), ["alpha"])
    assert [row["pmid"] for row in rows] == ["20", "2", "10"]
    many = ranking(*(str(i) for i in range(1, 12)))
    assert len(ranking_overview({"tf": many}, overview_engine(*(str(i) for i in range(1, 12))), ["alpha"])) == 10


def test_overview_html_keeps_complete_escaped_titles_and_numeric_statistics():
    from html import escape
    engine = overview_engine("1")
    title = '<script>alert("title")</script> & ' + "long title " * 80
    engine.documents["1"].title = title
    rows = ranking_overview({method: ranking("1") for method in METHODS}, engine, ["alpha", "beta", "alpha"])
    rendered = overview_html(rows)
    assert escape(title) in rendered
    assert rendered.count("<script>") == 1
    assert '<script>alert("title")</script>' not in rendered
    assert "詞命中數" in rendered and "文章長度" in rendered
    assert "Top 10 方法數" not in rendered
    assert rows[0]["query_term_hits"] == 3 and rows[0]["abstract_length_tokens"] == 3


@pytest.mark.parametrize("method", list(VECTOR_METHODS))
def test_l2_comparison_matches_independent_full_vector_norms_and_cosines(method):
    import numpy as np
    from test_core import documents as text_documents
    engine = Engine(text_documents("alpha alpha beta gamma gamma gamma", "alpha beta beta delta",
                                   "delta delta gamma", "delta gamma epsilon"))
    counts = np.array([[2, 1, 0, 0, 3], [1, 2, 1, 0, 0], [0, 0, 2, 0, 1], [0, 0, 1, 1, 1]], dtype=float)
    query_counts = np.array([2, 1, 0, 0, 0], dtype=float)
    idf = np.log10(4 / (counts > 0).sum(axis=0))

    def weighted(raw):
        values = raw.copy()
        if method == "idf":
            values = (values > 0).astype(float)
        elif method in {"log_tf", "log_tfidf"}:
            present = values > 0
            values[present] = 1 + np.log10(values[present])
        if method in {"idf", "tfidf", "log_tfidf"}:
            values *= idf
        return values

    matrix, q = weighted(counts), weighted(query_counts)
    norms, qnorm = np.linalg.norm(matrix, axis=1), np.linalg.norm(q)
    cosines = matrix @ q / (norms * qnorm)
    original = engine.rank("alpha alpha beta unknown", method, limit=None)
    result = normalization_comparison(engine, "alpha alpha beta unknown", method)
    assert result["same_ranking"] is True and result["max_score_difference"] < 1e-12
    assert result["retrieved_before"] == result["retrieved_after"] == 2
    assert result["query_norm_before"] == pytest.approx(qnorm)
    assert result["normalization_scope"] == "documents_only" and result["query_unchanged"]
    assert result["query_norm_after"] == pytest.approx(qnorm)
    assert qnorm != pytest.approx(1)  # This query distinguishes document-only from both-vector L2.
    for row in result["rows"]:
        i = int(row["pmid"]) - 1
        assert row["rank_before"] == row["rank_after"]
        assert row["cosine_before"] == pytest.approx(cosines[i])
        assert row["cosine_after"] == pytest.approx(cosines[i])
        assert row["document_norm_before"] == pytest.approx(norms[i])
        assert row["document_norm_after"] == pytest.approx(1)
        assert row["query_norm_before"] == row["query_norm_after"] == pytest.approx(qnorm)
        assert row["document_l2_dot"] == pytest.approx((matrix[i] / norms[i]) @ q)
        assert row["document_l2_dot"] != pytest.approx(row["cosine_after"])
    assert engine.rank("alpha alpha beta unknown", method, limit=None) == original


@pytest.mark.parametrize("query,method", [("", "tf"), ("the and", "tf"), ("unknown", "tf"), ("alpha", "idf")])
def test_l2_comparison_keeps_zero_vectors_unretrieved(query, method):
    from test_core import documents as text_documents
    result = normalization_comparison(Engine(text_documents("alpha", "alpha")), query, method)
    assert result["rows"] == [] and result["same_ranking"] is None
    assert result["max_score_difference"] is None
    assert result["query_norm_before"] == result["query_norm_after"] == 0
    assert result["normalization_scope"] == "documents_only" and result["query_unchanged"]


def test_l2_comparison_excludes_bm25():
    from test_core import documents as text_documents
    with pytest.raises(ValueError, match="BM25"):
        normalization_comparison(Engine(text_documents("alpha")), "alpha", "bm25")


def test_changes_separate_shared_entering_exiting_and_explain_direction():
    old, new = ranking("1", "2", "3", "4"), ranking("3", "2", "1", "5")
    shared, entered, exited = top10_changes(old, new, documents("1", "2", "3", "4", "5"))
    assert [(row["pmid"], row["baseline_rank"], row["compared_rank"], row["movement"]) for row in shared] == [
        ("3", 3, 1, "↑ 上升 2 名"), ("2", 2, 2, "名次相同"), ("1", 1, 3, "↓ 下降 2 名")]
    assert entered == [{"compared_rank": 4, "pmid": "5", "title": "Article 5"}]
    assert exited == [{"baseline_rank": 4, "pmid": "4", "title": "Article 4"}]
    assert all(value is not None for group in (shared, entered, exited) for row in group for value in row.values())


@pytest.mark.parametrize("old,new,counts", [([], [], (0, 0, 0)),
    (ranking("1"), ranking("1"), (1, 0, 0)), (ranking("1"), ranking("2"), (0, 1, 1)),
    ([], ranking("1"), (0, 1, 0)), (ranking("1"), [], (0, 0, 1))])
def test_changes_empty_identical_and_disjoint_rankings(old, new, counts):
    groups = top10_changes(old, new, documents("1", "2"))
    assert tuple(map(len, groups)) == counts
