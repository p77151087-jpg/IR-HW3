"""PubMed abstract parsing adapted from the retained HW1 parser.

Only abstract-body blocks enter HW3. Reference ArticleIdList elements are never
used as the document's identifiers. No HW2 runtime dependency is introduced.
"""
import re
from defusedxml import ElementTree as SafeET
from ir_hw1.models import Document, TextBlock


def readable(node):
    if node is None:
        return ""
    def flatten(element):
        pieces = [element.text or ""]
        for child in element:
            tag = child.tag.rsplit("}", 1)[-1]
            if tag not in {"graphic", "media", "tex-math", "supplementary-material", "inline-supplementary-material"}:
                text = flatten(child)
                pieces.append(" " + text + " " if tag in {"break", "td", "th", "p", "xref", "ext-link"} else text)
            pieces.append(child.tail or "")
        return "".join(pieces)
    return " ".join(flatten(node).split())


def parse_response(raw):
    if len(raw) > 25 * 1024 * 1024:
        raise ValueError("PubMed XML 超過 25 MiB。")
    root = SafeET.fromstring(raw, forbid_entities=True, forbid_external=True)
    if root.tag != "PubmedArticleSet":
        raise ValueError("EFetch 未回傳 PubmedArticleSet。")
    return root


def parse_article(article):
    if article.tag != "PubmedArticle":
        raise ValueError("unsupported_book_record")
    citation = article.find("MedlineCitation")
    pmid = readable(citation.find("PMID")) if citation is not None else ""
    if not re.fullmatch(r"[1-9]\d*", pmid):
        raise ValueError("invalid_pmid")
    content = citation.find("Article")
    if content is None:
        raise ValueError("missing_article")
    if "eng" not in [readable(node).lower() for node in content.findall("Language")]:
        raise ValueError("language_not_confirmed_english")
    title = readable(content.find("ArticleTitle"))
    if not title:
        raise ValueError("missing_title")
    blocks = []
    for node in content.findall("./Abstract/AbstractText"):
        if text := readable(node):
            label = node.get("Label", "").strip()
            blocks.append(TextBlock(f"b{len(blocks)}", "abstract", "摘要" + (" / " + label if label else ""), text))
    if not blocks:
        raise ValueError("empty_abstract")
    ids = {node.get("IdType"): readable(node) for node in article.findall("./PubmedData/ArticleIdList/ArticleId")}
    pmcid = ids.get("pmc", "").upper()
    if not re.fullmatch(r"PMC[1-9]\d*", pmcid):
        pmcid = "PMID" + pmid
    pubdate = content.find("./Journal/JournalIssue/PubDate")
    year = readable(pubdate.find("Year")) if pubdate is not None else ""
    if not year and pubdate is not None:
        match = re.search(r"\b\d{4}\b", readable(pubdate.find("MedlineDate")))
        year = match.group() if match else ""
    return Document(pmcid, title, blocks, pmid=pmid, doi=ids.get("doi", ""), year=year,
                    language="eng", content_scope="abstract",
                    license=readable(content.find("./Abstract/CopyrightInformation")),
                    source_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/")
