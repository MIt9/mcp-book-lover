"""Book recommendations via Open Library API."""

import httpx

BASE_URL = "https://openlibrary.org"


def search_books_online(query: str, limit: int = 10) -> list[dict]:
    """Search Open Library for books."""
    try:
        resp = httpx.get(f"{BASE_URL}/search.json", params={"q": query, "limit": limit}, timeout=10)
        resp.raise_for_status()
        docs = resp.json().get("docs", [])
        return [
            {
                "title": d.get("title", "Unknown"),
                "author": ", ".join(d.get("author_name", ["Unknown"])),
                "year": d.get("first_publish_year", "?"),
                "key": d.get("key", ""),
            }
            for d in docs
        ]
    except Exception:
        return []


def get_recommendations_for_book(author: str = "", genre: str = "") -> list[dict]:
    """Get recommendations by author or genre/subject."""
    if author:
        results = _search_by_author(author)
        if results:
            return results
    if genre:
        return _search_by_subject(genre)
    return []


def _search_by_author(author: str) -> list[dict]:
    try:
        resp = httpx.get(f"{BASE_URL}/search.json",
                         params={"author": author, "limit": 15}, timeout=10)
        resp.raise_for_status()
        docs = resp.json().get("docs", [])
        return [
            {
                "title": d.get("title", "Unknown"),
                "author": ", ".join(d.get("author_name", [author])),
                "year": d.get("first_publish_year", "?"),
            }
            for d in docs
        ]
    except Exception:
        return []


def _search_by_subject(subject: str) -> list[dict]:
    try:
        resp = httpx.get(f"{BASE_URL}/subjects/{subject.lower().replace(' ', '_')}.json",
                         params={"limit": 15}, timeout=10)
        resp.raise_for_status()
        works = resp.json().get("works", [])
        return [
            {
                "title": w.get("title", "Unknown"),
                "author": ", ".join(a.get("name", "Unknown") for a in w.get("authors", [])),
                "year": w.get("first_publish_year", "?"),
            }
            for w in works
        ]
    except Exception:
        return []
