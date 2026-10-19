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
matrix = np.zeros((len(ids), len(vocabulary)), dtype=np.float64)
for i, doc_id in enumerate(ids):
    for term, tf in engine.counts[doc_id].items():
        matrix[i, positions[term]] = tf
idf = np.log(len(ids) / np.count_nonzero(matrix, axis=0))
maximum_error, checked = 0.0, 0
for method in METHODS:
    base = matrix.copy()
    if method in {"log_tf", "log_tfidf"}:
        nonzero = base > 0
        base[nonzero] = 1 + np.log(base[nonzero])
    elif method == "idf":
        base = (base > 0).astype(float)
    if method in {"idf", "tfidf", "log_tfidf"}:
        base *= idf
    document_norm = np.linalg.norm(base, axis=1)
    for query in queries:
        counts = Counter(terms(query["text"], engine.settings.condition))
        vector = np.array([counts[term] for term in vocabulary], dtype=np.float64)
        if method in {"log_tf", "log_tfidf"}:
            nonzero = vector > 0
            vector[nonzero] = 1 + np.log(vector[nonzero])
        elif method == "idf":
            vector = (vector > 0).astype(float)
        if method in {"idf", "tfidf", "log_tfidf"}:
            vector *= idf
        denominator = document_norm * np.linalg.norm(vector)
        reference = np.divide(base @ vector, denominator, out=np.zeros(len(ids)), where=denominator != 0)
        actual = {row["pmid"]: row["score"] for row in engine.rank(query["text"], method, limit=None)}
        error = max(abs(actual.get(doc_id, 0) - reference[i]) for i, doc_id in enumerate(ids))
        if error >= 1e-10:
            raise AssertionError((query["qid"], method, error))
        maximum_error = max(maximum_error, error)
        checked += len(ids)

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
