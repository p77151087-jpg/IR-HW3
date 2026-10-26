"""C word spaces built after stopword removal, independent of document retrieval."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256 as digest
from itertools import combinations
import csv
import json
from pathlib import Path

import numpy as np
from scipy import sparse
from scipy.stats import rankdata

from ir_hw1.preprocessing import tokenize
from .corpus import ROOT, sha256
from .core import stopwords

VERSION = "hw3-word-association-v2-c"
FIXED_TERMS = ["semaglutide", "liraglutide", "dulaglutide", "tirzepatide", "insulin",
               "glucose", "obesity", "diabetes", "receptor", "glp-1"]
MODEL_NAMES = {"cbow_w2": "CBOW · window 2", "cbow_w5": "CBOW · window 5",
               "skipgram_w2": "Skip-Gram · window 2", "skipgram_w5": "Skip-Gram · window 5"}
POLICY = {
    "preprocessing": "C: same fixed stopword list as document retrieval, removed before TF-IDF construction and Word2Vec training; no stemming; windows count retained tokens",
    "tfidf": "TF(d,t) * log10(N/DF(t)); full-vocabulary document row L2, then term column cosine",
    "pool": "Sorted intersection of all four embedding vocabularies and nonzero TF-IDF columns; CF>=2 inherited from min_count; no display filter",
    "neighbors": "Exclude self and cosine<=0 in every method; preserve original signed scores in all pair/heatmap results. Never fill with zero scores.",
    "ties": "Descending cosine rounded to 12 decimal places, then Unicode lexical term order; CSV retains full scores",
    "overlap": "|Top-k(TF-IDF) intersect Top-k(Embedding)| / requested k, even when fewer returned; unavailable anchor -> NA",
    "spearman": "Same 45 unordered pairs in fixed term order; pairwise finite mask; average ranks for ties; <2 pairs or constant ranks -> NA; no significance claims",
}


def stable_hash(value: str) -> int:
    return int.from_bytes(digest(value.encode("utf-8")).digest()[:8], "little")


def write_json(path: Path, value) -> None:
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".pending")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with Path(path).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def single_term(text: str) -> str | None:
    tokens = tokenize(text)
    return tokens[0].term if len(tokens) == 1 and tokens[0].term not in stopwords() else None


@dataclass
class TfidfWords:
    words: list[str]
    counts: sparse.csr_matrix
    matrix: sparse.csc_matrix
    cf: np.ndarray
    df: np.ndarray
    idf: np.ndarray
    document_norms: np.ndarray

    def __post_init__(self):
        self.lookup = {t: i for i, t in enumerate(self.words)}
        self.norms = np.sqrt(np.asarray(self.matrix.power(2).sum(axis=0)).ravel())

    @classmethod
    def build(cls, documents: list[list[str]]):
        vocabulary = sorted({t for doc in documents for t in doc})
        lookup = {t: i for i, t in enumerate(vocabulary)}
        rows, columns, values = [], [], []
        for row, doc in enumerate(documents):
            for term, count in sorted(Counter(doc).items()):
                rows.append(row)
                columns.append(lookup[term])
                values.append(count)
        counts = sparse.csr_matrix((values, (rows, columns)), shape=(len(documents), len(vocabulary)), dtype=np.float64)
        cf = np.asarray(counts.sum(axis=0)).ravel().astype(np.int64)
        df = counts.getnnz(axis=0)
        idf = np.log10(len(documents) / df) if vocabulary else np.array([])
        weighted = counts.multiply(idf).tocsr()
        norms = np.sqrt(np.asarray(weighted.power(2).sum(axis=1)).ravel())
        inverse = np.divide(1., norms, out=np.zeros_like(norms), where=norms > 0)
        matrix = sparse.diags(inverse).dot(weighted).tocsc()
        matrix.eliminate_zeros()
        return cls(vocabulary, counts, matrix, cf, df, idf, norms)

    def status(self, term):
        index = self.lookup.get(term)
        return "oov" if index is None else "zero_vector" if self.norms[index] == 0 else "ok"

    def scores(self, term, candidates):
        if self.status(term) != "ok":
            return None
        i = self.lookup[term]
        indices = [self.lookup[t] for t in candidates]
        products = (self.matrix[:, i].T @ self.matrix[:, indices]).toarray().ravel()
        denom = self.norms[i] * self.norms[indices]
        return np.divide(products, denom, out=np.zeros_like(products), where=denom > 0)

    def cooccurrence(self, left, right):
        if left not in self.lookup or right not in self.lookup:
            return 0
        a = self.counts[:, self.lookup[left]].toarray().ravel() > 0
        b = self.counts[:, self.lookup[right]].toarray().ravel() > 0
        return int(np.count_nonzero(a & b))

    def save(self, root):
        root.mkdir()
        write_json(root / "vocabulary.json", self.words)
        sparse.save_npz(root / "tf.npz", self.counts)
        sparse.save_npz(root / "tfidf-document-l2.npz", self.matrix)
        np.savez(root / "statistics.npz", cf=self.cf, df=self.df, idf=self.idf, document_norms=self.document_norms)
        write_csv(root / "term_statistics.csv", [
            {"term": t, "cf": int(self.cf[i]), "df": int(self.df[i]), "idf": float(self.idf[i]),
             "column_norm": float(self.norms[i])} for i, t in enumerate(self.words)])

    @classmethod
    def load(cls, root):
        stats = np.load(root / "statistics.npz", allow_pickle=False)
        return cls(json.loads((root / "vocabulary.json").read_text(encoding="utf-8")),
                   sparse.load_npz(root / "tf.npz").tocsr(), sparse.load_npz(root / "tfidf-document-l2.npz").tocsc(),
                   stats["cf"], stats["df"], stats["idf"], stats["document_norms"])


class EmbeddingWords:
    def __init__(self, words, vectors):
        self.words, self.vectors = words, np.asarray(vectors, dtype=np.float64)
        self.lookup = {t: i for i, t in enumerate(words)}
        self.norms = np.linalg.norm(self.vectors, axis=1)

    def status(self, term):
        i = self.lookup.get(term)
        return "oov" if i is None else "zero_vector" if self.norms[i] == 0 else "ok"

    def scores(self, term, candidates):
        if self.status(term) != "ok":
            return None
        i = self.lookup[term]
        indices = [self.lookup[t] for t in candidates]
        denom = self.norms[i] * self.norms[indices]
        return np.divide(self.vectors[indices] @ self.vectors[i], denom,
                         out=np.zeros(len(indices)), where=denom > 0)


def common_pool(tfidf, embeddings):
    shared = {t for t in tfidf.words if tfidf.status(t) == "ok"}
    for space in embeddings.values():
        shared.intersection_update(space.words)
    return sorted(shared)


def neighbors(space, term, pool, k=10):
    if k not in (5, 10, 20):
        raise ValueError("k must be 5, 10 or 20")
    status = space.status(term)
    if status != "ok":
        return {"status": status, "requested": k, "returned": 0, "rows": []}
    scores = space.scores(term, pool)
    rows = [{"term": other, "cosine": float(score)} for other, score in zip(pool, scores)
            if other != term and np.isfinite(score) and score > 0]
    rows.sort(key=lambda row: (-round(row["cosine"], 12), row["term"]))
    rows = [{"rank": i + 1, **row} for i, row in enumerate(rows[:k])]
    return {"status": "ok", "requested": k, "returned": len(rows), "rows": rows}


def overlap(first, second, k):
    if first["status"] != "ok" or second["status"] != "ok":
        return None
    return len({r["term"] for r in first["rows"]} & {r["term"] for r in second["rows"]}) / k


def spearman(left, right):
    a, b = np.asarray(left, dtype=float), np.asarray(right, dtype=float)
    mask = np.isfinite(a) & np.isfinite(b)
    a, b = a[mask], b[mask]
    if len(a) < 2 or np.ptp(a) == 0 or np.ptp(b) == 0:
        return {"rho": None, "valid_pairs": len(a), "status": "insufficient_or_constant"}
    return {"rho": float(np.corrcoef(rankdata(a, method="average"), rankdata(b, method="average"))[0, 1]),
            "valid_pairs": len(a), "status": "ok"}


def pair_score(space, left, right):
    if space.status(left) != "ok" or space.status(right) != "ok":
        return None
    return float(space.scores(left, [right])[0])


class AssociationRun:
    def __init__(self, root: Path, verify=True):
        self.root = Path(root)
        self.manifest = json.loads((self.root / "manifest.json").read_text(encoding="utf-8"))
        if self.manifest.get("status") != "complete" or self.manifest.get("version") != VERSION:
            raise ValueError("詞彙關聯 run 尚未完成或版本不符")
        if verify:
            for name, expected in self.manifest["artifacts_sha256"].items():
                path = (self.root / name).resolve()
                if not path.is_relative_to(self.root.resolve()) or sha256(path) != expected:
                    raise ValueError(f"詞彙關聯檔案指紋不符：{name}")
        contract = self.manifest.get("tokenizer", {})
        if (contract.get("condition") != "C" or contract.get("keep_stopwords") is not False
                or contract.get("stopwords_sha256") != sha256(ROOT / "resources/stopwords.json")):
            raise ValueError("詞彙關聯須使用目前停用詞表的 C 前處理成果")
        self.tfidf = TfidfWords.load(self.root / "tfidf")
        blocked = stopwords()
        if blocked.intersection(self.tfidf.words):
            raise ValueError("C TF-IDF 詞表仍包含停用詞")
        self.models = {}
        self.metadata = {}
        for key in MODEL_NAMES:
            folder = self.root / "models" / key
            metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
            if (metadata["status"] != "complete" or metadata["corpus_sha256"] != self.manifest["corpus_sha256"]
                    or metadata.get("tokenizer") != contract):
                raise ValueError("模型未完成或語料版本不符")
            self.metadata[key] = metadata
            self.models[key] = EmbeddingWords(json.loads((folder / "vocabulary.json").read_text(encoding="utf-8")),
                                               np.load(folder / "vectors.npy", allow_pickle=False))
            if blocked.intersection(self.models[key].words):
                raise ValueError("C Embedding 詞表仍包含停用詞")
        self.pool = json.loads((self.root / "candidate_pool.json").read_text(encoding="utf-8"))
        if self.pool != common_pool(self.tfidf, self.models):
            raise ValueError("共同候選池不一致")


def compare_spaces(tfidf, models, pool):
    spaces = {"tfidf": tfidf, **models}
    status = []
    for term in FIXED_TERMS:
        i = tfidf.lookup.get(term)
        status.append({"term": term, "cf": int(tfidf.cf[i]) if i is not None else 0,
                       "df": int(tfidf.df[i]) if i is not None else 0,
                       **{name: space.status(term) for name, space in spaces.items()},
                       "in_candidate_pool": term in pool})
    pairs = []
    for left, right in combinations(FIXED_TERMS, 2):
        pairs.append({"pair_id": len(pairs) + 1, "left": left, "right": right,
                      "cooccurring_documents": tfidf.cooccurrence(left, right),
                      **{name: pair_score(space, left, right) for name, space in spaces.items()}})
    overlap_rows, neighbor_rows, summary = [], [], []
    for k in (5, 10, 20):
        for term in FIXED_TERMS:
            results = {name: neighbors(space, term, pool, k) for name, space in spaces.items()}
            for name, result in results.items():
                neighbor_rows.extend({"method": name, "query": term, "k": k, **row} for row in result["rows"])
            for key in models:
                a, b = results["tfidf"], results[key]
                overlap_rows.append({"model": key, "term": term, "k": k, "tfidf_returned": a["returned"],
                                     "embedding_returned": b["returned"], "overlap": overlap(a, b, k)})
        for key in models:
            values = [row["overlap"] for row in overlap_rows if row["model"] == key and row["k"] == k and row["overlap"] is not None]
            rank_correlation = spearman([row["tfidf"] for row in pairs], [row[key] for row in pairs])
            summary.append({"model": key, "k": k, "mean_overlap": float(np.mean(values)) if values else None,
                            "valid_terms": len(values), "total_terms": len(FIXED_TERMS), **rank_correlation})
    return {"term_status": status, "pairs": pairs, "overlap": overlap_rows, "neighbors": neighbor_rows, "summary": summary}
