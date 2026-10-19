"""Offline entry point for corpus verification, search and controlled experiments."""
import argparse
import json
from pathlib import Path
from .core import CONDITIONS, IDF_MODES, METHODS, Engine, Settings
from .corpus import ROOT, load_corpus, sha256, verify_hw2_unchanged
from .evaluation import load_judgments, load_queries
from .experiments import compare_runs, list_runs, run_experiment

def main():
    parser = argparse.ArgumentParser(description="HW3 offline retrieval and evaluation")
    parser.add_argument("--condition", choices=CONDITIONS, default="C")
    parser.add_argument("--idf", choices=IDF_MODES, default="standard")
    parser.add_argument("--snapshot", type=Path, help="Optional sealed corpus directory; defaults to the active 3000-document snapshot")
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--source", action="store_true", help="Also check original HW2 fingerprints (optional)")
    search = commands.add_parser("search")
    search.add_argument("query")
    search.add_argument("--method", choices=METHODS, default="log_tfidf")
    experiment = commands.add_parser("experiment")
    experiment.add_argument("--source", choices=["weak", "human"], default="weak")
    experiment.add_argument("--output", type=Path, help="New or empty directory only; existing results are never overwritten")
    experiment.add_argument("--k", type=int, default=10)
    history = commands.add_parser("history", aliases=["list"], help="List intact completed experiment runs")
    history.add_argument("--source", choices=["weak_rules", "human"])
    history.add_argument("--root", type=Path, help="Reports root (defaults to this project's reports)")
    compare = commands.add_parser("compare", help="Compare two saved runs after checking controlled conditions")
    compare.add_argument("left", type=Path)
    compare.add_argument("right", type=Path)
    args = parser.parse_args()
    if args.command in {"history", "list", "compare"}:
        try:
            result = (compare_runs(args.left, args.right) if args.command == "compare" else
                      list_runs(args.source, root=args.root))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            parser.error(str(exc))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    documents, manifest = load_corpus(args.snapshot) if args.snapshot else load_corpus()
    if args.command == "verify":
        queries = load_queries()
        judgments = load_judgments(manifest["sha256"], queries, documents)
        provenance = json.loads((ROOT / "reports/provenance.json").read_text(encoding="utf-8"))
        copied_changed = [name for name, record in provenance["copied_files"].items()
                          if sha256(ROOT / name) != record["sha256"]]
        result = {"documents": len(documents), "queries": len(queries), "corpus_sha256": manifest["sha256"],
                  "copied_files_changed": copied_changed,
                  "manual_judgments": sum(map(len, judgments["judgments"].values()))}
        if args.source:
            result["hw2_source"] = verify_hw2_unchanged()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if copied_changed or (args.source and result["hw2_source"]["changed"]):
            raise SystemExit(1)
        return
    engine = Engine(documents, Settings(args.condition, args.idf))
    if args.command == "search":
        print(json.dumps(engine.rank(args.query, args.method), ensure_ascii=False, indent=2))
    else:
        if args.k < 1:
            parser.error("--k must be positive")
        judgments = (load_judgments(manifest["sha256"], load_queries(), documents) if args.source == "human" else None)
        try:
            result = run_experiment(engine, manifest, judgments=judgments, output=args.output, k=args.k)
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        print(json.dumps({"output": result["output"], "summary": result["summary"],
                          "normalization_passed": result["normalization_passed"]}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
