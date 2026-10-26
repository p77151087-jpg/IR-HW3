"""Create/verify four TF/DF anchors and the six pairs requested by the user."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
import shutil

from ir_hw3.core import Engine
from ir_hw3.corpus import ROOT, load_corpus, sha256
from ir_hw3.evaluation import fingerprint
from ir_hw3.query_design import CASE_ORDER, VERSION, classify, term_profile

ANCHORS = [
    ("GLP-1", "高 TF／高 DF", ["glp-1", "glucagon-like peptide-1", "glucagon-like peptide 1"], "GLP-1 相關摘要"),
    ("receptor", "低 TF／高 DF", ["receptor", "receptors"], "受體相關摘要"),
    ("MASLD", "高 TF／低 DF", ["masld", "metabolic dysfunction-associated steatotic liver disease", "metabolic dysfunction associated steatotic liver disease"], "代謝功能障礙相關脂肪性肝病摘要"),
    ("hypertension", "低 TF／低 DF", ["hypertension", "hypertensive", "high blood pressure"], "高血壓相關摘要"),
]


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def main():
    documents, manifest = load_corpus()
    engine = Engine(documents)
    profiles = []
    for index, (term, category, aliases, intent) in enumerate(ANCHORS, 1):
        profile = term_profile(engine, term)
        if classify(profile) != category:
            raise ValueError(f"{term} 不再符合固定分類；不可直接沿用此查詢設計。")
        profiles.append({"type": index, "category": category, **profile})
    queries = []
    for index, case in enumerate(CASE_ORDER, 1):
        queries.append({"qid": f"Q{index:02d}", "text": " ".join(ANCHORS[i-1][0] for i in case),
                        "intent": "；".join(ANCHORS[i-1][3] for i in case) + ("（需同時涵蓋概念）" if len(case)>1 else ""),
                        "groups": [ANCHORS[i-1][2] for i in case], "design_version": VERSION,
                        "case": " 搭配 ".join(map(str, case)), "types": list(case)})
    query_hash = fingerprint(queries)
    design = {"schema_version": 1, "design_version": VERSION,
              "description": "Four TF/DF classes followed by all six unordered pairs; no ranking/label-based term selection.",
              "corpus_sha256": manifest["sha256"], "documents": engine.n,
              "settings": {"condition": "C", "idf": "standard"}, "queries_sha256": query_hash,
              "tf_definition": "Actual within-document TF; classification summarizes mean TF among documents containing the term.",
              "thresholds": {"high_mean_positive_tf_min": 3, "low_mean_positive_tf_max": 1.6,
                             "high_df_fraction_min": 0.2, "low_df_fraction_max": 0.05},
              "anchors": profiles,
              "limitations": ["Teaching-case thresholds are not universal high/low TF definitions.",
                              "Conditional mean TF does not imply the same TF in every document; CF is not a document TF.",
                              "Query terms each occur once; this is document TF/DF design, not repeated query-TF manipulation.",
                              "Aliases for relevance rules do not alter the exact-token statistics used for classification."]}
    rules = {"schema_version": 1, "rule_version": "pubmed-tfdf-v1", "queries_sha256": query_hash,
             "sources": ["https://pubmed.ncbi.nlm.nih.gov/help/#mesh-terms-mh"],
             "policy": "All query concept groups must match metadata; otherwise independently apply all abstract concept groups. No rankings/scores are read. Binary automatic proxy labels, not human relevance.",
             "fields": ["mesh", "chemical", "supplementary_concept", "keyword"],
             "matching": "NFKC/casefold with whole normalized token sequences; no MeSH tree expansion.",
             "shared_groups": {}, "queries": {q["qid"]: {"text": q["text"], "groups": q["groups"]} for q in queries}}
    targets = {ROOT / "data/queries.json": queries,
               ROOT / "data/query_design/tfdf-v1.json": design,
               ROOT / "data/reference_rules/pubmed-tfdf-v1.json": rules}
    active = ROOT / "data/queries.json"
    old = json.loads(active.read_text(encoding="utf-8"))
    if fingerprint(old) != query_hash:
        if any(q.get("design_version") == VERSION for q in old):
            raise ValueError("既有同版本查詢被修改，拒絕覆寫；請另建版本。")
        archive = ROOT / "data/query_sets" / fingerprint(old)
        archive.mkdir(parents=True, exist_ok=True)
        archived = archive / "queries.json"
        if archived.exists() and archived.read_bytes() != active.read_bytes():
            raise ValueError("查詢封存已存在但內容不同。")
        if not archived.exists():
            shutil.copy2(active, archived)
        old_rule = ROOT / "data/reference_rules/pubmed-v1.json"
        archived_rule = archive / "reference_rules.json"
        if not archived_rule.exists():
            shutil.copy2(old_rule, archived_rule)
        (archive / "manifest.json").write_bytes(encoded({"queries_sha256": fingerprint(old),
            "queries_file_sha256": sha256(archived), "reference_rules_file_sha256": sha256(archived_rule),
            "description": "Prior biomedical-intent Q01-Q10 preserved before TF/DF query replacement."}))
    for path, value in targets.items():
        content = encoded(value)
        if path.exists() and path != active and path.read_bytes() != content:
            raise ValueError(f"版本證據已存在且不同，拒絕覆寫：{path}")
        if not path.exists() or path.read_bytes() != content:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    print(json.dumps({"queries_sha256": query_hash, "queries": queries, "anchors": profiles}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
