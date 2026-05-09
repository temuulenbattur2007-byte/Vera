"""
tools/web_search.py — Tavily web search.
"""
import urllib.request
import urllib.parse
import json
from config import TAVILY_API_KEY

TAVILY_URL = "https://api.tavily.com/search"


def tavily_search(query: str, max_results: int = 5) -> list[dict]:
    payload = json.dumps({
        "api_key":        TAVILY_API_KEY,
        "query":          query,
        "max_results":    max_results,
        "search_depth":   "basic",
        "include_answer": True,
    }).encode("utf-8")

    req = urllib.request.Request(
        TAVILY_URL, data=payload,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        results = []
        if data.get("answer"):
            results.append({"title": "Direct Answer", "url": "", "content": data["answer"]})
        for r in data.get("results", [])[:max_results]:
            results.append({
                "title":   r.get("title", ""),
                "url":     r.get("url", ""),
                "content": r.get("content", "")[:400]
            })
        return results
    except Exception as e:
        return [{"title": "Error", "url": "", "content": f"Search failed: {e}"}]


def format_for_context(results: list[dict]) -> str:
    if not results:
        return "No results found."
    lines = ["[Web Search Results]"]
    for i, r in enumerate(results, 1):
        lines.append(f"\n{i}. {r['title']}")
        if r["url"]: lines.append(f"   Source: {r['url']}")
        lines.append(f"   {r['content']}")
    return "\n".join(lines)


def web_search(query: str = None, search: str = None, **kwargs) -> str:
    query = query or search or next(iter(kwargs.values()), None)
    if not query: return "No search query provided"
    results = tavily_search(query)
    lines = []
    for r in results[:3]:
        if r["title"] != "Direct Answer":
            lines.append(f"• {r['title']}: {r['content'][:150]}...")
        else:
            lines.append(r["content"])
    return "\n".join(lines)