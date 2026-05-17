"""Multi-source book search — ported from book-tracker Flutter app.

Sources:
- Google Books API
- Open Library API
- Author.Today (scraping)
- Knigogo (scraping, uk/ru)
- LibGen (scraping)
- Flibusta (scraping, ru)
- Project Gutenberg (scraping, en)
"""

import re
import asyncio
from dataclasses import dataclass, field
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "uk-UA,uk;q=0.9,ru;q=0.8,en;q=0.7",
}

TIMEOUT = 10.0


@dataclass
class SearchResult:
    title: str
    author: str
    source: str
    year: str = ""
    cover_url: str = ""
    description: str = ""
    url: str = ""


@dataclass
class SourceInfo:
    id: str
    name: str
    languages: set
    search_fn: object  # async callable(query) -> list[SearchResult]


# --- HTTP helpers ---

async def _fetch(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        r = await client.get(url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
        return r.text if r.status_code == 200 else None
    except Exception:
        return None


async def _post_search(client: httpx.AsyncClient, url: str, query: str, referer: str = "") -> str | None:
    headers = {**HEADERS, "Content-Type": "application/x-www-form-urlencoded"}
    if referer:
        headers["Referer"] = referer
    data = {"do": "search", "subaction": "search", "story": query}
    try:
        r = await client.post(url, headers=headers, data=data, timeout=TIMEOUT, follow_redirects=True)
        return r.text if r.status_code == 200 else None
    except Exception:
        return None


# --- Source implementations ---

async def _search_google_books(client: httpx.AsyncClient, query: str) -> list[SearchResult]:
    try:
        r = await client.get(
            "https://www.googleapis.com/books/v1/volumes",
            params={"q": query, "maxResults": "15"},
            timeout=TIMEOUT
        )
        if r.status_code != 200:
            return []
        items = r.json().get("items", [])
        results = []
        for item in items:
            info = item.get("volumeInfo", {})
            results.append(SearchResult(
                title=info.get("title", ""),
                author=", ".join(info.get("authors", ["Unknown"])),
                source="Google Books",
                year=str(info.get("publishedDate", ""))[:4],
                cover_url=info.get("imageLinks", {}).get("thumbnail", ""),
                description=info.get("description", "")[:200],
            ))
        return results
    except Exception:
        return []


async def _search_open_library(client: httpx.AsyncClient, query: str) -> list[SearchResult]:
    try:
        r = await client.get(
            "https://openlibrary.org/search.json",
            params={"q": query, "limit": "15"},
            timeout=TIMEOUT
        )
        if r.status_code != 200:
            return []
        docs = r.json().get("docs", [])
        return [
            SearchResult(
                title=d.get("title", ""),
                author=", ".join(d.get("author_name", ["Unknown"])),
                source="Open Library",
                year=str(d.get("first_publish_year", "")),
            )
            for d in docs[:15]
        ]
    except Exception:
        return []


async def _search_knigogo(client: httpx.AsyncClient, query: str) -> list[SearchResult]:
    for base in ["https://knigogo.top/", "https://knigogo.net/"]:
        html = await _fetch(client, f"{base}?s={quote(query)}")
        if not html:
            continue
        items = _parse_wordpress(html, "Knigogo")
        if items:
            return items
    return []


async def _search_author_today(client: httpx.AsyncClient, query: str) -> list[SearchResult]:
    urls = [
        f"https://author.today/search?category=works&q={quote(query)}",
        f"https://author.today/search?q={quote(query)}",
    ]
    for url in urls:
        html = await _fetch(client, url)
        if not html:
            continue
        items = _parse_author_today(html)
        if items:
            return items
    return []


async def _search_libgen(client: httpx.AsyncClient, query: str) -> list[SearchResult]:
    url = f"https://libgen.is/search.php?req={quote(query)}&res=20&column=title"
    html = await _fetch(client, url)
    if not html:
        return []
    results = []
    rows = re.findall(r'<tr.*?</tr>', html, re.DOTALL)
    for row in rows:
        title_m = re.search(r'<a href="book/index\.php\?md5=[^"]+">([^<]+)</a>', row)
        author_m = re.search(r'<td><a href="search\.php\?req=[^"]+">([^<]+)</a>', row)
        if not title_m:
            continue
        results.append(SearchResult(
            title=_decode_html(title_m.group(1)),
            author=_decode_html(author_m.group(1)) if author_m else "Unknown",
            source="LibGen",
        ))
        if len(results) >= 10:
            break
    return results


async def _search_flibusta(client: httpx.AsyncClient, query: str) -> list[SearchResult]:
    for base in ["http://flibusta.site", "https://flibusta.site"]:
        url = f"{base}/booksearch?ask={quote(query)}"
        html = await _fetch(client, url)
        if not html:
            continue
        # Only parse the main content, not sidebar
        sidebar_idx = html.find('id="sidebar')
        if sidebar_idx > 0:
            html = html[:sidebar_idx]
        results = []
        # Flibusta wraps matches in <span> inside <a>, so strip tags from link text
        for m in re.finditer(r'<a href="(/b/\d+)"[^>]*>(.*?)</a>', html):
            href = m.group(1)
            raw_title = _strip_tags(m.group(2))
            title = _decode_html(raw_title).strip()
            if not _is_valid_title(title):
                continue
            # Skip non-book links like (читать), (fb2), (epub)
            if title.startswith('(') and title.endswith(')'):
                continue
            snippet = html[m.end():m.end() + 200]
            author_m = re.search(r'<a href="/a/[^"]+"[^>]*>(.*?)</a>', snippet)
            author = _strip_tags(_decode_html(author_m.group(1))) if author_m else "Unknown"
            results.append(SearchResult(
                title=title,
                author=author,
                source="Flibusta",
                url=f"{base}{href}",
            ))
            if len(results) >= 12:
                break
        if results:
            return results
    return []


async def _search_searchfloor(client: httpx.AsyncClient, query: str) -> list[SearchResult]:
    url = f"https://searchfloor.org/search?q={quote(query)}"
    html = await _fetch(client, url)
    if not html:
        return []
    results = []
    for m in re.finditer(r'<a[^>]*href="/b/(\d+)"[^>]*>([^<]+)</a>', html):
        title = _decode_html(m.group(2))
        if not _is_valid_title(title):
            continue
        # Look for author nearby
        snippet = html[m.start():m.start() + 500]
        author_m = re.search(r'<a[^>]*href="/a/[^"]*"[^>]*>([^<]+)</a>', snippet)
        results.append(SearchResult(
            title=title,
            author=_decode_html(author_m.group(1)) if author_m else "Unknown",
            source="Searchfloor",
            url=f"https://searchfloor.org/book/{m.group(1)}",
        ))
        if len(results) >= 15:
            break
    return results


async def search_searchfloor_by_author(author: str) -> list[SearchResult]:
    """Search searchfloor.org by author page — returns all books."""
    url = f"https://searchfloor.org/a/{quote(author)}"
    async with httpx.AsyncClient() as client:
        html = await _fetch(client, url)
    if not html:
        return []
    results = []
    for m in re.finditer(r'<a[^>]*href="/b/(\d+)"[^>]*>([^<]+)</a>', html):
        title = _decode_html(m.group(2))
        if not _is_valid_title(title):
            continue
        results.append(SearchResult(
            title=title,
            author=author,
            source="Searchfloor",
            url=f"https://searchfloor.org/book/{m.group(1)}",
        ))
    return results


async def _search_gutenberg(client: httpx.AsyncClient, query: str) -> list[SearchResult]:
    url = f"https://www.gutenberg.org/ebooks/search/?query={quote(query)}"
    html = await _fetch(client, url)
    if not html:
        return []
    results = []
    for m in re.finditer(r'<li class="booklink">(.*?)</li>', html, re.DOTALL):
        item = m.group(1)
        title_m = re.search(r'<span class="title">(.*?)</span>', item)
        author_m = re.search(r'<span class="subtitle">(.*?)</span>', item)
        if not title_m:
            continue
        results.append(SearchResult(
            title=_decode_html(_strip_tags(title_m.group(1))),
            author=_decode_html(_strip_tags(author_m.group(1))) if author_m else "Unknown",
            source="Project Gutenberg",
        ))
        if len(results) >= 10:
            break
    return results


# --- Parsers ---

def _parse_wordpress(html: str, source: str) -> list[SearchResult]:
    results = []
    for m in re.finditer(r'<article.*?</article>', html, re.DOTALL):
        article = m.group(0)
        title_m = (
            re.search(r'rel="bookmark">([^<]+)</a>', article) or
            re.search(r'<h2[^>]*>\s*<a[^>]*>([^<]+)</a>', article)
        )
        if not title_m:
            continue
        author_m = (
            re.search(r'Автор:\s*</span>\s*<a[^>]*>([^<]+)</a>', article) or
            re.search(r'rel="author">([^<]+)</a>', article)
        )
        results.append(SearchResult(
            title=_decode_html(title_m.group(1)),
            author=_decode_html(author_m.group(1)) if author_m else "Unknown",
            source=source,
        ))
        if len(results) >= 12:
            break
    return results


def _parse_author_today(html: str) -> list[SearchResult]:
    results = []
    soup = BeautifulSoup(html, "html.parser")
    # Find book titles in search results
    for title_div in soup.select(".book-title"):
        a = title_div.find("a")
        if not a:
            continue
        title = a.get_text(strip=True)
        if not _is_valid_title(title):
            continue
        # Find author in parent container
        parent = title_div.find_parent(class_=re.compile(r"book-row|book-card"))
        author = "Unknown"
        if parent:
            author_el = parent.select_one(".book-author a, a[href*='/u/']")
            if author_el:
                author = author_el.get_text(strip=True)
        results.append(SearchResult(title=title, author=author, source="Author.Today"))
        if len(results) >= 15:
            break
    # Fallback: anchors with /work/ in href
    if not results:
        for a in soup.find_all("a", href=re.compile(r"/work/\d+")):
            title = a.get_text(strip=True)
            if _is_valid_title(title) and len(title) > 3:
                results.append(SearchResult(title=title, author="Unknown", source="Author.Today"))
            if len(results) >= 15:
                break
    return results


# --- Helpers ---

def _decode_html(text: str) -> str:
    text = text.replace("&amp;", "&").replace("&quot;", '"')
    text = text.replace("&#039;", "'").replace("&lt;", "<").replace("&gt;", ">")
    return text.strip()


def _strip_tags(text: str) -> str:
    return re.sub(r'<[^>]+>', '', text).strip()


def _is_valid_title(title: str) -> bool:
    if not title or len(title) < 2 or len(title) > 200:
        return False
    blacklist = {"головна", "пошук", "search", "home", "menu", "login", "увійти",
                 "показать все", "show all", "next", "prev", "»", "«"}
    return title.lower().strip() not in blacklist


def _normalize(text: str) -> str:
    return re.sub(r'\s+', ' ', text.lower()).strip()


def _has_cyrillic(text: str) -> bool:
    return bool(re.search(r'[А-Яа-яІіЇїЄєҐґ]', text))


# --- Main search orchestrator ---

SOURCES = [
    SourceInfo("google_books", "Google Books", {"uk", "ru", "en"}, _search_google_books),
    SourceInfo("open_library", "Open Library", {"uk", "ru", "en"}, _search_open_library),
    SourceInfo("author_today", "Author.Today", {"uk", "ru"}, _search_author_today),
    SourceInfo("knigogo", "Knigogo", {"uk", "ru"}, _search_knigogo),
    SourceInfo("searchfloor", "Searchfloor", {"uk", "ru"}, _search_searchfloor),
    SourceInfo("libgen", "LibGen", {"uk", "ru", "en"}, _search_libgen),
    SourceInfo("flibusta", "Flibusta", {"ru"}, _search_flibusta),
    SourceInfo("gutenberg", "Project Gutenberg", {"en"}, _search_gutenberg),
]


def _select_sources(query: str, source_ids: list[str] | None = None) -> list[SourceInfo]:
    if source_ids:
        return [s for s in SOURCES if s.id in source_ids]
    if _has_cyrillic(query):
        return [s for s in SOURCES if "uk" in s.languages or "ru" in s.languages]
    return [s for s in SOURCES if "en" in s.languages]


async def search_all(query: str, source_ids: list[str] | None = None) -> list[SearchResult]:
    """Search all relevant sources in parallel, deduplicate, rank by relevance."""
    sources = _select_sources(query, source_ids)

    async with httpx.AsyncClient() as client:
        tasks = [s.search_fn(client, query) for s in sources]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

    results = []
    seen = set()
    for outcome in outcomes:
        if isinstance(outcome, Exception) or not outcome:
            continue
        for item in outcome:
            key = f"{_normalize(item.title)}|{_normalize(item.author)}"
            if key not in seen:
                seen.add(key)
                results.append(item)

    # Rank by relevance
    _rank_results(results, query)
    return results


def _rank_results(results: list[SearchResult], query: str):
    tokens = set(_normalize(query).split())
    if not tokens:
        return

    def score(r: SearchResult) -> int:
        title_norm = _normalize(r.title)
        author_norm = _normalize(r.author)
        s = 0
        query_norm = _normalize(query)
        if query_norm in title_norm or title_norm in query_norm:
            s += 10
        for t in tokens:
            if t in title_norm.split():
                s += 2
            if t in author_norm.split():
                s += 1
        return s

    results.sort(key=score, reverse=True)


def get_available_sources() -> list[dict]:
    return [{"id": s.id, "name": s.name, "languages": sorted(s.languages)} for s in SOURCES]
