"""Create/verify a deterministic deployment allowlist, without editing old runs."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ir_hw3.cloud_results import ASSOCIATION_RUN, EVALUATION_RUN
from ir_hw3.corpus import load_corpus, SNAPSHOT, ORIGINAL_SNAPSHOT, sha256
from ir_hw3.experiments import _read_run
from ir_hw3.word_association import AssociationRun

MANIFEST = ROOT / "deployment/manifest.json"


def selected_files():
    names = {"app.py", "cloud_app.py", "README.md", "AGENTS.md", ".gitignore", ".gitattributes",
             ".streamlit/config.toml", "requirements.txt", "requirements-lock.txt", "pyproject.toml",
             "start_hw3.cmd", "stop_background_hw3.cmd"}
    names.add("docs/Homework-3.pdf")
    for folder, pattern in [("ir_hw1", "*.py"), ("ir_hw3", "*.py"), ("ir_hw3", "*.js"),
                            ("scripts", "*.py"), ("scripts", "*.ps1"), ("tests", "*.py"),
                            ("resources", "*.json"), ("docs", "*.md"), ("deployment", "*.md")]:
        names.update(p.relative_to(ROOT).as_posix() for p in (ROOT / folder).glob(pattern))
    names.add("data/queries.json")
    names.update(p.relative_to(ROOT).as_posix() for p in (ROOT / "deployment").glob("*.json") if p.name != "manifest.json")
    for folder in ["data/reference_rules", "data/query_design", SNAPSHOT.relative_to(ROOT).as_posix(),
                   ORIGINAL_SNAPSHOT.relative_to(ROOT).as_posix(), ASSOCIATION_RUN, EVALUATION_RUN]:
        names.update(p.relative_to(ROOT).as_posix() for p in (ROOT / folder).rglob("*") if p.is_file())
    for name in ["HW3_REPORT_TFDF.md", "HW3_REPORT_BM25.md"]:
        names.add("reports/" + name)
    return sorted(names)


def build():
    load_corpus(SNAPSHOT)
    load_corpus(ORIGINAL_SNAPSHOT)
    AssociationRun(ROOT / ASSOCIATION_RUN)
    _read_run(ROOT / EVALUATION_RUN)
    entries = []
    for name in selected_files():
        path = ROOT / name
        if not path.is_file() or path.stat().st_size >= 100 * 2**20:
            raise ValueError(f"Missing/oversized deployment file: {name}")
        entries.append({"path": name, "bytes": path.stat().st_size, "sha256": sha256(path)})
    payload = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    result = {"schema_version": 1, "entrypoint": "cloud_app.py", "python": "3.12",
              "association_run": ASSOCIATION_RUN, "evaluation_run": EVALUATION_RUN,
              "policy": "Only these files plus deployment/manifest.json are published in the deployment branch; original run bytes/manifests are unchanged.",
              "files": entries, "total_bytes": sum(x["bytes"] for x in entries),
              "files_fingerprint_sha256": hashlib.sha256(payload).hexdigest()}
    MANIFEST.parent.mkdir(exist_ok=True)
    MANIFEST.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return result


def verify(*, tracked=False):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    payload = json.dumps(manifest["files"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    if hashlib.sha256(payload).hexdigest() != manifest["files_fingerprint_sha256"]:
        raise ValueError("Deployment inventory fingerprint mismatch")
    for item in manifest["files"]:
        path = (ROOT / item["path"]).resolve()
        if (not path.is_relative_to(ROOT) or not path.is_file() or
                path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]):
            raise ValueError("Deployment integrity failure: " + item["path"])
    if tracked:
        actual = set(subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")) - {""}
        expected = {x["path"] for x in manifest["files"]} | {"deployment/manifest.json"}
        if actual != expected:
            raise ValueError(f"Git inventory mismatch: extra={sorted(actual-expected)}, missing={sorted(expected-actual)}")
    # Retain independent original per-run hash validation too.
    load_corpus(SNAPSHOT)
    load_corpus(ORIGINAL_SNAPSHOT)
    AssociationRun(ROOT / ASSOCIATION_RUN)
    _read_run(ROOT / EVALUATION_RUN)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--tracked", action="store_true")
    args = parser.parse_args()
    result = verify(tracked=args.tracked) if args.verify else build()
    print(json.dumps({key: result[key] for key in ["total_bytes", "files_fingerprint_sha256"]}))
    print(f"{len(result['files'])} files; largest {max(x['bytes'] for x in result['files']) / 2**20:.2f} MiB")
