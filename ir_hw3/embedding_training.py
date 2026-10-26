"""Explicit CLI-only, fresh four-model training on the sealed HW3 snapshot."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path
import platform
from time import perf_counter
import unicodedata

from gensim.models import Word2Vec
from gensim.models.callbacks import CallbackAny2Vec
import numpy as np

from ir_hw1.preprocessing import TOKENIZER_VERSION, TOKEN_RE, tokenize
from .association_sentences import SENTENCE_VERSION, split_sentences
from .corpus import ROOT, SNAPSHOT, load_corpus, sha256
from .core import stopwords
from .word_association import (VERSION, FIXED_TERMS, MODEL_NAMES, POLICY, TfidfWords,
                               EmbeddingWords, common_pool, compare_spaces, stable_hash, write_csv, write_json)


@dataclass(frozen=True)
class TrainingConfig:
    vector_size: int = 100
    window: int = 2
    min_count: int = 2
    epochs: int = 30
    seed: int = 42
    workers: int = 1
    sg: int = 0
    negative: int = 5
    sample: float = 0.001
    ns_exponent: float = 0.75
    alpha: float = 0.025
    min_alpha: float = 0.0001
    sorted_vocab: int = 1
    shrink_windows: bool = True
    cbow_mean: int = 1


def versions():
    return {"python": platform.python_version(), "platform": platform.platform(),
            **{name: version(name) for name in ("gensim", "numpy", "scipy", "regex", "matplotlib", "streamlit")}}


def tokenizer_contract():
    return {"condition": "C", "version": TOKENIZER_VERSION, "regex": TOKEN_RE.pattern,
            "normalization": "NFC, casefold, curly apostrophe -> apostrophe, Unicode hyphens U+2010/U+2011 -> ASCII hyphen",
            "unicode_database": unicodedata.unidata_version, "regex_version": version("regex"),
            "keep_stopwords": False, "stemming": False, "search_compound_expansion": False,
            "stopwords_sha256": sha256(ROOT / "resources/stopwords.json"),
            "stopwords_version": json.loads((ROOT / "resources/stopwords.json").read_text(encoding="utf-8"))["version"],
            "stopwords_count": len(stopwords()),
            "source_sha256": sha256(ROOT / "ir_hw1/preprocessing.py")}


def prepare_documents(documents):
    """HW2 lexical PMID order; original block/sentence/token order inside a doc."""
    records, document_tokens, order = [], [], []
    blocked = stopwords()

    def c_terms(text):
        return [t.term for t in tokenize(text) if t.term not in blocked]

    for doc in sorted(documents.values(), key=lambda item: item.pmid):
        if not doc.pmid or doc.pmid in order or doc.content_scope != "abstract":
            raise ValueError("Requires unique PMID and abstract-only documents")
        order.append(doc.pmid)
        expected, actual = [], []
        for block_index, block in enumerate(doc.blocks):
            if block.kind != "abstract":
                continue
            expected.extend(c_terms(block.text))
            for number, sentence in enumerate(split_sentences(block.text)):
                tokens = c_terms(sentence.text)
                if tokens:
                    records.append({"pmid": doc.pmid, "block_index": block_index, "block_id": block.id,
                                    "sentence": number, "start": sentence.start, "end": sentence.end,
                                    "boundary_rule": sentence.rule, "tokens": tokens})
                    actual.extend(tokens)
        if actual != expected:
            raise ValueError(f"Sentence splitting changed C tokens: {doc.pmid}")
        document_tokens.append(expected)
    if not records:
        raise ValueError("No training sentences")
    return order, document_tokens, records


class EpochLossRecorder(CallbackAny2Vec):
    def __init__(self, name, output):
        self.name, self.output, self.rows, self.previous = name, output, [], 0.

    def on_epoch_begin(self, model):
        self.start = perf_counter()

    def on_epoch_end(self, model):
        cumulative = float(model.get_latest_training_loss())
        delta = cumulative - self.previous
        if not np.isfinite(cumulative) or delta < 0:
            raise ValueError("Invalid cumulative training loss")
        row = {"epoch": len(self.rows) + 1, "loss": delta, "cumulative_loss": cumulative,
               "seconds": perf_counter() - self.start}
        self.rows.append(row)
        self.previous = cumulative
        with self.output.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row) + "\n")
        print(json.dumps({"model": self.name, **row}), flush=True)


def train_model(sequences, output, config, shared, name):
    """Always constructs a new Word2Vec; no resume/load branch exists here."""
    output.mkdir()
    write_json(output / "metadata.json", {"status": "training", "config": asdict(config)})
    start = perf_counter()
    model = Word2Vec(**asdict(config), hashfxn=stable_hash)
    model.build_vocab(sequences)
    if len(model.wv) < 2:
        raise ValueError("Insufficient min_count vocabulary")
    initial_vectors_sha256 = __import__("hashlib").sha256(model.wv.vectors.tobytes()).hexdigest()
    callback = EpochLossRecorder(name, output / "epochs.jsonl")
    effective, raw = model.train(sequences, total_examples=model.corpus_count, epochs=config.epochs,
                                 compute_loss=True, callbacks=[callback])
    if len(callback.rows) != config.epochs or not np.isfinite(model.wv.vectors).all():
        raise ValueError("Training incomplete or non-finite vectors")
    # Save complete model in a single file; hashfxn lives in an importable HW3 module.
    model.save(str(output / "word2vec.model"), separately=[])
    np.save(output / "vectors.npy", model.wv.vectors, allow_pickle=False)
    write_json(output / "vocabulary.json", model.wv.index_to_key)
    write_csv(output / "vocabulary.csv", [{"index": i, "term": t, "cf": int(model.wv.get_vecattr(t, "count"))}
                                            for i, t in enumerate(model.wv.index_to_key)])
    write_csv(output / "epoch_losses.csv", callback.rows)
    metadata = {**shared, "status": "complete", "name": name,
                "architecture": "Skip-Gram" if config.sg else "CBOW", "config": asdict(config),
                "resolved_additional_parameters": {key: getattr(model, key) for key in
                    ("hs", "batch_words", "max_vocab_size", "max_final_vocab", "null_word", "compute_loss")},
                "initialization": "New Word2Vec constructor + build_vocab; no loaded weights or pretrained vectors",
                "initial_vectors_bytes_sha256": initial_vectors_sha256,
                "hash_function": "SHA256 first 8 bytes little endian (same as HW2)",
                "vocabulary_size": len(model.wv), "effective_training_words_all_epochs": int(effective),
                "raw_training_words_all_epochs": int(raw), "seconds": perf_counter() - start,
                "epoch_losses": callback.rows,
                "loss_policy": "First differences of cumulative negative-sampling loss in one train call. Float32 accumulation may lose precision; not semantic accuracy or cross-architecture evidence.",
                "artifacts_sha256": {p.name: sha256(p) for p in output.iterdir() if p.is_file() and p.name != "metadata.json"}}
    # Offline reload is part of completing each individual model.
    reloaded = Word2Vec.load(str(output / "word2vec.model"))
    if reloaded.wv.index_to_key != model.wv.index_to_key or not np.array_equal(reloaded.wv.vectors, model.wv.vectors):
        raise ValueError("Offline reload differs")
    metadata["offline_reload_exact"] = True
    write_json(output / "metadata.json", metadata)
    return EmbeddingWords(model.wv.index_to_key, model.wv.vectors), metadata


def train_run(output: Path):
    output = output.resolve()
    if not output.is_relative_to(ROOT.resolve()):
        raise ValueError("All training outputs must stay inside HW3")
    documents, corpus = load_corpus(SNAPSHOT)
    if len(documents) != 3000:
        raise ValueError("Formal comparison requires exactly 3,000 abstracts")
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "manifest.json", {"version": VERSION, "status": "training"})
    order, document_tokens, records = prepare_documents(documents)
    sequences = [record["tokens"] for record in records]
    write_json(output / "document_order.json", order)
    write_json(output / "fixed_terms.json", FIXED_TERMS)
    with (output / "sentences.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    write_json(output / "corpus_manifest.json", corpus)
    sources = ["ir_hw1/preprocessing.py", "ir_hw1/models.py", "ir_hw3/corpus.py", "ir_hw3/core.py", "resources/stopwords.json",
               "ir_hw3/association_sentences.py", "ir_hw3/word_association.py", "ir_hw3/embedding_training.py",
               "ir_hw3/association_report.py"]
    (output / "sources").mkdir()
    source_hashes = {}
    for name in sources:
        target = output / "sources" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
        source_hashes[name] = sha256(target)
    shared = {"version": VERSION, "corpus_sha256": corpus["sha256"],
              "snapshot_manifest_sha256": sha256(SNAPSHOT / "snapshot.json"),
              "selection_sha256": corpus["selection_sha256"], "documents": len(documents),
              "sentences": len(records), "tokens": sum(map(len, sequences)),
              "input_vocabulary_size": len(Counter(t for s in sequences for t in s)),
              "sentences_sha256": sha256(output / "sentences.jsonl"),
              "document_order_sha256": sha256(output / "document_order.json"),
              "order": "PMID lexical ascending; source block order; detected sentence order; C token source order after stopword removal",
              "tokenizer": tokenizer_contract(), "sentence_rules": SENTENCE_VERSION,
              "sentence_source_sha256": sha256(ROOT / "ir_hw3/association_sentences.py"),
              "boundary_policy": "No context crosses documents, abstract blocks or detected sentences; per-document flattened sentence tokens equal whole-block C tokens exactly; windows count retained tokens",
              "source_sha256": source_hashes, "versions": versions(),
              "created_at_utc": datetime.now(timezone.utc).isoformat()}
    tfidf = TfidfWords.build(document_tokens)
    tfidf.save(output / "tfidf")
    write_json(output / "tfidf/metadata.json", {**shared, "status": "complete", "shape": list(tfidf.matrix.shape),
                                               "policy": POLICY["tfidf"], "full_vocabulary": True})
    print(json.dumps({"prepared": True, **{k: shared[k] for k in ("documents", "sentences", "tokens", "input_vocabulary_size")}}), flush=True)
    (output / "models").mkdir()
    models, metadata = {}, {}
    for name in MODEL_NAMES:
        config = replace(TrainingConfig(), sg=int(name.startswith("skipgram")), window=int(name[-1]))
        models[name], metadata[name] = train_model(sequences, output / "models" / name, config, shared, name)
    pool = common_pool(tfidf, models)
    write_json(output / "candidate_pool.json", pool)
    results = compare_spaces(tfidf, models, pool)
    for name, rows in results.items():
        write_csv(output / f"{name}.csv", rows)
    write_json(output / "results.json", results)
    from .association_report import build_report
    build_report(output, shared, tfidf, models, pool, metadata, results)
    manifest = {**shared, "version": VERSION, "status": "complete", "policies": POLICY,
                "candidate_pool_size": len(pool), "models": list(MODEL_NAMES),
                "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                "artifacts_sha256": {p.relative_to(output).as_posix(): sha256(p)
                                      for p in sorted(output.rglob("*")) if p.is_file() and p.name != "manifest.json"}}
    write_json(output / "manifest.json", manifest)
    print(json.dumps({"status": "complete", "output": str(output), "pool": len(pool), "summary": results["summary"]}), flush=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/word_association/runs" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    args = parser.parse_args()
    train_run(args.output)


if __name__ == "__main__":
    main()
