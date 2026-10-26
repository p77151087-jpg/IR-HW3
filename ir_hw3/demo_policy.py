"""Process-wide, irreversible read-only policy for the public demonstration."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

from .corpus import ROOT

_ENABLED = False
_CACHE = Path(tempfile.gettempdir()) / "ir-hw3-demo-cache"


class DemoReadOnlyError(PermissionError):
    pass


def is_demo():
    return _ENABLED


def verify_deployment():
    import streamlit as st

    @st.cache_resource(max_entries=1, show_spinner="驗證部署清單與檔案指紋…")
    def check(signature):
        manifest = json.loads((ROOT / "deployment/manifest.json").read_text(encoding="utf-8"))
        payload = json.dumps(manifest["files"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        if hashlib.sha256(payload).hexdigest() != manifest["files_fingerprint_sha256"]:
            raise ValueError("部署清單指紋不符")
        for record in manifest["files"]:
            path = (ROOT / record["path"]).resolve()
            if not path.is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
                raise ValueError("部署檔案缺失或指紋不符：" + record["path"])
        return True

    try:
        manifest = json.loads((ROOT / "deployment/manifest.json").read_text(encoding="utf-8"))
        paths = [ROOT / "deployment/manifest.json", *(ROOT / x["path"] for x in manifest["files"])]
        check(tuple((str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in paths))
    except (ValueError, OSError, KeyError) as exc:
        st.error(f"部署資料不完整：{exc}")
        st.info("請管理者依部署清單補齊檔案；展示版不會重新下載、訓練或覆寫成果。")
        st.stop()


def _blocked(*args, **kwargs):
    raise DemoReadOnlyError("雲端展示模式禁止訓練、下載語料、匯入判讀或保存實驗；請使用本機完整版。")


def _audit(event, args):
    """Backstop against writes, including stale references and direct Path calls."""
    if not _ENABLED:
        return
    paths = ()
    if event == "open":
        path, mode, flags = args
        if (mode and any(c in mode for c in "wax+")) or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            paths = (path,)
    elif event in {"os.remove", "os.rmdir", "os.mkdir", "os.chmod", "os.truncate", "os.utime"}:
        paths = args[:1]
    elif event in {"os.rename", "os.link", "os.symlink"}:
        paths = args[:2]
    for path in paths:
        if isinstance(path, (str, bytes, os.PathLike)):
            target = Path(os.fsdecode(path)).resolve()
            if target.is_relative_to(ROOT.resolve()):
                raise DemoReadOnlyError(f"雲端展示模式禁止改寫專案檔案：{target.relative_to(ROOT)}")


def enable_demo():
    """Call before importing the UI; no query parameter/session switch can undo it."""
    global _ENABLED
    if _ENABLED:
        return
    sys.dont_write_bytecode = True
    _CACHE.mkdir(parents=True, exist_ok=True)
    os.environ["MPLCONFIGDIR"] = str(_CACHE / "matplotlib")
    # Load definitions only. None of these modules trains or fetches on import.
    from . import evaluation, experiments, acquisition, word_association, embedding_training
    from gensim.models import Word2Vec
    targets = [
        (evaluation, ("atomic_json", "save_judgments", "parse_judgment_csv")),
        (experiments, ("run_experiment",)),
        (acquisition, ("cached_request", "expand_snapshot")),
        (word_association, ("write_json", "write_csv")),
        (embedding_training, ("train_model", "train_run")),
    ]
    for module, names in targets:
        for name in names:
            setattr(module, name, _blocked)
    word_association.TfidfWords.save = _blocked
    Word2Vec.train = _blocked
    _ENABLED = True
    sys.addaudithook(_audit)
