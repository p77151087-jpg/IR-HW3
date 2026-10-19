import hashlib
import json
import pytest
from defusedxml.common import EntitiesForbidden

from ir_hw1.models import Document, TextBlock
from ir_hw3 import acquisition, evaluation
from ir_hw3.corpus import load_corpus, sha256
from ir_hw3.pubmed import parse_article, parse_response


def article(pmid, *, language="eng", abstract="Alpha <i>beta</i> result."):
    return f'''<PubmedArticle><MedlineCitation><PMID>{pmid}</PMID><Article>
    <ArticleTitle>GLP-1 research {pmid}</ArticleTitle><Language>{language}</Language>
    <Journal><JournalIssue><PubDate><Year>2025</Year></PubDate></JournalIssue></Journal>
    <Abstract><AbstractText Label="RESULTS">{abstract}</AbstractText></Abstract>
    </Article></MedlineCitation><PubmedData><ArticleIdList><ArticleId IdType="doi">author-doi</ArticleId></ArticleIdList>
    <ReferenceList><Reference><ArticleIdList><ArticleId IdType="doi">wrong-reference-doi</ArticleId></ArticleIdList></Reference></ReferenceList>
    </PubmedData></PubmedArticle>'''


def test_pubmed_parsing_preserves_body_and_author_identifiers():
    doc = parse_article(parse_response(("<PubmedArticleSet>" + article("3") + "</PubmedArticleSet>").encode())[0])
    assert doc.pmid == "3" and doc.doi == "author-doi" and doc.year == "2025"
    assert doc.blocks[0].text == "Alpha beta result."
    assert "RESULTS" in doc.blocks[0].section and "RESULTS" not in doc.blocks[0].text
    assert all(block.kind == "abstract" for block in doc.blocks)


@pytest.mark.parametrize("kwargs,reason", [({"language": "fre"}, "language_not_confirmed_english"),
                                          ({"abstract": ""}, "empty_abstract")])
def test_pubmed_excludes_ineligible_records(kwargs, reason):
    root = parse_response(("<PubmedArticleSet>" + article("3", **kwargs) + "</PubmedArticleSet>").encode())
    with pytest.raises(ValueError, match=reason):
        parse_article(root[0])


def test_pubmed_rejects_entity_expansion():
    with pytest.raises(EntitiesForbidden):
        parse_response(b'<!DOCTYPE foo [<!ENTITY x "unsafe">]><PubmedArticleSet>&x;</PubmedArticleSet>')


def test_expansion_uses_cached_evidence_retains_base_and_never_overwrites_seal(tmp_path, monkeypatch):
    monkeypatch.setattr(acquisition, "ROOT", tmp_path)
    base = tmp_path / "data/corpus/base"
    (base / "raw-batches").mkdir(parents=True)
    docs = [Document("PMID" + str(i), "Base " + str(i), [TextBlock("b0", "abstract", "摘要", "Original body")],
                     pmid=str(i), language="eng").to_dict() for i in (1, 2)]
    encoded = ("\n".join(json.dumps(doc) for doc in docs) + "\n").encode()
    (base / "abstracts.jsonl").write_bytes(encoded)
    (base / "selection.json").write_text("[]", encoding="utf-8")
    manifest = {"schema_version": 1, "status": "complete", "selected_pmids": ["1", "2"], "counts": {"selected": 2},
                "raw_files": [], "sha256": sha256(base / "abstracts.jsonl"), "selection_sha256": sha256(base / "selection.json"),
                "query": "GLP-1", "content": "abstract only", "sources": [], "copyright_notice": "test"}
    evaluation.atomic_json(base / "snapshot.json", manifest)
    requests = []
    def fake_request(root, name, endpoint, params):
        requests.append(params)
        raw = (json.dumps({"esearchresult": {"idlist": ["1", "2", "3", "4", "5"], "count": "5"}}).encode()
               if name.endswith(".json") else ("<PubmedArticleSet>" + article("3", language="fre") + article("4") + article("5") + "</PubmedArticleSet>").encode())
        path = root / "raw-batches" / name
        path.write_bytes(raw)
        return raw, {"file": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(raw).hexdigest(), "retrieved_at_utc": "test"}
    monkeypatch.setattr(acquisition, "cached_request", fake_request)
    output = tmp_path / "data/corpus/expanded"
    result = acquisition.expand_snapshot(base, output, 3, progress=lambda *args, **kwargs: None)
    assert list(load_corpus(output)[0]) == ["1", "2", "4"]
    assert (output / "abstracts.jsonl").read_bytes().startswith(encoded)
    assert (base / "abstracts.jsonl").read_bytes() == encoded
    assert result["counts"]["excluded"] == 1 and result["counts"]["added"] == 1
    assert requests[1]["id"] == "3,4,5"
    before = (output / "snapshot.json").read_bytes()
    assert acquisition.expand_snapshot(base, output, 3)["sha256"] == result["sha256"]
    assert len(requests) == 2
    with pytest.raises(ValueError, match="不可覆寫"):
        acquisition.expand_snapshot(base, output, 4)
    assert (output / "snapshot.json").read_bytes() == before


def test_manual_judgments_are_separated_when_corpus_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluation, "ROOT", tmp_path)
    legacy = tmp_path / "data/judgments/manual.json"
    monkeypatch.setattr(evaluation, "JUDGMENTS", legacy)
    queries = [{"qid": "Q1", "text": "GLP-1"}]
    evaluation.save_judgments("old", queries, ["1"], [{"qid": "Q1", "pmid": "1", "grade": 1, "reason": "Original judgment"}])
    before = legacy.read_bytes()
    assert evaluation.load_judgments("new", queries, ["1", "2"])["judgments"] == {}
    evaluation.save_judgments("new", queries, ["1", "2"], [{"qid": "Q1", "pmid": "2", "grade": 0, "reason": "New corpus judgment"}])
    assert legacy.read_bytes() == before
    assert evaluation.judgment_path("new") != legacy
    assert evaluation.load_judgments("old", queries, ["1"])["judgments"]["Q1"]["1"]["grade"] == 1
