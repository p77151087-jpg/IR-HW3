"""Document-only L2 comparison with unchanged query weights and standard cosine."""
import math

from .core import VECTOR_METHODS

DOCUMENT_L2_SCOPE = "documents_only"


def normalization_comparison(engine, query, method):
    if method not in VECTOR_METHODS:
        raise ValueError("L2 前後比較只適用五種向量方法，BM25 不適用。")
    before = engine.rank(query, method, limit=None, scoring="cosine")
    _, query_weights, _ = engine.query(query, method)
    original_query_weights = dict(query_weights)
    vectors, norms = engine.vectors(method)

    def norm(values):
        return math.sqrt(sum(value * value for value in values))

    query_norm = norm(query_weights.values())
    scores, document_norms_after, document_dots = {}, {}, {}
    if query_norm:
        candidates = {pid for term, weight in query_weights.items() if weight for pid in engine.postings[term]}
        for pid in candidates:
            if not norms[pid]:
                continue
            # Only d is rescaled. q retains its original weighting and repeated TF.
            unit_document = {term: weight / norms[pid] for term, weight in vectors[pid].items()}
            unit_norm = norm(unit_document.values())
            dot = sum(weight * unit_document.get(term, 0.0) for term, weight in query_weights.items())
            document_norms_after[pid] = unit_norm
            document_dots[pid] = dot
            scores[pid] = max(0.0, min(1.0, dot / (query_norm * unit_norm))) if unit_norm else 0.0
    # Reuse the established precision and PMID tie-break without changing Engine.
    after = engine._ordered(scores, None)
    query_norm_after = norm(query_weights.values())
    old, new = ({row["pmid"]: row for row in ranking} for ranking in (before, after))
    ids = list(dict.fromkeys(row["pmid"] for row in before[:10] + after[:10]))
    rows = [{"normalization_scope": DOCUMENT_L2_SCOPE, "pmid": pid,
             "rank_before": old.get(pid, {}).get("rank"), "rank_after": new.get(pid, {}).get("rank"),
             "cosine_before": old.get(pid, {}).get("score"), "cosine_after": new.get(pid, {}).get("score"),
             "query_norm_before": query_norm, "query_norm_after": query_norm_after,
             "document_norm_before": norms[pid], "document_norm_after": document_norms_after.get(pid, 0.0),
             "document_l2_dot": document_dots.get(pid), "title": engine.documents[pid].title} for pid in ids]
    return {"normalization_scope": DOCUMENT_L2_SCOPE, "rows": rows,
            "query_unchanged": query_weights == original_query_weights,
            "query_norm_before": query_norm, "query_norm_after": query_norm_after,
            "retrieved_before": len(before), "retrieved_after": len(after),
            "same_ranking": list(old) == list(new) if old or new else None,
            "max_score_difference": max((abs(old.get(pid, {}).get("score", 0.0) - new.get(pid, {}).get("score", 0.0))
                                         for pid in old.keys() | new.keys()), default=None)}
