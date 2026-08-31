"""Approved-source health information for the patient assistant."""

from __future__ import annotations

import json
import logging
import re

from app.core.config import settings

logger = logging.getLogger(__name__)

MAX_RESULTS = 3
MAX_SNIPPET_CHARS = 400
ALLOWED_DOMAINS = [
    "medlineplus.gov",
    "nlm.nih.gov",
    "nih.gov",
    "cdc.gov",
    "who.int",
    "nhs.uk",
    "fda.gov",
    "nice.org.uk",
]
_IDENTIFIERS = re.compile(
    r"[\w.+-]+@[\w-]+\.[\w.]+|\bMRN[-\s]?\d+\b|\+?\d[\d\s().-]{7,}\d|\b\d{4}-\d{2}-\d{2}\b", re.IGNORECASE
)


def _clean(text: str, limit: int) -> str:
    return " ".join((text or "").split())[:limit]


def _query(raw: str) -> str:
    return _clean(_IDENTIFIERS.sub("", raw), 200)


def _result(query: str, results: list[dict[str, str]]) -> str:
    return json.dumps({"topic": query, "results": results}, ensure_ascii=True)


async def search_health_information(query: str) -> str:
    """Return health-authority search results for an identifier-free topic."""
    from tavily import AsyncTavilyClient

    cleaned = _query(query)
    if not cleaned:
        return _result("", [])
    try:
        response = await AsyncTavilyClient(api_key=settings.TAVILY_API_KEY).search(
            cleaned, max_results=MAX_RESULTS, include_domains=ALLOWED_DOMAINS
        )
    except Exception as exc:
        logger.warning("Health information lookup failed (%s)", type(exc).__name__)
        return _result(cleaned, [])
    return _result(
        cleaned,
        [
            {
                "title": _clean(hit["title"], 120),
                "url": hit.get("url", ""),
                "summary": _clean(hit.get("content", ""), MAX_SNIPPET_CHARS),
            }
            for hit in (response.get("results") or [])
            if hit.get("title")
        ],
    )
