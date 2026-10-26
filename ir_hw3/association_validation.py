"""Offline artifact and independent numerical verification; never trains."""
import argparse
from collections import Counter
from dataclasses import asdict, replace
from datetime import datetime, timezone
from itertools import combinations
import json
from pathlib import Path

from gensim.models import Word2Vec
import numpy as np
from scipy import sparse, stats

from .corpus import ROOT, SNAPSHOT, load_corpus, sha256
from .embedding_training import TrainingConfig, prepare_documents, tokenizer_contract
from .word_association import AssociationRun, FIXED_TERMS, MODEL_NAMES, neighbors, pair_score, write_json
from .core import terms, stopwords


def validate_run(root):
    run = AssociationRun(root)
    manifest = run.manifest
    documents, corpus = load_corpus()
    assert len(documents) == manifest["documents"] == 3000
    assert corpus["sha256"] == manifest["corpus_sha256"]
    assert sha256(SNAPSHOT / "snapshot.json") == manifest["snapshot_manifest_sha256"]
    assert manifest["tokenizer"] == tokenizer_contract()
    for name, expected in manifest["source_sha256"].items():
        assert sha256(root / "sources" / name) == expected, name
        # The frozen report generator is the exact training-time version. Later
        # plotting/cache-only changes cannot alter already saved model vectors.
        if name != "ir_hw3/association_report.py":
            assert sha256(ROOT / name) == expected, name
    order, token_documents, records = prepare_documents(documents)
    blocked = stopwords()
    for doc_id, tokens in zip(order, token_documents):
        expected = [term for block in documents[doc_id].blocks if block.kind == "abstract"
                    for term in terms(block.text, "C")]
        assert tokens == expected, (doc_id, "C preprocessing differs from document retrieval")
    assert not blocked.intersection(t for tokens in token_documents for t in tokens)
    saved_records = [json.loads(line) for line in (root / "sentences.jsonl").read_text(encoding="utf-8").splitlines()]
    assert records == saved_records
    assert order == json.loads((root / "document_order.json").read_text(encoding="utf-8"))
    assert sum(map(len, token_documents)) == manifest["tokens"]
    assert len(records) == manifest["sentences"]
    counts = Counter(t for doc in token_documents for t in doc)
    df = Counter(t for doc in token_documents for t in set(doc))
    vocabulary = sorted(counts)
    assert vocabulary == run.tfidf.words
    assert np.array_equal(run.tfidf.cf, [counts[t] for t in vocabulary])
    assert np.array_equal(run.tfidf.df, [df[t] for t in vocabulary])
    # Independent CSR construction from token positions, including duplicate entries.
    lookup = {t: i for i, t in enumerate(vocabulary)}
    indptr = np.cumsum([0, *map(len, token_documents)])
    indices = [lookup[t] for doc in token_documents for t in doc]
    raw = sparse.csr_matrix((np.ones(len(indices)), indices, indptr), shape=(3000, len(vocabulary)))
    raw.sum_duplicates()
    assert (raw != run.tfidf.counts).nnz == 0
    idfs = np.array([np.log10(3000 / df[t]) for t in vocabulary])
    assert np.allclose(idfs, run.tfidf.idf, rtol=0, atol=1e-15)
    weighted = raw @ sparse.diags(idfs)
    norms = np.sqrt(weighted.multiply(weighted).sum(axis=1)).A1
    assert np.allclose(norms, run.tfidf.document_norms, rtol=1e-13, atol=1e-13)
    oracle = (sparse.diags(np.divide(1, norms, out=np.zeros_like(norms), where=norms > 0)) @ weighted).tocsc()
    difference = oracle - run.tfidf.matrix
    matrix_error = float(np.max(np.abs(difference.data))) if difference.nnz else 0.
    assert matrix_error < 1e-12
    meta_tfidf = json.loads((root / "tfidf/metadata.json").read_text(encoding="utf-8"))
    assert meta_tfidf["corpus_sha256"] == manifest["corpus_sha256"]
    assert meta_tfidf["tokenizer"] == manifest["tokenizer"]
    assert meta_tfidf["shape"] == [3000, len(vocabulary)]
    pair_rows = json.loads((root / "results.json").read_text(encoding="utf-8"))["pairs"]
    assert [(r["left"], r["right"]) for r in pair_rows] == list(combinations(FIXED_TERMS, 2))
    expected_pool = {t for i, t in enumerate(vocabulary) if np.linalg.norm(oracle[:, i].data) > 0}
    expected_model_vocab = {t for t, count in counts.items() if count >= 2}
    versions = manifest["versions"]
    model_checks, maximum_pair_error, maximum_neighbor_error = [], 0., 0.
    fixed_plus_sample = FIXED_TERMS + [run.pool[i] for i in np.random.default_rng(42).choice(len(run.pool), 5, replace=False)]

    def independent_cosine(a, b):
        norm = np.linalg.norm(a) * np.linalg.norm(b)
        return float(np.dot(a, b) / norm) if norm else None

    def check_neighbors(space, source, term, key):
        nonlocal maximum_neighbor_error
        anchor, candidates = source(term)
        denominators = np.linalg.norm(anchor) * candidates[1]
        numerators = candidates[0] @ anchor
        scores = np.divide(np.asarray(numerators).ravel(), denominators,
                           out=np.zeros(len(run.pool)), where=denominators > 0)
        rows = [(t, float(s)) for t, s in zip(run.pool, scores) if t != term and np.isfinite(s) and s > 0]
        rows.sort(key=lambda row: (-round(row[1], 12), row[0]))
        actual = neighbors(space, term, run.pool, 20)["rows"]
        assert [r["term"] for r in actual] == [r[0] for r in rows[:20]], (key, term)
        maximum_neighbor_error = max(maximum_neighbor_error, max([abs(a["cosine"] - b[1]) for a, b in zip(actual, rows)] or [0.]))

    pool_indices = [lookup[t] for t in run.pool]
    oracle_pool = oracle[:, pool_indices].T.tocsr()
    pool_norms = np.sqrt(oracle_pool.multiply(oracle_pool).sum(axis=1)).A1
    for term in fixed_plus_sample:
        if run.tfidf.status(term) == "ok":
            check_neighbors(run.tfidf, lambda t: (oracle[:, lookup[t]].toarray().ravel(), (oracle_pool, pool_norms)), term, "tfidf")
    for row in pair_rows:
        a, b = row["left"], row["right"]
        expected = independent_cosine(oracle[:, lookup[a]].toarray().ravel(), oracle[:, lookup[b]].toarray().ravel())
        assert expected is None and row["tfidf"] is None or abs(expected - row["tfidf"]) < 1e-12
        if expected is not None:
            maximum_pair_error = max(maximum_pair_error, abs(expected - row["tfidf"]))
    for key in MODEL_NAMES:
        folder, metadata = root / "models" / key, run.metadata[key]
        assert metadata["documents"] == 3000 and metadata["tokens"] == manifest["tokens"]
        assert metadata["sentences_sha256"] == manifest["sentences_sha256"]
        assert metadata["tokenizer"] == manifest["tokenizer"] and metadata["versions"] == versions
        config = replace(TrainingConfig(), sg=int(key.startswith("skipgram")), window=int(key[-1]))
        assert metadata["config"] == asdict(config)
        for name, expected in metadata["artifacts_sha256"].items():
            assert sha256(folder / name) == expected
        model = Word2Vec.load(str(folder / "word2vec.model"))
        assert set(model.wv.index_to_key) == expected_model_vocab
        assert not blocked.intersection(model.wv.index_to_key)
        expected_pool.intersection_update(model.wv.index_to_key)
        assert model.wv.index_to_key == run.models[key].words
        assert np.array_equal(model.wv.vectors, np.load(folder / "vectors.npy", allow_pickle=False))
        assert all(getattr(model, name) == value for name, value in asdict(config).items())
        assert model.corpus_count == len(records) and model.corpus_total_words == manifest["tokens"]
        assert metadata["raw_training_words_all_epochs"] == manifest["tokens"] * 30
        assert len(metadata["epoch_losses"]) == 30
        assert all(model.wv.get_vecattr(t, "count") == counts[t] for t in model.wv.index_to_key)
        vectors = model.wv.vectors.astype(np.float64)
        pool_vectors = vectors[[model.wv.key_to_index[t] for t in run.pool]]
        norms = np.linalg.norm(pool_vectors, axis=1)
        for term in fixed_plus_sample:
            if term in model.wv:
                check_neighbors(run.models[key], lambda t: (vectors[model.wv.key_to_index[t]], (pool_vectors, norms)), term, key)
        for row in pair_rows:
            a, b = row["left"], row["right"]
            if a in model.wv and b in model.wv:
                expected = independent_cosine(vectors[model.wv.key_to_index[a]], vectors[model.wv.key_to_index[b]])
                maximum_pair_error = max(maximum_pair_error, abs(expected - row[key]))
        finite = [r for r in pair_rows if r["tfidf"] is not None and r[key] is not None]
        a, b = [r["tfidf"] for r in finite], [r[key] for r in finite]
        expected_rho = float(stats.spearmanr(a, b).statistic) if len(a) >= 2 and np.ptp(a) > 0 and np.ptp(b) > 0 else None
        saved = next(r for r in json.loads((root / "results.json").read_text(encoding="utf-8"))["summary"] if r["model"] == key)
        assert saved["rho"] == expected_rho or abs(saved["rho"] - expected_rho) < 1e-14
        model_checks.append({"model": key, "offline_reload": True, "config": asdict(config), "vocabulary": len(model.wv),
                             "corpus_sha256": metadata["corpus_sha256"], "fixed_pairs_checked": len(finite)})
    assert run.pool == sorted(expected_pool)
    assert maximum_pair_error < 1e-12 and maximum_neighbor_error < 1e-12
    return {"passed": True, "documents": 3000, "sentences": len(records), "tokens": manifest["tokens"],
            "preprocessing": "C", "stopwords_absent_in_all_spaces": True,
            "stopwords_sha256": manifest["tokenizer"]["stopwords_sha256"],
            "vocabulary": len(vocabulary), "candidate_pool": len(run.pool), "fixed_pairs": len(pair_rows),
            "models": model_checks, "independent_matrix_max_error": matrix_error,
            "independent_pair_max_error": maximum_pair_error, "independent_neighbor_max_error": maximum_neighbor_error,
            "neighbor_queries_per_method": len(fixed_plus_sample), "corpus_sha256": corpus["sha256"],
            "run_manifest_sha256": sha256(root / "manifest.json"), "artifacts_checked": len(manifest["artifacts_sha256"]),
            "versions": versions, "validated_at_utc": datetime.now(timezone.utc).isoformat()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.run / ("validation-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
    if output.exists():
        raise FileExistsError(output)
    result = validate_run(args.run)
    write_json(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
