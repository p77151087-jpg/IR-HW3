"""Independent NumPy log10 cosine checks for B/C/D and both IDF modes."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collections import Counter
import json
import numpy as np
from ir_hw3.core import Engine, METHODS, Settings, terms, LOGARITHM_BASE, WEIGHTING_VERSION
from ir_hw3.corpus import ROOT, load_corpus, sha256, verify_hw2_unchanged
from ir_hw3.evaluation import atomic_json, load_queries
from ir_hw3.experiments import run_experiment, weak_judgments


def check_setting(documents, queries, settings):
    engine = Engine(documents, settings)
    vocabulary = sorted(engine.df)
    positions = {term: i for i, term in enumerate(vocabulary)}
    ids = list(documents)
    df = np.zeros(len(vocabulary), dtype=np.float64)
    for counts in engine.counts.values():
        for term in counts:
            df[positions[term]] += 1
    idf = (np.log10(len(ids) / df) if settings.idf == 'standard' else
           np.log10((len(ids) + 1) / (df + 1)) + 1)
    query_counts = [Counter(terms(q['text'], settings.condition)) for q in queries]
    query_matrix = np.array([[c[t] for t in vocabulary] for c in query_counts], dtype=np.float64)
    maximum_error, checked = 0.0, 0
    for method in METHODS:
        def weighted(matrix):
            base = matrix.copy()
            if method in {'log_tf', 'log_tfidf'}:
                present = base > 0
                base[present] = 1 + np.log10(base[present])
            elif method == 'idf':
                base = (base > 0).astype(float)
            if method in {'idf', 'tfidf', 'log_tfidf'}:
                base *= idf
            return base
        vectors = weighted(query_matrix)
        query_norms = np.linalg.norm(vectors, axis=1)
        actual = [{r['pmid']: r['score'] for r in engine.rank(q['text'], method, limit=None)} for q in queries]
        for offset in range(0, len(ids), 128):
            batch = ids[offset:offset + 128]
            counts = np.zeros((len(batch), len(vocabulary)), dtype=np.float64)
            for row, doc_id in enumerate(batch):
                for term, tf in engine.counts[doc_id].items():
                    counts[row, positions[term]] = tf
            base = weighted(counts)
            denominator = np.linalg.norm(base, axis=1)[:, None] * query_norms[None, :]
            reference = np.divide(base @ vectors.T, denominator,
                                  out=np.zeros((len(batch), len(queries))), where=denominator != 0)
            observed = np.array([[scores.get(doc_id, 0) for scores in actual] for doc_id in batch])
            error = float(np.max(np.abs(observed - reference)))
            if error >= 1e-10:
                raise AssertionError((settings, method, offset, error))
            maximum_error = max(maximum_error, error)
            checked += len(batch) * len(queries)
    return {'condition': settings.condition, 'idf': settings.idf,
            'scores_checked': checked, 'maximum_cosine_error': maximum_error}


def main():
    documents, manifest = load_corpus()
    queries = load_queries()
    checks = []
    for condition in ('B', 'C', 'D'):
        for idf_mode in ('standard', 'smooth'):
            check = check_setting(documents, queries, Settings(condition, idf_mode))
            checks.append(check)
            print(json.dumps(check), flush=True)
    engine = Engine(documents)
    labels = weak_judgments(engine, queries, manifest['sha256'])
    first = run_experiment(engine, manifest, judgments=labels)
    second = run_experiment(engine, manifest, judgments=labels)
    same = {name: sha256(Path(first['output']) / name) == sha256(Path(second['output']) / name)
            for name in first['manifest']['outputs_sha256']}
    if not all(same.values()) or not first['normalization_passed']:
        raise AssertionError('Repeatability or normalization mismatch')
    source = verify_hw2_unchanged()
    if source['changed']:
        raise AssertionError(source)
    result = {'logarithm_base': LOGARITHM_BASE, 'weighting_version': WEIGHTING_VERSION,
              'documents': len(documents), 'queries': len(queries), 'methods': len(METHODS),
              'independent_cosine_scores_checked': sum(c['scores_checked'] for c in checks),
              'maximum_cosine_error': max(c['maximum_cosine_error'] for c in checks),
              'settings_checked': checks, 'repeatability': same,
              'normalization_passed': first['normalization_passed'], 'hw2_source': source,
              'judgment_source': 'weak_rules', 'settings': {'condition': 'C', 'idf': 'standard'},
              'runs': [{'output': run['output'], 'run_id': run['manifest']['run_id'],
                        'manifest_sha256': sha256(Path(run['output']) / 'manifest.json')} for run in (first, second)]}
    atomic_json(ROOT / 'reports/verification.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
