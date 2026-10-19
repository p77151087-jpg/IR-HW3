"""Sparse TF/IDF vector-space retrieval; document/query weighting is symmetric."""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
import html
import json
import math
from pathlib import Path

from ir_hw1.models import Document
from ir_hw1.preprocessing import tokenize, stem_term
from .corpus import ROOT, abstract_text

METHODS = {
    "tf": "原始 TF", "log_tf": "Log TF", "idf": "僅 IDF",
    "tfidf": "TF × IDF", "log_tfidf": "Log TF × IDF",
}
CONDITIONS = {"B": "B：切詞與正規化", "C": "C：B＋移除停用詞", "D": "D：C＋Porter"}
IDF_MODES = {"standard": "標準 ln(N / DF)", "smooth": "平滑 ln((N+1)/(DF+1)) + 1"}

@dataclass(frozen=True)
class Settings:
    condition: str = "C"
    idf: str = "standard"

    def __post_init__(self):
        if self.condition not in CONDITIONS or self.idf not in IDF_MODES:
            raise ValueError("不支援的前處理或 IDF 設定。")

@lru_cache(maxsize=1)
def stopwords() -> frozenset[str]:
    return frozenset(json.loads((ROOT / "resources/stopwords.json").read_text(encoding="utf-8"))["words"])

def terms(text: str, condition: str = "C") -> list[str]:
    if condition not in CONDITIONS:
        raise ValueError("未知前處理設定。")
    result = [token.term for token in tokenize(text)]
    if condition in {"C", "D"}:
        result = [term for term in result if term not in stopwords()]
    return [stem_term(term) for term in result] if condition == "D" else result

def term_weight(tf: int, idf: float, method: str) -> float:
    if method not in METHODS:
        raise ValueError("未知權重方法。")
    if tf <= 0:
        return 0.0
    if method == "tf":
        return float(tf)
    if method == "log_tf":
        return 1.0 + math.log(tf)
    if method == "idf":
        return idf
    return (tf if method == "tfidf" else 1.0 + math.log(tf)) * idf

def order_id(value: str):
    return (0, int(value)) if value.isdigit() else (1, value)

class Engine:
    def __init__(self, documents: dict[str, Document], settings: Settings = Settings()):
        if not documents:
            raise ValueError("語料不可為空。")
        self.documents = documents
        self.settings = settings
        self.counts = {doc_id: Counter(terms(abstract_text(doc), settings.condition))
                       for doc_id, doc in documents.items()}
        self.df = Counter()
        self.cf = Counter()
        for counts in self.counts.values():
            self.df.update(counts.keys())
            self.cf.update(counts)
        self.n = len(documents)  # Empty vectors remain part of the document population.
        self.idf = {term: (math.log(self.n / df) if settings.idf == "standard"
                          else math.log((self.n + 1) / (df + 1)) + 1)
                    for term, df in self.df.items()}
        self.postings = {}
        for doc_id, counts in self.counts.items():
            for term, tf in counts.items():
                self.postings.setdefault(term, {})[doc_id] = tf
        self._vectors = {}

    def vectors(self, method: str) -> tuple[dict, dict]:
        if method not in METHODS:
            raise ValueError("未知權重方法。")
        if method not in self._vectors:
            weights = {doc_id: {term: term_weight(tf, self.idf[term], method)
                                for term, tf in counts.items()}
                       for doc_id, counts in self.counts.items()}
            norms = {doc_id: math.sqrt(sum(value * value for value in vector.values()))
                     for doc_id, vector in weights.items()}
            self._vectors[method] = weights, norms
        return self._vectors[method]

    def query(self, query: str, method: str) -> tuple[Counter, dict, list[str]]:
        if len(query) > 2000:
            raise ValueError("查詢最多 2,000 個字元。")
        counts = Counter(terms(query, self.settings.condition))
        unknown = sorted(set(counts) - set(self.df))
        weights = {term: term_weight(tf, self.idf[term], method)
                   for term, tf in counts.items() if term in self.idf}
        return counts, weights, unknown

    def rank(self, query: str, method: str = "log_tfidf", *, limit: int | None = 10,
             scoring: str = "cosine", normalize: bool = False) -> list[dict]:
        if scoring not in {"cosine", "dot"}:
            raise ValueError("scoring 必須是 cosine 或 dot。")
        if limit is not None and limit < 1:
            raise ValueError("limit 必須為正整數。")
        _, query_weights, _ = self.query(query, method)
        weights, norms = self.vectors(method)
        query_norm = math.sqrt(sum(weight * weight for weight in query_weights.values()))
        if not query_norm:
            return []
        scores = {}
        for term, query_weight in query_weights.items():
            if not query_weight:
                continue
            for doc_id in self.postings[term]:
                document_weight = weights[doc_id][term]
                if normalize:
                    document_weight = document_weight / norms[doc_id] if norms[doc_id] else 0.0
                scores[doc_id] = scores.get(doc_id, 0.0) + document_weight * (
                    query_weight / query_norm if normalize else query_weight)
        if scoring == "cosine":
            for doc_id in scores:
                if not normalize:
                    denominator = norms[doc_id] * query_norm
                    scores[doc_id] = scores[doc_id] / denominator if denominator else 0.0
                scores[doc_id] = max(0.0, min(1.0, scores[doc_id]))
        ordered = sorted((doc_id for doc_id, score in scores.items() if score > 0),
                         key=lambda doc_id: (-round(scores[doc_id], 12), order_id(doc_id)))
        if limit is not None:
            ordered = ordered[:limit]
        return [{"rank": rank, "pmid": doc_id, "score": scores[doc_id],
                 "title": self.documents[doc_id].title}
                for rank, doc_id in enumerate(ordered, 1)]

    def explain(self, query: str, doc_id: str, method: str = "log_tfidf") -> list[dict]:
        counts, query_weights, _ = self.query(query, method)
        vectors, norms = self.vectors(method)
        query_norm = math.sqrt(sum(weight * weight for weight in query_weights.values()))
        denominator = query_norm * norms[doc_id]
        rows = []
        for term in sorted(counts):
            document_weight = vectors[doc_id].get(term, 0.0)
            query_weight = query_weights.get(term, 0.0)
            rows.append({"term": term, "query_tf": counts[term],
                         "document_tf": self.counts[doc_id][term], "df": self.df[term],
                         "idf": self.idf.get(term, 0.0), "query_weight": query_weight,
                         "document_weight": document_weight,
                         "cosine_contribution": query_weight * document_weight / denominator if denominator else 0.0})
        return rows

    def term_statistics(self) -> list[dict]:
        return [{"term": term, "cf": cf, "df": self.df[term], "idf": self.idf[term]}
                for term, cf in self.cf.most_common()]

    def normalization_check(self, query: str, method: str = "log_tfidf") -> dict:
        raw = self.rank(query, method, limit=None)
        normalized = self.rank(query, method, limit=None, normalize=True)
        by_id = {row["pmid"]: row["score"] for row in normalized}
        return {"same_ranking": [r["pmid"] for r in raw] == [r["pmid"] for r in normalized],
                "max_score_difference": max((abs(row["score"] - by_id.get(row["pmid"], 0)) for row in raw), default=0),
                "retrieved": len(raw)}

    def snippet(self, doc_id: str, query: str, width: int = 360) -> str:
        """Escape all source text, then add marks using tokenizer character offsets."""
        text = abstract_text(self.documents[doc_id])
        wanted = set(terms(query, self.settings.condition))
        matches = []
        for token in tokenize(text):
            term = stem_term(token.term) if self.settings.condition == "D" else token.term
            if term in wanted:
                matches.append((token.start, token.end))
        left = max(0, matches[0][0] - 90) if matches else 0
        right = min(len(text), left + width)
        pieces, cursor = [], left
        for start, end in matches:
            if start < left or end > right:
                continue
            pieces.extend((html.escape(text[cursor:start]), "<mark>" + html.escape(text[start:end]) + "</mark>"))
            cursor = end
        pieces.append(html.escape(text[cursor:right]))
        return ("…" if left else "") + "".join(pieces) + ("…" if right < len(text) else "")
