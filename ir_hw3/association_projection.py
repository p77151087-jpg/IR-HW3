"""Small, read-only word-space projections; original cosine scores stay untouched."""
from html import escape

import numpy as np

from .word_association import FIXED_TERMS, pair_score


def normalized_word_vectors(space, terms):
    """Copy only the requested full-dimensional word vectors, then L2 each word."""
    indices = [space.lookup[term] for term in terms]
    # Streamlit can retain cached instances while reloading their defining
    # classes. Use the matrix interface instead of reload-sensitive class identity.
    matrix = getattr(space, "matrix", None)
    if matrix is not None:
        vectors = matrix[:, indices].T.toarray()
    else:
        vectors = space.vectors[indices].copy()
    norms = np.linalg.norm(vectors, axis=1)
    if not np.isfinite(vectors).all() or np.any(norms == 0):
        raise ValueError("投影詞必須有有限、非零向量")
    return vectors / norms[:, None]


def pca_xy(vectors):
    """Centered full SVD, without whitening; fix component signs for repeatability."""
    centered = vectors - vectors.mean(axis=0)
    u, singular, components = np.linalg.svd(centered, full_matrices=False)
    dimensions = min(2, len(singular))
    coordinates = np.zeros((len(vectors), 2), dtype=float)
    for axis in range(dimensions):
        pivot = int(np.argmax(np.abs(components[axis])))
        sign = -1.0 if components[axis, pivot] < 0 else 1.0
        coordinates[:, axis] = u[:, axis] * singular[axis] * sign
    energy = singular ** 2
    total = float(energy.sum())
    threshold = np.finfo(float).eps * max(centered.shape) * (singular[0] if len(singular) else 0)
    rank = int(np.count_nonzero(singular > threshold))
    return coordinates, (float(energy[:2].sum() / total) if total > 0 else 0.0), rank


def tsne_xy(vectors, perplexity=3.0):
    """Exact t-SNE on full word vectors; fixed seed and one computational thread."""
    from sklearn import __version__
    from sklearn.manifold import TSNE
    from threadpoolctl import threadpool_limits

    if not np.isfinite(perplexity) or not 0 < perplexity < len(vectors):
        raise ValueError("t-SNE perplexity 必須大於 0 且小於詞數")
    if not np.isfinite(vectors).all():
        raise ValueError("t-SNE 需要有限的完整詞向量")
    parameters = dict(n_components=2, perplexity=float(perplexity), early_exaggeration=12.0,
                      learning_rate="auto", max_iter=1000, n_iter_without_progress=300,
                      min_grad_norm=1e-7, metric="euclidean", init="random", random_state=42,
                      method="exact", n_jobs=1)
    estimator = TSNE(**parameters)
    with threadpool_limits(limits=1):
        xy = estimator.fit_transform(vectors.copy())
    if not np.isfinite(xy).all() or not np.isfinite(estimator.kl_divergence_):
        raise ValueError("t-SNE 未產生有限的投影結果")
    return xy, {"library": "scikit-learn", "version": __version__, "parameters": parameters,
                "optimizer_reported_kl": float(estimator.kl_divergence_),
                "last_iteration_index": int(estimator.n_iter_),
                "iterations": int(estimator.n_iter_) + 1, "learning_rate": float(estimator.learning_rate_)}


def compare_word_maps(tfidf, embedding, left, right, projection="pca", perplexity=3.0):
    """Use the same ordered words in two independently fitted projection spaces."""
    if projection not in ("pca", "tsne"):
        raise ValueError("投影方式必須為 pca 或 tsne")
    requested = list(dict.fromkeys([*FIXED_TERMS, left, right]))
    missing = [{"term": term, "tfidf": tfidf.status(term), "embedding": embedding.status(term)}
               for term in requested if tfidf.status(term) != "ok" or embedding.status(term) != "ok"]
    terms = [term for term in requested if all(row["term"] != term for row in missing)]
    result = {"terms": terms, "missing": missing, "pair": [left, right], "spaces": {},
              "projection": projection,
              "algorithm": ("word L2 -> centered full-SVD PCA; independently fitted on the same displayed terms"
                            if projection == "pca" else "word L2 -> exact t-SNE on full vectors; same displayed terms and fixed random seed")}
    if left not in terms or right not in terms or len(terms) < 3:
        result["status"] = "unavailable"
        return result
    result["status"] = "ok"
    for name, space in (("tfidf", tfidf), ("embedding", embedding)):
        vectors = normalized_word_vectors(space, terms)
        diagnostics = None
        if projection == "pca":
            xy, retained, rank = pca_xy(vectors)
        else:
            # A reduced shared set must still satisfy perplexity < number of words.
            effective_perplexity = min(float(perplexity), len(terms) - 1.0)
            xy, diagnostics = tsne_xy(vectors, effective_perplexity)
            retained = rank = None
        result["spaces"][name] = {
            "dimensions": int(vectors.shape[1]), "retained_variance": retained, "rank": rank,
            "diagnostics": diagnostics,
            "pair_cosine": pair_score(space, left, right),
            "rows": [{"term": term, "x": float(point[0]), "y": float(point[1]),
                      "role": ("詞 A／B" if term == left == right else "詞 A" if term == left
                               else "詞 B" if term == right else "參考詞")}
                     for term, point in zip(terms, xy)],
        }
    # Both X and Y use the same range and equal pixel units, across both panels.
    maximum = max(abs(row[axis]) for data in result["spaces"].values()
                  for row in data["rows"] for axis in ("x", "y"))
    result["extent"] = max(0.5, maximum * 1.3)
    return result


def word_map_svg(data, pair, extent, title, projection="pca"):
    """Responsive square SVG; escaped labels and native hover titles, no JavaScript."""
    size, pad, span = 520, 64, 392
    def position(row):
        return pad + (row["x"] / extent + 1) * span / 2, pad + (1 - row["y"] / extent) * span / 2
    colors = {"詞 A": "#c65f1a", "詞 B": "#2563b4", "詞 A／B": "#7e3c98", "參考詞": "#8096a3"}
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" '
             f'role="img" aria-label="{escape(title, quote=True)}" style="width:100%;height:auto;display:block;'
             'background:#fff;border:1px solid #dde6eb;border-radius:12px;font-family:Arial,sans-serif">',
             f'<title>{escape(title)}</title>']
    for value in np.linspace(-extent, extent, 5):
        x, y = position({"x": value, "y": value})
        parts += [f'<path d="M{x:.2f},{pad} V{pad+span} M{pad},{y:.2f} H{pad+span}" stroke="#edf1f4" fill="none"/>',
                  f'<text x="{x:.2f}" y="478" text-anchor="middle" fill="#627986" font-size="12">{value:.2f}</text>',
                  f'<text x="55" y="{y+4:.2f}" text-anchor="end" fill="#627986" font-size="12">{value:.2f}</text>']
    x_label, y_label = (("X（主成分 1）", "Y（主成分 2）") if projection == "pca"
                        else ("X（t-SNE 維度 1）", "Y（t-SNE 維度 2）"))
    parts += ['<path d="M64,260 H456 M260,64 V456" stroke="#b5c4ce" stroke-dasharray="4 4" fill="none"/>',
              f'<text x="260" y="505" text-anchor="middle" fill="#425d6c" font-size="14">{x_label}</text>',
              f'<text transform="translate(17,260) rotate(-90)" text-anchor="middle" fill="#425d6c" font-size="14">{y_label}</text>']
    selected = [row for row in data["rows"] if row["term"] in pair]
    if len(selected) == 2:
        a, b = [position(row) for row in selected]
        parts.append(f'<path d="M{a[0]:.2f},{a[1]:.2f} L{b[0]:.2f},{b[1]:.2f}" stroke="#6d7e88" stroke-dasharray="5 4" fill="none"/>')
    # Place highlighted labels first; move later labels to avoid covering earlier text.
    boxes = []
    ordered = sorted(data["rows"], key=lambda row: row["role"] == "參考詞")
    for row in ordered:
        x, y = position(row)
        label = row["term"] if row["role"] == "參考詞" else f'{row["role"]}：{row["term"]}'
        width = min(400, len(label) * 7 + 8)
        offsets = [(10, -17), (10, 7), (-width-10, -17), (-width-10, 7),
                   (10, -38), (10, 28), (-width-10, -38), (-width-10, 28)]
        candidates = [(max(28, min(size-width-12, x+dx)), max(22, min(438, y+dy))) for dx, dy in offsets]
        def collisions(candidate):
            lx, ly = candidate
            return sum(lx < bx+bw+3 and lx+width+3 > bx and ly < by+18+3 and ly+18+3 > by
                       for bx, by, bw in boxes)
        lx, ly = min(candidates, key=collisions)
        boxes.append((lx, ly, width))
        color = colors[row["role"]]
        radius = 7 if row["role"] != "參考詞" else 4.5
        tooltip = f'{row["role"]}：{row["term"]}；X＝{row["x"]:.6f}；Y＝{row["y"]:.6f}（二維投影座標）'
        parts += [f'<g><title>{escape(tooltip)}</title>',
                  f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{radius}" fill="{color}" stroke="white" stroke-width="1.5"/>',
                  f'<path d="M{x:.2f},{y:.2f} L{lx:.2f},{ly+9:.2f}" stroke="{color}" stroke-opacity="0.35" fill="none"/>',
                  f'<rect x="{lx:.2f}" y="{ly:.2f}" width="{width}" height="18" rx="3" fill="white" fill-opacity="0.90"/>',
                  f'<text x="{lx+4:.2f}" y="{ly+13:.2f}" fill="{color}" font-size="13" '
                  f'font-weight="{"400" if row["role"] == "參考詞" else "700"}">{escape(label)}</text></g>']
    return "".join([*parts, "</svg>"])
