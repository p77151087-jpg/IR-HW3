import math
import pytest
from ir_hw1.models import Document, TextBlock
from ir_hw3.core import Engine, VECTOR_METHODS, Settings, term_weight, terms

def documents(*texts):
    return {str(i): Document(pmcid="PMID" + str(i), pmid=str(i), title="Document " + str(i),
                             blocks=[TextBlock("b0", "abstract", "Abstract", text)], language="eng")
            for i, text in enumerate(texts, 1)}

@pytest.mark.parametrize("method,expected", [("tf", 10), ("log_tf", 2),
                                             ("idf", 2), ("tfidf", 20), ("log_tfidf", 4)])
def test_weight_hand_calculations(method, expected):
    assert term_weight(10, 2, method) == pytest.approx(expected)
    assert term_weight(0, 2, method) == 0

def test_per_document_tf_df_and_query_repetition():
    engine = Engine(documents("alpha alpha beta", "alpha beta beta", "gamma", ""), Settings("B"))
    assert engine.n == 4
    assert engine.counts["1"]["alpha"] == 2
    assert engine.cf["alpha"] == 3
    assert engine.df["alpha"] == 2
    assert engine.idf["alpha"] == pytest.approx(0.3010299956639812)
    ranking = engine.rank("alpha alpha beta", "tf")
    assert ranking[0]["pmid"] == "1"
    assert ranking[0]["score"] == pytest.approx(1)
    assert ranking[1]["score"] == pytest.approx(0.8)
    assert engine.query("alpha alpha beta", "tf")[0]["alpha"] == 2

@pytest.mark.parametrize("method", list(VECTOR_METHODS))
def test_cosine_l2_equivalence_and_explanation_sum(method):
    engine = Engine(documents("alpha alpha beta", "alpha gamma gamma", "beta gamma", ""), Settings("B"))
    query = "alpha beta beta"
    check = engine.normalization_check(query, method)
    assert check["same_ranking"]
    assert check["max_score_difference"] < 1e-12
    for row in engine.rank(query, method):
        assert sum(r["cosine_contribution"] for r in engine.explain(query, row["pmid"], method)) == pytest.approx(row["score"])

def test_dot_product_length_effect_is_not_cosine():
    engine = Engine(documents("alpha", "alpha alpha beta beta beta beta"), Settings("B"))
    assert engine.rank("alpha", "tf", scoring="dot")[0]["pmid"] == "2"
    assert engine.rank("alpha", "tf", scoring="dot", normalize=True)[0]["pmid"] == "1"
    assert engine.rank("alpha", "tf")[0]["pmid"] == "1"

def test_ubiquitous_idf_zero_and_smoothing():
    plain = Engine(documents("alpha", "alpha alpha"), Settings("B", "standard"))
    smooth = Engine(plain.documents, Settings("B", "smooth"))
    assert plain.idf["alpha"] == 0
    assert plain.rank("alpha", "idf") == []
    assert smooth.idf["alpha"] == 1
    assert [r["pmid"] for r in smooth.rank("alpha", "idf")] == ["1", "2"]


@pytest.mark.parametrize("condition", ["B", "C", "D"])
@pytest.mark.parametrize("idf_mode,expected", [("standard", 0.3010299956639812),
                                               ("smooth", 1.2218487496163564)])
def test_log10_idf_known_values_in_all_settings(condition, idf_mode, expected):
    engine = Engine(documents("alpha alpha beta", "alpha beta", "gamma", ""), Settings(condition, idf_mode))
    assert engine.idf["alpha"] == pytest.approx(expected)
    assert term_weight(100, engine.idf["alpha"], "log_tfidf") == pytest.approx(3 * expected)

def test_oov_does_not_dilute_vector_and_zero_queries():
    engine = Engine(documents("alpha beta", "gamma"))
    assert engine.rank("alpha unknownword", "tf") == engine.rank("alpha", "tf")
    assert engine.query("alpha unknownword", "tf")[2] == ["unknownword"]
    for query in ("", "the and", "???", "unseenword"):
        assert engine.rank(query) == []

def test_preprocessing_same_for_query_and_document_preserves_biomedical_terms():
    assert terms("GLP-1 β-cells 3.5", "B") == ["glp-1", "β-cells", "3.5"]
    assert terms("the therapies GLP-1", "D") == ["therapi", "glp-1"]
    engine = Engine(documents("the therapies GLP-1"), Settings("D", "smooth"))
    assert set(engine.counts["1"]) == set(engine.query("the therapies GLP-1", "tf")[1])

def test_abstract_only_and_safe_highlighting():
    docs = documents("alpha <script>alert('bad')</script> beta")
    docs["1"].title = "titleonlyterm"
    engine = Engine(docs, Settings("B"))
    assert "titleonlyterm" not in engine.df
    snippet = engine.snippet("1", "alpha")
    assert "<mark>alpha</mark>" in snippet
    assert "<script>" not in snippet
    assert "&lt;script&gt;" in snippet

def test_numeric_pmid_ties_are_stable():
    docs = documents("alpha", "alpha")
    docs["10"] = docs.pop("1")
    engine = Engine(docs, Settings("B"))
    assert [r["pmid"] for r in engine.rank("alpha", "tf")] == ["2", "10"]

def test_invalid_settings_methods_queries():
    with pytest.raises(ValueError):
        Settings("A")
    with pytest.raises(ValueError):
        Engine({})
    engine = Engine(documents("alpha"))
    with pytest.raises(ValueError):
        engine.rank("alpha", "bad")
    with pytest.raises(ValueError):
        engine.rank("alpha", scoring="bad")
    with pytest.raises(ValueError):
        engine.rank("a" * 2001)
