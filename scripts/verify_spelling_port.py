"""Before/after evidence for the interactive-only spelling port (no file overwrites)."""
from pathlib import Path
import argparse
import gc
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ir_hw3.core import Engine, Settings, METHODS
from ir_hw3.corpus import ROOT, load_corpus, sha256
from ir_hw3.evaluation import evaluate, fingerprint, load_queries, load_judgments
from ir_hw3.experiments import weak_judgments


def capture():
    documents, manifest = load_corpus()
    queries = load_queries()
    labels = [load_judgments(manifest['sha256'], queries, documents),
              weak_judgments(Engine(documents), queries, manifest['sha256'])]
    # Reuse preserved automatic reference judgments; never regenerate old results.
    for path in sorted((ROOT / 'reports/pubmed_hybrid/runs').glob('*/judgments.json'), reverse=True):
        value = json.loads(path.read_text(encoding='utf-8'))
        if value['corpus_sha256'] == manifest['sha256'] and value['queries_sha256'] == fingerprint(queries):
            labels.append(value)
            break
    checks = []
    for condition in ('B', 'C', 'D'):
        for idf in ('standard', 'smooth'):
            engine = Engine(documents, Settings(condition, idf))
            rankings = {q['qid']: {m: fingerprint(engine.rank(q['text'], m, limit=None))
                                  for m in METHODS} for q in queries}
            metrics = {label['source']: fingerprint(evaluate(engine, queries, label)) for label in labels}
            checks.append({'condition': condition, 'idf': idf, 'rankings': rankings, 'metrics': metrics})
            del engine
            gc.collect()
    return {'corpus_sha256': manifest['sha256'], 'queries_sha256': fingerprint(queries),
            'documents': len(documents), 'sources': [label['source'] for label in labels], 'checks': checks}


def protected_files(output):
    files = {}
    for folder in ('data', 'reports'):
        for path in (ROOT / folder).rglob('*'):
            if path.is_file() and not path.is_relative_to(output):
                files[str(path)] = sha256(path)
    # All HW2 source, tests, launchers and dependency declarations, read only.
    source = ROOT.parent / 'IR-HW2'
    excluded = {'.git', '.venv', '.venv-hw2', '__pycache__', '.pytest_cache', 'tmp', 'data', 'reports'}
    import os
    for directory, names, filenames in os.walk(source):
        names[:] = [name for name in names if name not in excluded]
        for name in filenames:
            path = Path(directory) / name
            if path.suffix in {'.py', '.ps1', '.cmd', '.bat', '.toml', '.txt'}:
                files[str(path)] = sha256(path)
    for path in [ROOT / 'app.py', *sorted((ROOT / 'ir_hw3').glob('*.py')),
                 ROOT / 'ir_hw1/preprocessing.py']:
        files[str(path)] = sha256(path)
    return files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['before', 'after', 'numeric'])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.phase == 'numeric':
        # Run the existing independent oracle unchanged, saving its final result
        # beside this task's evidence instead of replacing verification.json.
        import runpy
        module = runpy.run_path(str(ROOT / 'scripts/verify_hw3.py'))
        destination = output / 'numeric.json'
        if destination.exists():
            raise FileExistsError(destination)
        write_json = module['atomic_json']
        module['main'].__globals__['atomic_json'] = lambda path, value: write_json(destination, value)
        module['main']()
        return
    destination = output / (args.phase + '.json')
    if destination.exists():
        raise FileExistsError(destination)
    result = capture()
    if args.phase == 'before':
        result['protected_files'] = protected_files(output)
        (output / 'app-before.py.txt').write_bytes((ROOT / 'app.py').read_bytes())
    else:
        before = json.loads((output / 'before.json').read_text(encoding='utf-8'))
        result['evaluation_identical'] = all(result[key] == before[key] for key in result)
        allowed = {str(ROOT / 'app.py')}
        changes = [name for name, digest in before['protected_files'].items()
                   if not Path(name).is_file() or sha256(Path(name)) != digest]
        result['changed_protected_files'] = changes
        result['protected_files_checked'] = len(before['protected_files'])
        result['hw2_files_checked'] = sum('IR-HW2' in name for name in before['protected_files'])
        result['passed'] = result['evaluation_identical'] and set(changes) <= allowed
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items() if key not in {'checks', 'protected_files'}}, ensure_ascii=False))
    if args.phase == 'after' and not result['passed']:
        raise AssertionError('Spelling isolation or preserved file verification failed')


if __name__ == '__main__':
    main()
