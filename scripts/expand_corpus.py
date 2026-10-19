"""Explicitly requested 1000 -> 3000 expansion; HW2 remains read-only."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
from ir_hw3.acquisition import expand_snapshot
from ir_hw3.corpus import ROOT

if __name__ == "__main__":
    manifest = expand_snapshot(ROOT / "data/corpus/glp1-1000-20260929",
                               ROOT / "data/corpus/glp1-3000-20261015")
    print(json.dumps({"status": manifest["status"], "counts": manifest["counts"],
                      "sha256": manifest["sha256"]}, ensure_ascii=False, indent=2))
