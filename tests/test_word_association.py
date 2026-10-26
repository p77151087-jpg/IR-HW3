"""Small mathematical examples; pytest never trains the formal four models."""
from collections import Counter
from dataclasses import asdict, replace
from itertools import combinations
import json

from gensim.models import Word2Vec
import numpy as np
import pytest

from ir_hw1.models import Document, TextBlock
from ir_hw3.association_sentences import split_sentences
from ir_hw3.embedding_training import TrainingConfig, prepare_documents, train_model
from ir_hw3.word_association import (TfidfWords, EmbeddingWords, common_pool, neighbors,
                                    overlap, spearman, single_term, pair_score, FIXED_TERMS, compare_spaces)


def cosine(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def small_tfidf():
    return TfidfWords.build([["a", "a", "b"], ["b", "c"], ["c", "c", "d"]])


def test_hand_calculated_word_columns_after_full_document_l2():
    index = small_tfidf()
    rare, common = np.log10(3), np.log10(3 / 2)
    norms = np.array([np.sqrt(4 * rare**2 + common**2), np.sqrt(2 * common**2),
                      np.sqrt(4 * common**2 + rare**2)])
    a = np.array([2 * rare / norms[0], 0, 0])
    b = np.array([common / norms[0], common / norms[1], 0])
    assert index.matrix.shape == (3, 4)
    np.testing.assert_allclose(index.document_norms, norms)
    np.testing.assert_allclose(index.matrix[:, index.lookup["a"]].toarray().ravel(), a)
    assert pair_score(index, "a", "b") == pytest.approx(cosine(a, b))
    # This is word-to-word, not the cosine between document rows.
    dense = index.matrix.toarray()
    assert pair_score(index, "a", "b") != pytest.approx(cosine(dense[0], dense[1]))
    np.testing.assert_allclose(np.linalg.norm(dense, axis=1), 1)
    np.testing.assert_array_equal(index.cf, [2, 2, 3, 1])
    np.testing.assert_array_equal(index.df, [1, 2, 2, 1])


def test_positive_idf_column_scaling_cancels_without_document_l2():
    index = small_tfidf()
    raw = index.counts.toarray()
    weighted = raw * index.idf
    for i, j in combinations(range(len(index.words)), 2):
        assert cosine(raw[:, i], raw[:, j]) == pytest.approx(cosine(weighted[:, i], weighted[:, j]))
    # Row L2 changes the relative document coordinates. IDF then acts indirectly.
    assert pair_score(index, "a", "b") != pytest.approx(cosine(weighted[:, 0], weighted[:, 1]))


def test_full_space_document_norms_do_not_change_with_candidate_selection():
    index = small_tfidf()
    original = index.document_norms.copy()
    score = index.scores("b", ["a"])[0]
    assert score == index.scores("b", index.words)[index.lookup["a"]]
    neighbors(index, "b", ["a", "b"], 5)
    np.testing.assert_array_equal(index.document_norms, original)
    assert index.matrix.shape[1] == 4


def test_zero_idf_oov_empty_documents_and_no_synthetic_vector():
    index = TfidfWords.build([["the", "x"], ["the", "y"]])
    assert index.status("the") == "zero_vector"
    assert index.status("absent") == "oov"
    assert pair_score(index, "the", "x") is None
    assert neighbors(index, "absent", ["x", "y"], 10)["returned"] == 0
    empty = TfidfWords.build([[], ["x"]])
    assert empty.counts.shape == (2, 1)
    assert empty.idf[0] == pytest.approx(np.log10(2))
    assert empty.document_norms[0] == 0


def test_shared_pool_is_fixed_four_way_intersection_not_selected_neighbors():
    index = TfidfWords.build([["a", "b", "z"], ["a", "c", "z"]])
    models = {str(i): EmbeddingWords(["a", "b", "c", "outside", "z"], np.ones((5, 2))) for i in range(4)}
    models["3"] = EmbeddingWords(["a", "c", "z"], np.ones((3, 2)))
    assert common_pool(index, models) == ["c"]  # a/z have zero IDF; b missing in model 4.


def test_topk_excludes_self_zeros_and_negatives_but_pair_scores_keep_negatives():
    space = EmbeddingWords(["q", "z", "a", "zero", "negative"], [[1, 0], [1, 1], [1, 1], [0, 1], [-1, 0]])
    result = neighbors(space, "q", space.words, 5)
    assert [r["term"] for r in result["rows"]] == ["a", "z"]
    assert result["requested"] == 5 and result["returned"] == 2
    assert pair_score(space, "q", "negative") == -1
    zero = EmbeddingWords(["q"], [[0, 0]])
    assert neighbors(zero, "q", ["q"], 5)["status"] == "zero_vector"


def test_ties_round_to_twelve_places_then_lexical_order():
    class Space:
        def status(self, term):
            return "ok"
        def scores(self, term, candidates):
            return np.array([.8, .8 + 1e-14])
    assert [r["term"] for r in neighbors(Space(), "q", ["a", "z"], 5)["rows"]] == ["a", "z"]


@pytest.mark.parametrize("k", [0, 1, 7, 21])
def test_invalid_k_is_explicit(k):
    with pytest.raises(ValueError):
        neighbors(small_tfidf(), "a", ["b"], k)


def test_overlap_uses_requested_denominator_even_with_short_results():
    first = {"status": "ok", "rows": [{"term": "a"}, {"term": "b"}]}
    second = {"status": "ok", "rows": [{"term": "a"}]}
    assert overlap(first, second, 5) == .2
    assert overlap(first, {"status": "oov", "rows": []}, 5) is None


@pytest.mark.parametrize("a,b,rho,count", [
    ([1, 2, 3], [1, 2, 3], 1, 3), ([1, 2, 3], [3, 2, 1], -1, 3),
    ([1, 1, 2], [1, 2, 3], np.sqrt(3) / 2, 3),
    ([1, None, 3], [1, 8, 3], 1, 2), ([1, 1], [2, 3], None, 2),
    ([None, 2], [1, 2], None, 1), ([], [], None, 0)])
def test_spearman_known_ties_missing_and_constant_cases(a, b, rho, count):
    result = spearman(a, b)
    assert result["valid_pairs"] == count
    assert result["rho"] is None if rho is None else result["rho"] == pytest.approx(rho)


def test_c_query_normalization_removes_stopwords_and_retains_compounds_and_unstemmed_words():
    assert single_term("GLP‑1") == "glp-1"
    assert single_term("THE") is None
    assert single_term("with") is None
    assert single_term("the insulin") is None
    assert single_term("not") == "not"
    assert single_term("receptors") == "receptors"
    assert single_term("1.5") == "1.5"
    assert single_term("GLP-1 receptor") is None


def test_sentence_and_document_order_abstract_only_and_no_context_crossing():
    documents = {p: Document("", "TITLEEXCLUDED", [TextBlock("one", "abstract", "", text),
                   TextBlock("title", "title", "", "ALSOEXCLUDED"), TextBlock("two", "abstract", "", "Other block.")],
                   pmid=p, content_scope="abstract")
                 for p, text in [("9", "Insulin works. Glucose changes."), ("10", "Dr. Smith used 1.5 mg. The trial ended.")]}
    order, tokens, records = prepare_documents(documents)
    assert order == ["10", "9"]
    assert all("titleexcluded" not in doc and "alsoexcluded" not in doc for doc in tokens)
    assert all(len(set(r["pmid"] for r in [row])) == 1 for row in records)
    assert not any("works" in r["tokens"] and "glucose" in r["tokens"] for r in records)
    assert not any("changes" in r["tokens"] and "other" in r["tokens"] for r in records)
    assert any("1.5" in r["tokens"] for r in records)
    assert len(split_sentences("Dr. Smith used 1.5 mg. The trial ended.")) == 2
    assert all([t for r in records if r["pmid"] == p for t in r["tokens"]] == token_doc for p, token_doc in zip(order, tokens))


def test_c_preparation_matches_retrieval_and_removes_stopwords_before_building_spaces():
    from ir_hw3.core import terms, stopwords
    from ir_hw3.embedding_training import tokenizer_contract
    text = "The insulin and glucose were measured. The and with. Not without receptors or GLP-1."
    documents = {"1": Document("", "TITLEEXCLUDED", [TextBlock("one", "abstract", "", text)],
                                pmid="1", content_scope="abstract")}
    order, tokens, records = prepare_documents(documents)
    assert order == ["1"]
    assert tokens == [terms(text, "C")]
    assert not stopwords().intersection(tokens[0])
    assert [row["tokens"] for row in records] == [
        ["insulin", "glucose", "measured"], ["not", "without", "receptors", "glp-1"]]
    assert not stopwords().intersection(TfidfWords.build(tokens).words)
    contract = tokenizer_contract()
    assert contract["condition"] == "C" and contract["keep_stopwords"] is False
    assert len(contract["stopwords_sha256"]) == 64


def test_fixed_45_pair_order_keeps_all_missing_terms_and_signed_scores():
    tfidf = TfidfWords.build([[FIXED_TERMS[0]], [FIXED_TERMS[1]], ["other"]])
    models = {"tiny": EmbeddingWords(FIXED_TERMS[:2], [[1, 0], [-1, 0]])}
    result = compare_spaces(tfidf, models, common_pool(tfidf, models))
    assert len(result["pairs"]) == 45
    assert [(r["left"], r["right"]) for r in result["pairs"]] == list(combinations(FIXED_TERMS, 2))
    assert result["pairs"][0]["tiny"] == -1
    assert result["pairs"][-1]["tiny"] is None
    assert len(result["term_status"]) == 10
    assert result["summary"][0]["valid_terms"] == 2
    assert result["summary"][0]["rho"] is None


def test_small_model_new_initialization_save_hash_and_fresh_process_reload(tmp_path):
    import subprocess
    import sys
    from ir_hw3.corpus import sha256
    config = replace(TrainingConfig(), epochs=1, min_count=2, sample=0)
    sentences = [["insulin", "glucose", "basal", "glucose", "insulin"]] * 12
    space, meta = train_model(sentences, tmp_path / "tiny", config, {"corpus_sha256": "test-only"}, "tiny")
    assert meta["status"] == "complete" and len(meta["epoch_losses"]) == 1
    assert meta["config"] == asdict(config)
    assert meta["offline_reload_exact"]
    for filename, expected in meta["artifacts_sha256"].items():
        assert sha256(tmp_path / "tiny" / filename) == expected
    loaded = Word2Vec.load(str(tmp_path / "tiny/word2vec.model"))
    assert loaded.wv.get_vecattr("glucose", "count") == 24
    code = "from gensim.models import Word2Vec; import sys; m=Word2Vec.load(sys.argv[1]); assert len(m.wv)==3"
    subprocess.run([sys.executable, "-B", "-c", code, str(tmp_path / "tiny/word2vec.model")], check=True)
    with pytest.raises(FileExistsError):
        train_model(sentences, tmp_path / "tiny", config, {}, "tiny")


@pytest.mark.parametrize("status", ["training", "failed"])
def test_incomplete_run_cannot_be_loaded_as_complete(tmp_path, status):
    from ir_hw3.word_association import AssociationRun, VERSION
    (tmp_path / "manifest.json").write_text(json.dumps({"version": VERSION, "status": status}), encoding="utf-8")
    with pytest.raises(ValueError, match="尚未完成"):
        AssociationRun(tmp_path)


def test_artifact_hash_mismatch_rejected_before_model_loading(tmp_path):
    from ir_hw3.word_association import AssociationRun, VERSION
    (tmp_path / "vectors.npy").write_bytes(b"changed")
    (tmp_path / "manifest.json").write_text(json.dumps({"version": VERSION, "status": "complete",
                                "artifacts_sha256": {"vectors.npy": "incorrect"}}), encoding="utf-8")
    with pytest.raises(ValueError, match="指紋不符"):
        AssociationRun(tmp_path)
