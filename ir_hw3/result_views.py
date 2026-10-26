"""Presentation rows derived from rankings; never modify retrieval scores."""
from html import escape
from pathlib import Path

from .core import METHODS, order_id
from .normalization import normalization_comparison


def document_statistics(engine, query_terms, doc_id):
    return {"query_term_hits": sum(engine.counts[doc_id].get(term, 0) for term in set(query_terms)),
            "abstract_length_tokens": engine.lengths[doc_id]}


def ranking_details(engine, query_terms, ranking):
    """Count each unique query term once, using the scored abstract's tokens."""
    unique_terms = set(query_terms)
    return [{"rank": row["rank"], "pmid": row["pmid"], "score": row["score"],
             **document_statistics(engine, unique_terms, row["pmid"]), "title": row["title"]}
            for row in ranking]


def ranking_overview(rankings, engine, query_terms):
    """One document per row; preserve ordering and add abstract token statistics."""
    ranks = {method: {row["pmid"]: row["rank"] for row in ranking[:10]}
             for method, ranking in rankings.items()}
    doc_ids = set().union(*(set(items) for items in ranks.values()))

    def position(doc_id):
        found = [items[doc_id] for items in ranks.values() if doc_id in items]
        return -len(found), min(found), order_id(doc_id)

    return [{"pmid": doc_id,
             **{METHODS[method]: str(items[doc_id]) if doc_id in items else "—"
                for method, items in ranks.items()},
             **document_statistics(engine, query_terms, doc_id),
             "title": engine.documents[doc_id].title}
            for doc_id in sorted(doc_ids, key=position)]


def overview_html(rows):
    """Sortable display only: escape cells and append the bundled static script."""
    columns = [("pmid", "PMID"), *[(label, label) for label in METHODS.values()],
               ("query_term_hits", "詞命中數"), ("abstract_length_tokens", "文章長度"), ("title", "文章標題")]
    headings = "".join(
        f'<th scope="col" aria-sort="none" data-sort-type="{"text" if key == "title" else "number"}">'
        f'<button type="button" aria-label="{escape(label)}，點選排序">{escape(label)}</button></th>'
        for key, label in columns)
    body = "".join("<tr>" + "".join(
        f'<td class="{"article-title" if key == "title" else ""}">{escape(str(row[key]))}</td>'
        for key, _ in columns) + "</tr>" for row in rows)
    return """<style>
.rank-overview-scroll { max-height:560px; overflow:auto; width:100%; border:1px solid #dde6eb; border-radius:8px; }
.rank-overview-scroll:focus-visible { outline:2px solid #287e78; outline-offset:2px; }
.rank-overview-table { width:100%; min-width:1396px; table-layout:fixed; border-collapse:separate; border-spacing:0; font-size:14px; }
.rank-overview-table th,.rank-overview-table td { padding:10px; border-right:1px solid #dde6eb; border-bottom:1px solid #dde6eb; text-align:center; vertical-align:top; white-space:normal; }
.rank-overview-table th { position:sticky; top:0; z-index:2; background:#edf2f5; }
.rank-overview-table th button { display:block; width:100%; padding:0; border:0; background:transparent; color:inherit; font:inherit; font-weight:700; cursor:pointer; text-align:inherit; }
.rank-overview-table th button:hover { text-decoration:underline; }
.rank-overview-table th button:focus-visible { outline:2px solid #287e78; outline-offset:3px; }
.rank-overview-table th[aria-sort="none"] button::after { content:" ↕"; color:#697c89; }
.rank-overview-table th[aria-sort="descending"] button::after { content:" ▼"; color:#287e78; }
.rank-overview-table th[aria-sort="ascending"] button::after { content:" ▲"; color:#287e78; }
.rank-overview-table th:first-child,.rank-overview-table td:first-child { position:sticky; left:0; background:#f6f8fa; z-index:1; }
.rank-overview-table th:first-child { z-index:3; background:#edf2f5; }
.rank-overview-table td.article-title { text-align:left; overflow-wrap:anywhere; }
.rank-overview-sort-status { margin:6px 0 0; font-size:14px; color:#526673; }
</style>
<div class="rank-overview-scroll" role="region" aria-label="可左右捲動的六方法名次總覽" tabindex="0">
<table class="rank-overview-table" aria-label="六種方法的 Top 10 名次總覽">
<colgroup><col style="width:96px">""" + '<col style="width:80px">' * 6 + """<col style="width:100px"><col style="width:100px"><col style="width:620px"></colgroup>
<thead><tr>""" + headings + "</tr></thead><tbody>" + body + "</tbody></table></div>" + (
        '<p class="rank-overview-sort-status" role="status" aria-live="polite"></p><script>'
        + Path(__file__).with_name("ranking_overview.js").read_text(encoding="utf-8") + "</script>")


def top10_changes(baseline, compared, documents):
    """Separate shared, entering, and exiting documents without invented ranks."""
    old = {row["pmid"]: row["rank"] for row in baseline[:10]}
    new = {row["pmid"]: row["rank"] for row in compared[:10]}
    shared, entered, exited = [], [], []
    for doc_id, rank in new.items():
        document = {"pmid": doc_id, "title": documents[doc_id].title}
        if doc_id not in old:
            entered.append({"compared_rank": rank, **document})
            continue
        improvement = old[doc_id] - rank
        movement = (f"↑ 上升 {improvement} 名" if improvement > 0 else
                    f"↓ 下降 {-improvement} 名" if improvement < 0 else "名次相同")
        shared.append({"baseline_rank": old[doc_id], "compared_rank": rank,
                       "movement": movement, **document})
    for doc_id, rank in old.items():
        if doc_id not in new:
            exited.append({"baseline_rank": rank, "pmid": doc_id,
                           "title": documents[doc_id].title})
    return shared, entered, exited
