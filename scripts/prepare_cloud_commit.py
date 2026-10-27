"""Build a reviewed deployment commit via an isolated index; preserve main/files."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from build_cloud_bundle import verify

BRANCH = "codex/streamlit-cloud"
REMOTE = "https://github.com/p77151087-jpg/IR-HW3.git"


def git(*args, env=None, input=None):
    return subprocess.check_output(["git", *args], cwd=ROOT, env=env, input=input).decode().strip()


def main():
    if git("remote", "get-url", "origin") != REMOTE:
        raise ValueError("Wrong repository destination")
    manifest = verify()
    names = [item["path"] for item in manifest["files"]] + ["deployment/manifest.json"]
    base = git("rev-parse", "refs/heads/main")
    existing = subprocess.run(["git", "rev-parse", "--verify", f"refs/heads/{BRANCH}"], cwd=ROOT, capture_output=True, text=True)
    parent = existing.stdout.strip() if existing.returncode == 0 else base
    with tempfile.TemporaryDirectory(prefix="cloud-index-", dir=ROOT / "tmp") as folder:
        env = os.environ.copy()
        env["GIT_INDEX_FILE"] = str(Path(folder) / "index")
        paths = Path(folder) / "paths"
        paths.write_bytes(b"\0".join(name.encode() for name in names) + b"\0")
        git("read-tree", "--empty", env=env)
        git("add", "-f", "--pathspec-from-file=" + str(paths), "--pathspec-file-nul", env=env)
        subprocess.check_call([sys.executable, "-B", "-X", "utf8", str(ROOT / "scripts/build_cloud_bundle.py"), "--verify", "--tracked"], cwd=ROOT, env=env)
        tree = git("write-tree", env=env)
        message = ("Deploy read-only HW3 demonstration to Streamlit Cloud\n\n"
                   "Preserve C preprocessing, formulas, fixed corpora, complete four-model run and historical hashes. "
                   "Publish only the verified allowlist; main history and local archives are retained.\n")
        commit = git("commit-tree", tree, "-p", parent, input=message.encode())
        git("update-ref", f"refs/heads/{BRANCH}", commit, parent if existing.returncode == 0 else "0" * 40)
    print(json.dumps({"branch": BRANCH, "commit": commit, "parent": parent, "main_unchanged": git("rev-parse", "refs/heads/main") == base, "files": len(names)}))


if __name__ == "__main__":
    main()
