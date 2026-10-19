"""Measure backend latency without changing retrieval or manual judgments."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datetime import datetime, timezone
import json
import platform
from statistics import median
from time import perf_counter
from uuid import uuid4

from ir_hw3.core import Engine, Settings
from ir_hw3.corpus import ROOT, load_corpus, sha256
from ir_hw3.evaluation import atomic_json, evaluate, fingerprint, load_queries
from ir_hw3.experiments import weak_judgments


def measured(function):
    started = perf_counter()
    result = function()
    return result, perf_counter() - started


def main():
    loads = []
    for _ in range(3):
        (documents, manifest), seconds = measured(load_corpus)
        loads.append(seconds)
    queries = load_queries()
    rows, labels = [], None
    # Process caches are shared. These are backend timings, not cold-browser or
    # independent-process benchmarks; the measurement scope is saved below.
    for condition in ("C", "B", "D"):
        for idf in ("standard", "smooth"):
            engine, build = measured(lambda: Engine(documents, Settings(condition, idf)))
            if labels is None:
                labels = weak_judgments(engine, queries, manifest["sha256"])
            ranking, first_search = measured(lambda: engine.rank(queries[0]["text"], "log_tfidf"))
            searches = []
            for _ in range(5):
                repeated, seconds = measured(lambda: engine.rank(queries[0]["text"], "log_tfidf"))
                if repeated != ranking:
                    raise AssertionError("Repeated search changed its ranking or scores")
                searches.append(seconds)
            (_, summary), batch = measured(lambda: evaluate(engine, queries, labels))
            rows.append({"condition": condition, "idf": idf, "engine_build_seconds": build,
                         "first_search_seconds": first_search, "warm_search_median_seconds": median(searches),
                         "five_methods_ten_queries_evaluation_seconds": batch,
                         "queries_evaluated": summary[0]["queries_evaluated"]})
    now = datetime.now(timezone.utc)
    path = ROOT / "reports/performance" / (now.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8] + ".json")
    sources = [ROOT / "scripts/profile_hw3.py", ROOT / "ir_hw1/preprocessing.py",
               ROOT / "ir_hw1/models.py", ROOT / "resources/stopwords.json",
               *sorted((ROOT / "ir_hw3").glob("*.py"))]
    report = {"created_at_utc": now.isoformat(), "python": platform.python_version(),
              "scope": "Single-process backend wall times; shared preprocessing caches; no browser latency. "
                       "Engine build includes preprocessing/indexing; first search builds log_tfidf vectors; "
                       "batch evaluation may build other methods' vectors. No optimization applied.",
              "documents": len(documents), "queries": len(queries), "judgment_source": "weak_rules",
              "corpus_sha256": manifest["sha256"], "queries_sha256": fingerprint(queries),
              "source_sha256": {p.relative_to(ROOT).as_posix(): sha256(p) for p in sources},
              "load_corpus_seconds": loads, "load_corpus_median_seconds": median(loads), "settings": rows}
    atomic_json(path, report)
    print(json.dumps({"output": str(path), **report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
