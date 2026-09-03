"""PubMed literature lookup for the doctor assistant, via NCBI's free E-utilities (no API key)."""

from __future__ import annotations

import json
import logging

import httpx

logger = logging.getLogger(__name__)

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
MAX_RESULTS = 5
TIMEOUT_SECONDS = 8.0


async def search_pubmed(query: str) -> str:
    """Search PubMed for clinical/medical literature matching `query`.

    Returns a JSON string of up to 5 results, each with pmid, title, authors, journal, year and
    a link to the article on pubmed.ncbi.nlm.nih.gov. Use this for evidence, guidelines or
    research questions - cite the returned titles/PMIDs rather than inventing a citation.
    """
    query = (query or "").strip()
    if not query:
        return json.dumps({"query": query, "results": []})
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            search = await client.get(
                f"{BASE}/esearch.fcgi",
                params={"db": "pubmed", "term": query, "retmode": "json", "retmax": MAX_RESULTS, "sort": "relevance"},
            )
            search.raise_for_status()
            ids = search.json().get("esearchresult", {}).get("idlist", [])
            if not ids:
                return json.dumps({"query": query, "results": []})
            summary = await client.get(
                f"{BASE}/esummary.fcgi", params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"}
            )
            summary.raise_for_status()
            docs = summary.json().get("result", {})
    except Exception as exc:  # noqa: BLE001 - a lookup failure just means no results, never a crash
        logger.warning("PubMed lookup failed (%s)", type(exc).__name__)
        return json.dumps({"query": query, "results": []})

    results = []
    for pmid in ids:
        doc = docs.get(pmid)
        if not doc:
            continue
        authors = ", ".join(a.get("name", "") for a in doc.get("authors", [])[:3])
        results.append(
            {
                "pmid": pmid,
                "title": doc.get("title", "").strip(),
                "authors": authors,
                "journal": doc.get("fulljournalname") or doc.get("source", ""),
                "year": (doc.get("pubdate") or "")[:4],
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            }
        )
    return json.dumps({"query": query, "results": results})
