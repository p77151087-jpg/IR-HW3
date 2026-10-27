"""Independent PCA geometry and t-SNE probability/objective checks."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import argparse
import json

import numpy as np

from ir_hw3.association_projection import compare_word_maps
from ir_hw3.corpus import ROOT, sha256
from ir_hw3.word_association import AssociationRun


def tsne_reference(unit, xy, perplexity):
    """Independent entropy bisection and Student-t KL, checked against the pinned library."""
    from scipy.spatial.distance import pdist, squareform
    from sklearn.manifold._t_sne import _joint_probabilities, _kl_divergence

    distances = squareform(pdist(unit, "sqeuclidean")).astype(np.float32)
    n = len(unit)
    conditional = np.zeros((n, n))
    for i in range(n):
        mask = np.arange(n) != i
        row = distances[i, mask].astype(float)
        beta, lower, upper = 1.0, -np.inf, np.inf
        for _ in range(100):
            weights = np.exp(-row * beta)
            total = float(weights.sum()) or 1e-8
            difference = np.log(total) + beta * np.dot(row, weights) / total - np.log(perplexity)
            if abs(difference) <= 1e-5:
                break
            if difference > 0:
                lower = beta
                beta = (beta + upper) / 2 if np.isfinite(upper) else beta * 2
            else:
                upper = beta
                beta = (beta + lower) / 2 if np.isfinite(lower) else beta / 2
        conditional[i, mask] = weights / total
    reference = conditional + conditional.T
    reference /= reference.sum()
    library = _joint_probabilities(distances, perplexity, 0)
    affinity_error = float(np.max(np.abs(squareform(reference) - library)))
    low = 1 / (1 + squareform(pdist(xy, "sqeuclidean")))
    np.fill_diagonal(low, 0)
    low /= low.sum()
    mask = reference > 0
    kl = float(np.sum(reference[mask] * np.log(reference[mask] / low[mask])))
    library_kl = _kl_divergence(xy.ravel(), library, 1, n, 2)[0]
    assert np.isfinite(kl) and kl >= -1e-12
    return affinity_error, abs(kl - library_kl), kl


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=ROOT / "reports/word_association/runs/20261024-c-four-models")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--projection", choices=["pca", "tsne"], default="pca")
    parser.add_argument("--perplexity", type=float, default=3.0)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("請指定新檔名，保留既有驗證紀錄")
    run = AssociationRun(args.run)
    records = []
    errors = {"geometry": 0.0, "cosine": 0.0, "variance": 0.0, "affinity": 0.0, "kl_objective": 0.0}
    for model, embedding in run.models.items():
        for left, right in (("insulin", "glucose"), ("semaglutide", "liraglutide"),
                            ("metformin", "receptor"), ("insulin", "insulin")):
            maps = compare_word_maps(run.tfidf, embedding, left, right, args.projection, args.perplexity)
            assert maps["status"] == "ok"
            assert maps == compare_word_maps(run.tfidf, embedding, left, right, args.projection, args.perplexity)
            for key, space in (("tfidf", run.tfidf), ("embedding", embedding)):
                result = maps["spaces"][key]
                assert [r["term"] for r in result["rows"]] == maps["terms"]
                indices = [space.lookup[t] for t in maps["terms"]]
                raw = space.matrix[:, indices].toarray().T if key == "tfidf" else space.vectors[indices].copy()
                unit = raw / np.sqrt((raw * raw).sum(axis=1))[:, None]
                xy = np.array([[r["x"], r["y"]] for r in result["rows"]])
                if args.projection == "pca":
                    centered = unit - unit.mean(axis=0)
                    gram = centered @ centered.T
                    values, directions = np.linalg.eigh(gram)
                    order = np.argsort(values)[::-1][:2]
                    expected = directions[:, order] @ np.diag(np.maximum(values[order], 0)) @ directions[:, order].T
                    errors["geometry"] = max(errors["geometry"], float(np.max(np.abs(xy @ xy.T - expected))))
                    retained = float(np.maximum(values[order], 0).sum() / np.trace(gram))
                    errors["variance"] = max(errors["variance"], abs(retained - result["retained_variance"]))
                else:
                    perplexity = result["diagnostics"]["parameters"]["perplexity"]
                    affinity_error, kl_error, kl = tsne_reference(unit, xy, perplexity)
                    errors["affinity"] = max(errors["affinity"], affinity_error)
                    errors["kl_objective"] = max(errors["kl_objective"], kl_error)
                    result["independent_final_kl"] = kl
                    assert result["retained_variance"] is None and np.isfinite(xy).all()
                a, b = [unit[maps["terms"].index(t)] for t in (left, right)]
                errors["cosine"] = max(errors["cosine"], abs(float(a @ b) - result["pair_cosine"]))
            records.append({"model": model, **maps})
        missing = compare_word_maps(run.tfidf, embedding, "notinthecorpusxyz", "glucose", args.projection, args.perplexity)
        assert missing["status"] == "unavailable" and not missing["spaces"]
    assert max(errors[k] for k in ("geometry", "cosine", "variance")) < 1e-11
    assert errors["affinity"] < 1e-8 and errors["kl_objective"] < 1e-6
    sources = ["ir_hw3/association_projection.py", "ir_hw3/association_ui.py", "ir_hw3/word_association.py",
               "ir_hw3/core.py", "resources/stopwords.json", "scripts/verify_association_projection.py",
               "requirements.txt", "requirements-lock.txt"]
    result = {"status": "passed", "manifest_sha256": sha256(args.run / "manifest.json"),
              "corpus_sha256": run.manifest["corpus_sha256"], "model_pair_cases": len(records),
              "space_projections_checked": len(records) * 2, "projection": args.projection,
              "perplexity": args.perplexity if args.projection == "tsne" else None,
              "repeat_exact": True, "maximum_errors": errors,
              "sources_sha256": {p: sha256(ROOT / p) for p in sources}, "projections": records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("projections", "sources_sha256")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
