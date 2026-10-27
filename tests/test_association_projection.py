"""Independent geometry checks for display-only word projections."""
import numpy as np
import pytest

from ir_hw3.association_projection import compare_word_maps, normalized_word_vectors, pca_xy, tsne_xy, word_map_svg
from ir_hw3.word_association import EmbeddingWords, TfidfWords


def test_pca_matches_independent_centered_gram_eigendecomposition():
    vectors = np.array([[1, 2, -1, 4], [-2, 3, 1, 0], [4, 0, 2, 1], [0, -1, 5, 2]], dtype=float)
    xy, retained, rank = pca_xy(vectors)
    centered = vectors - vectors.mean(axis=0)
    gram = centered @ centered.T
    values, directions = np.linalg.eigh(gram)
    order = np.argsort(values)[::-1]
    expected = directions[:, order[:2]] * np.sqrt(np.maximum(values[order[:2]], 0))
    # Gram products compare geometry without assuming arbitrary PCA axis signs.
    np.testing.assert_allclose(xy @ xy.T, expected @ expected.T, atol=1e-12)
    assert retained == pytest.approx(values[order[:2]].sum() / np.trace(gram))
    assert rank == 3
    np.testing.assert_allclose(xy.mean(axis=0), 0, atol=1e-14)
    np.testing.assert_array_equal(xy, pca_xy(vectors)[0])
    for i in range(len(vectors)):
        for j in range(len(vectors)):
            assert np.linalg.norm(xy[i] - xy[j]) <= np.linalg.norm(vectors[i] - vectors[j]) + 1e-12


def test_word_l2_uses_all_document_coordinates_and_never_mutates_spaces():
    tfidf = TfidfWords.build([["insulin", "insulin", "glucose"], ["glucose", "receptor"],
                             ["receptor", "other"], ["other"]])
    terms = ["insulin", "glucose", "receptor"]
    old = tfidf.matrix.toarray().copy()
    norms = tfidf.norms.copy()
    normalized = normalized_word_vectors(tfidf, terms)
    assert normalized.shape == (3, 4)
    columns = old[:, [tfidf.lookup[t] for t in terms]].T
    np.testing.assert_allclose(normalized, columns / np.linalg.norm(columns, axis=1)[:, None])
    np.testing.assert_array_equal(tfidf.matrix.toarray(), old)
    np.testing.assert_array_equal(tfidf.norms, norms)
    for i, term in enumerate(terms):
        np.testing.assert_allclose(normalized @ normalized[i], tfidf.scores(term, terms))


def test_identical_ordered_words_and_separate_geometry_preserve_original_cosines():
    first = EmbeddingWords(["insulin", "glucose", "receptor", "custom"],
                           [[1, 0, 0], [1, 1, 0], [0, 0, 1], [0, 1, 2]])
    second = EmbeddingWords(first.words, [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [1, 2, 3]])
    before = second.vectors.copy()
    maps = compare_word_maps(first, second, "custom", "glucose")
    assert maps["terms"] == ["insulin", "glucose", "receptor", "custom"]
    assert maps["status"] == "ok"
    for name, space in (("tfidf", first), ("embedding", second)):
        assert [row["term"] for row in maps["spaces"][name]["rows"]] == maps["terms"]
        assert maps["spaces"][name]["pair_cosine"] == float(space.scores("custom", ["glucose"])[0])
        assert maps["spaces"][name]["dimensions"] == 3
        assert max(abs(row[a]) for row in maps["spaces"][name]["rows"] for a in ("x", "y")) < maps["extent"]
    np.testing.assert_array_equal(second.vectors, before)
    assert compare_word_maps(first, second, "insulin", "glucose")["spaces"]["embedding"]["pair_cosine"] == -1


def test_cached_tfidf_interface_does_not_depend_on_reloaded_class_identity():
    from types import SimpleNamespace
    space = TfidfWords.build([["insulin", "glucose"], ["glucose", "receptor"], ["receptor"]])
    # Same fields on a cached object from another class generation, as in Streamlit.
    cached = SimpleNamespace(lookup=space.lookup, matrix=space.matrix)
    assert not isinstance(cached, TfidfWords)
    np.testing.assert_array_equal(normalized_word_vectors(cached, ["insulin", "glucose"]),
                                  normalized_word_vectors(space, ["insulin", "glucose"]))


def test_unavailable_selected_word_never_gets_a_synthetic_coordinate():
    first = EmbeddingWords(["insulin", "glucose", "receptor"], np.eye(3))
    second = EmbeddingWords(["insulin", "glucose", "receptor"], [[0, 0, 0], [1, 0, 0], [0, 1, 0]])
    for left in ("insulin", "unknown"):
        maps = compare_word_maps(first, second, left, "glucose")
        assert maps["status"] == "unavailable"
        assert maps["spaces"] == {}
        assert left not in maps["terms"]
        assert left in [row["term"] for row in maps["missing"]]


def test_duplicate_pair_has_one_highlighted_point_and_rank_one_is_supported():
    space = EmbeddingWords(["insulin", "glucose", "receptor"], [[1, 0], [-1, 0], [1, 0]])
    maps = compare_word_maps(space, space, "insulin", "insulin")
    data = maps["spaces"]["embedding"]
    assert len(data["rows"]) == 3
    assert [row["role"] for row in data["rows"]] == ["詞 A／B", "參考詞", "參考詞"]
    assert data["rank"] == 1
    assert data["retained_variance"] == pytest.approx(1)
    assert data["pair_cosine"] == 1
    np.testing.assert_allclose([row["y"] for row in data["rows"]], 0, atol=1e-14)


def test_svg_escapes_labels_and_has_equal_axis_units_and_hover_text():
    data = {"rows": [{"term": '<script>alert("x")</script>', "x": 0.5, "y": 0.5, "role": "詞 A"},
                     {"term": "glucose", "x": -0.5, "y": -0.5, "role": "詞 B"}]}
    svg = word_map_svg(data, [row["term"] for row in data["rows"]], 1, '<img src="x">')
    assert '<script>' not in svg and '<img ' not in svg
    assert '&lt;script&gt;' in svg and '&lt;img ' in svg
    assert 'viewBox="0 0 520 520"' in svg
    assert 'cx="358.00" cy="162.00"' in svg  # same 98 px movement on X and Y
    assert '二維投影座標' in svg and '主成分 1' in svg and '主成分 2' in svg
    assert '<title>' in svg and 'javascript' not in svg.lower()


def test_tsne_is_repeatable_changes_with_perplexity_and_does_not_mutate_input():
    vectors = np.random.default_rng(9).normal(size=(10, 11))
    vectors /= np.linalg.norm(vectors, axis=1)[:, None]
    before = vectors.copy()
    xy, diagnostics = tsne_xy(vectors, 3)
    again, repeated = tsne_xy(vectors, 3)
    np.testing.assert_array_equal(xy, again)
    np.testing.assert_array_equal(vectors, before)
    assert diagnostics == repeated
    assert xy.shape == (10, 2) and np.isfinite(xy).all()
    assert not np.array_equal(xy, tsne_xy(vectors, 5)[0])
    assert diagnostics["parameters"]["random_state"] == 42
    assert diagnostics["parameters"]["method"] == "exact"
    assert diagnostics["parameters"]["init"] == "random"
    assert 250 <= diagnostics["iterations"] <= 1000
    assert np.isfinite(diagnostics["optimizer_reported_kl"])


@pytest.mark.parametrize("perplexity", [0, -1, 10, float("nan")])
def test_tsne_rejects_invalid_perplexity(perplexity):
    with pytest.raises(ValueError, match="perplexity"):
        tsne_xy(np.eye(10), perplexity)


def test_tsne_uses_full_spaces_without_pca_and_keeps_same_words_and_original_scores(monkeypatch):
    from ir_hw3 import association_projection
    tfidf = TfidfWords.build([["insulin", "glucose"], ["glucose", "receptor"], ["receptor"], ["custom"]])
    embedding = EmbeddingWords(tfidf.words, np.random.default_rng(3).normal(size=(4, 100)))
    original = association_projection.tsne_xy
    inputs = []
    def record(vectors, perplexity):
        inputs.append((vectors.shape, perplexity))
        return original(vectors, perplexity)
    def forbidden(*args):
        raise AssertionError("t-SNE must not use the PCA 2D coordinates as input")
    monkeypatch.setattr(association_projection, "pca_xy", forbidden)
    monkeypatch.setattr(association_projection, "tsne_xy", record)
    maps = compare_word_maps(tfidf, embedding, "custom", "glucose", "tsne", 5)
    assert maps["projection"] == "tsne" and maps["status"] == "ok"
    assert inputs == [((4, 4), 3.0), ((4, 100), 3.0)]
    for name, space in (("tfidf", tfidf), ("embedding", embedding)):
        data = maps["spaces"][name]
        assert [row["term"] for row in data["rows"]] == maps["terms"]
        assert data["retained_variance"] is None and data["rank"] is None
        assert data["pair_cosine"] == float(space.scores("custom", ["glucose"])[0])
        svg = word_map_svg(data, maps["pair"], maps["extent"], name, "tsne")
        assert "t-SNE 維度 1" in svg and "t-SNE 維度 2" in svg and "主成分" not in svg
    with pytest.raises(ValueError, match="投影方式"):
        compare_word_maps(tfidf, embedding, "insulin", "glucose", "unknown")
