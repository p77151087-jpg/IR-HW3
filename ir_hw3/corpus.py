"""Read-only sealed HW2 snapshot loading, adapted without acquisition/UI code."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from ir_hw1.models import Document

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_SNAPSHOT = ROOT / "data/corpus/glp1-1000-20260929"
SNAPSHOT = ROOT / "data/corpus/glp1-3000-20261015"

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def load_corpus(root: Path = SNAPSHOT) -> tuple[dict[str, Document], dict]:
    root = Path(root)
    manifest = json.loads((root / "snapshot.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "complete" or manifest.get("schema_version") != 1:
        raise ValueError("語料快照未完成或版本不符。")
    files = [("abstracts.jsonl", manifest["sha256"]),
             ("selection.json", manifest["selection_sha256"])]
    files.extend((entry["file"], entry["sha256"]) for entry in manifest["raw_files"])
    for name, expected in files:
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file() or sha256(path) != expected:
            raise ValueError(f"語料完整性驗證失敗：{name}")
    documents = {}
    for line in (root / "abstracts.jsonl").read_text(encoding="utf-8").splitlines():
        document = Document.from_dict(json.loads(line))
        if not document.pmid or document.pmid in documents:
            raise ValueError("語料包含空白或重複 PMID。")
        if document.language != "eng" or not abstract_text(document).strip():
            raise ValueError(f"PMID {document.pmid} 不是英文非空摘要。")
        documents[document.pmid] = document
    if list(documents) != manifest["selected_pmids"] or len(documents) != manifest["counts"]["selected"]:
        raise ValueError("語料數量或 PMID 順序與快照不符。")
    return documents, manifest

def abstract_text(document: Document) -> str:
    return "\n".join(block.text for block in document.blocks if block.kind == "abstract")

def verify_hw2_unchanged() -> dict:
    provenance = json.loads((ROOT / "reports/provenance.json").read_text(encoding="utf-8"))
    source = Path(provenance["source_root"])
    changed = [name for name, expected in provenance["protected_source_files"].items()
               if not (source / name).is_file() or sha256(source / name) != expected]
    return {"checked": len(provenance["protected_source_files"]), "changed": changed,
            "source_available": source.exists()}
