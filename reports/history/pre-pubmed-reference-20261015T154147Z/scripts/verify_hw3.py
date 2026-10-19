"""Independent NumPy cosine reference and byte-for-byte repeatability check."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collections import Counter
import json
import math
import numpy as np
from ir_hw3.core import Engine, METHODS, terms
from ir_hw3.corpus import ROOT, load_corpus, sha256, verify_hw2_unchanged
from ir_hw3.evaluation import atomic_json, load_queries
from ir_hw3.experiments import run_experiment, weak_judgments

documents, manifest = load_corpus()
engine = Engine(documents)
queries = load_queries()
vocabulary = sorted(engine.df)
positions = {term: i for i, term in enumerate(vocabulary)}
ids = list(engine.documents)
# Bounded dense reference blocks avoid holding two full N x vocabulary arrays
# after corpus expansion. NumPy still checks every document/query/method score.
df = np.zeros(len(vocabulary), dtype=np.float64)
for counts in engine.counts.values():
    for term in counts:
        df[positions[term]] += 1
idf = np.log(len(ids) / df)
query_counts = [Counter(terms(query["text"], engine.settings.condition)) for query in queries]
query_matrix = np.array([[counts[term] for term in vocabulary] for counts in query_counts], dtype=np.float64)
maximum_error, checked = 0.0, 0
for method in METHODS:
    def weighted(matrix):
        base = matrix.copy()
        if method in {"log_tf", "log_tfidf"}:
            nonzero = base > 0
            base[nonzero] = 1 + np.log(base[nonzero])
        elif method == "idf":
            base = (base > 0).astype(float)
        if method in {"idf", "tfidf", "log_tfidf"}:
            base *= idf
        return base
    vectors = weighted(query_matrix)
    query_norms = np.linalg.norm(vectors, axis=1)
    actual = [{row["pmid"]: row["score"] for row in engine.rank(query["text"], method, limit=None)} for query in queries]
    for offset in range(0, len(ids), 128):
        batch = ids[offset:offset + 128]
        counts = np.zeros((len(batch), len(vocabulary)), dtype=np.float64)
        for row, doc_id in enumerate(batch):
            for term, tf in engine.counts[doc_id].items():
                counts[row, positions[term]] = tf
        base = weighted(counts)
        denominator = np.linalg.norm(base, axis=1)[:, None] * query_norms[None, :]
        reference = np.divide(base @ vectors.T, denominator,
                              out=np.zeros((len(batch), len(queries))), where=denominator != 0)
        observed = np.array([[scores.get(doc_id, 0) for scores in actual] for doc_id in batch])
        error = float(np.max(np.abs(observed - reference)))
        if error >= 1e-10:
            raise AssertionError((offset, method, error))
        maximum_error = max(maximum_error, error)
        checked += len(batch) * len(queries)

labels = weak_judgments(engine, queries, manifest["sha256"])
first = run_experiment(engine, manifest, judgments=labels)
second = run_experiment(engine, manifest, judgments=labels)
same = {}
for name in first["manifest"]["outputs_sha256"]:
    same[name] = sha256(Path(first["output"]) / name) == sha256(Path(second["output"]) / name)
if not all(same.values()) or not first["normalization_passed"]:
    raise AssertionError("Repeatability or normalization mismatch")
source = verify_hw2_unchanged()
if source["changed"]:
    raise AssertionError(source)
result = {"documents": len(ids), "queries": len(queries), "methods": len(METHODS),
          "independent_cosine_scores_checked": checked, "maximum_cosine_error": maximum_error,
          "repeatability": same, "normalization_passed": first["normalization_passed"],
          "hw2_source": source, "judgment_source": "weak_rules",
          "settings": {"condition": engine.settings.condition, "idf": engine.settings.idf},
          "runs": [{"output": run["output"], "run_id": run["manifest"]["run_id"],
                    "manifest_sha256": sha256(Path(run["output"]) / "manifest.json")}
                   for run in (first, second)]}
atomic_json(ROOT / "reports/verification.json", result)
print(json.dumps(result, ensure_ascii=False, indent=2))
