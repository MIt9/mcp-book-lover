"""MCP Book Lover server — book tracking, reviews, recommendations, conversion."""

import json
import asyncio


def _run_async(coro):
    """Run async coroutine safely, even if an event loop is already running."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        return pool.submit(asyncio.run, coro).result()
from mcp.server.fastmcp import FastMCP
from mcp_book_lover import db
from mcp_book_lover.convert import convert_book_file
from mcp_book_lover.recommendations import get_recommendations_for_book
from mcp_book_lover.search import search_all, get_available_sources, search_searchfloor_by_author

mcp = FastMCP("book-lover", instructions="""Personal book library assistant. Use these tools to help the user manage their reading life.

LIBRARY WORKFLOW:
- Add books with bl_add_book (set status: want_to_read → downloaded → reading → finished)
- Use bl_find_in_library to search before adding — avoid duplicates
- When finishing a book, call bl_update_book_status with status="finished", then prompt for a review via bl_review_book
- For series books, always set series + series_order fields

RECOMMENDATIONS:
- bl_suggest_next uses ratings and series reviews to score unread books — prefer it over generic lists
- bl_review_series is more useful than bl_review_book for scoring series (used by bl_suggest_next)
- Save interesting titles from searches with bl_save_recommendation, then bl_delete_recommendation after adding to library

SEARCH & DOWNLOAD:
- bl_search_books auto-selects sources by script: Cyrillic → uk/ru sources, Latin → en sources
- bl_find_download shows links (LibGen, Flibusta); bl_download_book actually downloads from searchfloor.org to ~/Books
- After downloading, update the book record with file_path via bl_add_book or note it in description

FORMAT CONVERSION:
- bl_convert_book preserves: chapters, bold/italic, inline images, cover, metadata
- Supported paths: epub↔fb2, fb2/epub/txt/pdf → pdf, any → txt
- PDF output requires a system Unicode font (Arial on macOS, DejaVu on Linux) for Cyrillic

STATS & GOALS:
- bl_set_goal sets a yearly reading target; bl_goal_progress shows progress bar
- bl_reading_stats gives top authors/genres useful for making recommendations
""")


@mcp.tool()
def bl_add_book(title: str, author: str, genre: str = "", language: str = "",
             status: str = "want_to_read", file_path: str = "",
             description: str = "", series: str = "", series_order: float = 0) -> str:
    """Add a book to your library.
    
    Args:
        title: Book title
        author: Author name
        genre: Genre (fiction, non-fiction, sci-fi, fantasy, etc.)
        language: Language code (uk, en, ru, etc.)
        status: Reading status — want_to_read, downloaded, reading, or finished
        file_path: Path to book file (epub, fb2, pdf, txt)
        description: Short description or notes
        series: Series name (e.g. "The Witcher", "Dune Chronicles")
        series_order: Order in series (e.g. 1, 2, 3)
    """
    book = db.add_book(title=title, author=author, genre=genre,
                       language=language, status=status,
                       file_path=file_path, description=description,
                       series=series, series_order=series_order)
    return json.dumps(book, ensure_ascii=False, indent=2)


@mcp.tool()
def bl_list_books(status: str = "", author: str = "", genre: str = "") -> str:
    """List books in your library with optional filters.
    
    Args:
        status: Filter by status (want_to_read, downloaded, reading, finished)
        author: Filter by author name (partial match)
        genre: Filter by genre (partial match)
    """
    books = db.list_books(
        status=status or None,
        author=author or None,
        genre=genre or None
    )
    if not books:
        return "No books found."
    lines = []
    for b in books:
        stars = f"{'⭐' * int(b['rating'])}" if b['rating'] else ""
        lines.append(f"[{b['id']}] {b['title']} — {b['author']} ({b['status']}) {stars}")
    return "\n".join(lines)


@mcp.tool()
def bl_update_book_status(book_id: int, status: str) -> str:
    """Update reading status of a book.
    
    Args:
        book_id: Book ID from the library
        status: New status — want_to_read, downloaded, reading, or finished
    """
    from datetime import datetime
    fields = {"status": status}
    if status == "finished":
        fields["date_read"] = datetime.now().isoformat()
    book = db.update_book(book_id, **fields)
    if not book:
        return f"Book {book_id} not found."
    return f"Updated: {book['title']} → {status}"


@mcp.tool()
def bl_delete_book(book_id: int) -> str:
    """Delete a book and all its reviews, quotes, and tags.
    
    Args:
        book_id: Book ID from the library
    """
    book = db.get_book(book_id)
    if not book:
        return f"Book {book_id} not found."
    db.delete_book(book_id)
    return f"🗑️ Deleted: {book['title']} — {book['author']}"


@mcp.tool()
def bl_review_book(book_id: int, text: str, rating: float) -> str:
    """Write a review for a book.
    
    Args:
        book_id: Book ID from the library
        text: Your review text
        rating: Rating from 1 to 5
    """
    if not (1 <= rating <= 5):
        return "Rating must be between 1 and 5."
    book = db.get_book(book_id)
    if not book:
        return f"Book {book_id} not found."
    review = db.add_review(book_id, text, rating)
    return f"Review added for '{book['title']}': {rating}/5\n{text}"


@mcp.tool()
def bl_get_reviews(book_id: int) -> str:
    """Get all reviews for a book.
    
    Args:
        book_id: Book ID from the library
    """
    book = db.get_book(book_id)
    if not book:
        return f"Book {book_id} not found."
    reviews = db.get_reviews(book_id)
    if not reviews:
        return f"No reviews for '{book['title']}' yet."
    lines = [f"Reviews for '{book['title']}':"]
    for r in reviews:
        lines.append(f"  {'⭐' * int(r['rating'])} ({r['date_created'][:10]})\n  {r['text']}")
    return "\n".join(lines)


@mcp.tool()
def bl_get_recommendations(book_id: int = 0, author: str = "", genre: str = "") -> str:
    """Get book recommendations based on a book, author, or genre.
    
    Args:
        book_id: Get recommendations based on this book (uses its author/genre)
        author: Search for books by this author
        genre: Search for books in this genre/subject
    """
    if book_id:
        book = db.get_book(book_id)
        if not book:
            return f"Book {book_id} not found."
        author = author or book["author"]
        genre = genre or book["genre"]
    
    if not author and not genre:
        return "Provide book_id, author, or genre for recommendations."
    
    results = get_recommendations_for_book(author=author, genre=genre)
    if not results:
        return "No recommendations found."
    
    lines = ["📚 Recommendations:"]
    for r in results[:10]:
        lines.append(f"  • {r['title']} — {r['author']} ({r.get('year', '?')})")
    return "\n".join(lines)


@mcp.tool()
def bl_find_in_library(query: str, status: str = "") -> str:
    """Search for books in YOUR library by title, author, series, or description.
    
    Args:
        query: Search text (matches title, author, series, description, genre)
        status: Optional filter by status (want_to_read, downloaded, reading, finished)
    """
    results = db.search_library(query, status=status)
    if not results:
        return f"No books matching '{query}' in your library."
    lines = [f"📚 Found {len(results)} book(s) in library:"]
    for b in results:
        status_icon = {"finished": "✅", "reading": "📖", "downloaded": "💾", "want_to_read": "📋"}.get(b["status"], "")
        series_info = f" [{b['series']} #{int(b['series_order'])}]" if b.get("series") else ""
        lines.append(f"  {status_icon} [{b['id']}] {b['title']} — {b['author']}{series_info}")
    return "\n".join(lines)


@mcp.tool()
def bl_search_books(query: str, sources: str = "") -> str:
    """Search for books across multiple sources (Google Books, Open Library, Author.Today, Knigogo, LibGen, Flibusta, Gutenberg).

    Sources are auto-selected by language (Cyrillic → uk/ru sources, Latin → en sources).
    
    Args:
        query: Search query (title, author, or keywords)
        sources: Comma-separated source IDs to search (optional). Available: google_books, open_library, author_today, knigogo, libgen, flibusta, gutenberg
    """
    source_ids = [s.strip() for s in sources.split(",") if s.strip()] if sources else None
    results = _run_async(search_all(query, source_ids=source_ids))
    if not results:
        return "No results found."
    lines = [f"Found {len(results)} results:"]
    for r in results[:20]:
        src = f"[{r.source}]"
        year = f" ({r.year})" if r.year else ""
        lines.append(f"  • {r.title} — {r.author}{year} {src}")
    if len(results) > 20:
        lines.append(f"  ... and {len(results) - 20} more")
    return "\n".join(lines)


@mcp.tool()
def bl_list_series() -> str:
    """List all book series in your library with progress."""
    series = db.list_series()
    if not series:
        return "No series in your library yet."
    lines = ["📚 Series:"]
    for s in series:
        total = s["total"]
        finished = s["finished"]
        reading = s["reading"]
        downloaded = s["downloaded"]
        pct = int(finished / total * 100) if total else 0
        status_parts = []
        if finished:
            status_parts.append(f"✅{finished}")
        if reading:
            status_parts.append(f"📖{reading}")
        if downloaded:
            status_parts.append(f"💾{downloaded}")
        remaining = total - finished - reading - downloaded
        if remaining > 0:
            status_parts.append(f"📋{remaining}")
        lines.append(f"  • {s['series']} — {s['author']} [{'/'.join(status_parts)}] ({pct}% done)")
    return "\n".join(lines)


@mcp.tool()
def bl_series_books(series: str) -> str:
    """Show all books in a series with their status and order.
    
    Args:
        series: Series name (or part of it)
    """
    books = db.get_series_books(series)
    if not books:
        return f"No books found in series '{series}'."
    status_icons = {"finished": "✅", "reading": "📖", "downloaded": "💾", "want_to_read": "📋"}
    lines = [f"📚 {series}:"]
    for b in books:
        icon = status_icons.get(b["status"], "?")
        order = f"#{int(b['series_order'])} " if b["series_order"] else ""
        stars = f" {'⭐' * int(b['rating'])}" if b["rating"] else ""
        lines.append(f"  {order}{icon} {b['title']}{stars}")
    return "\n".join(lines)


@mcp.tool()
def bl_convert_book(input_path: str, output_format: str) -> str:
    """Convert a book file to another format.
    
    Args:
        input_path: Path to the source book file
        output_format: Target format — epub, fb2, txt, or pdf
    """
    supported = {"epub", "fb2", "txt", "pdf"}
    if output_format not in supported:
        return f"Supported formats: {', '.join(supported)}"
    
    try:
        output_path = convert_book_file(input_path, output_format)
        return f"Converted successfully: {output_path}"
    except Exception as e:
        return f"Conversion error: {e}"


@mcp.tool()
def bl_reading_stats() -> str:
    """Get your reading statistics: total books, finished this year, avg rating, top authors and genres."""
    stats = db.get_stats()
    lines = [
        "📊 Reading Stats:",
        f"  Total books: {stats['total']}",
        f"  Finished: {stats['finished']} | Reading: {stats['reading']} | Want to read: {stats['want_to_read']}",
        f"  Finished this year: {stats['this_year_finished']}",
        f"  Average rating: {stats['avg_rating']}/5",
    ]
    if stats["top_authors"]:
        lines.append("  Top authors: " + ", ".join(f"{a['author']} ({a['count']})" for a in stats["top_authors"]))
    if stats["top_genres"]:
        lines.append("  Top genres: " + ", ".join(f"{g['genre']} ({g['count']})" for g in stats["top_genres"]))
    return "\n".join(lines)


@mcp.tool()
def bl_add_quote(book_id: int, text: str, page: str = "") -> str:
    """Save a quote from a book.
    
    Args:
        book_id: Book ID from the library
        text: The quote text
        page: Page number or chapter reference (optional)
    """
    book = db.get_book(book_id)
    if not book:
        return f"Book {book_id} not found."
    quote = db.add_quote(book_id, text, page)
    page_info = f" (p.{page})" if page else ""
    return f"Quote saved from '{book['title']}'{page_info}:\n\"{text}\""


@mcp.tool()
def bl_list_quotes(book_id: int = 0) -> str:
    """List saved quotes. If book_id is provided, shows quotes from that book only.
    
    Args:
        book_id: Filter by book ID (0 = all quotes)
    """
    quotes = db.get_quotes(book_id)
    if not quotes:
        return "No quotes saved yet."
    lines = ["📝 Quotes:"]
    for q in quotes:
        page_info = f" (p.{q['page']})" if q['page'] else ""
        lines.append(f"  \"{q['text']}\"\n    — {q['title']}, {q['author']}{page_info}")
    return "\n".join(lines)


@mcp.tool()
def bl_suggest_next() -> str:
    """Suggest what to read next based on your reading history, ratings, and favorite genres/authors."""
    stats = db.get_stats()
    want_to_read = db.list_books(status="want_to_read")
    downloaded = db.list_books(status="downloaded")
    series_reviews = db.get_series_reviews()
    
    # Take latest review per series (deduplicate)
    latest_by_series = {}
    for r in series_reviews:
        s = r["series"].lower()
        if s not in latest_by_series:
            latest_by_series[s] = r
    
    liked_series = {s for s, r in latest_by_series.items() if r["rating"] >= 4}
    disliked_series = {s for s, r in latest_by_series.items() if r["rating"] <= 2}
    
    candidates = want_to_read + downloaded
    
    if candidates:
        top_authors = {a["author"].lower() for a in stats.get("top_authors", [])}
        top_genres = {g["genre"].lower() for g in stats.get("top_genres", [])}
        
        def score(book):
            s = 0
            if book["author"].lower() in top_authors:
                s += 3
            if book["genre"].lower() in top_genres:
                s += 2
            # Exact match for series
            book_series = (book.get("series") or "").lower()
            if book_series and book_series in liked_series:
                s += 4
            if book_series and book_series in disliked_series:
                s -= 5
            return s
        
        candidates.sort(key=score, reverse=True)
        lines = ["📖 Suggested next reads:"]
        if latest_by_series:
            lines.append(f"  (based on {len(latest_by_series)} series reviews)")
        for b in candidates[:5]:
            reason = []
            if b["author"].lower() in top_authors:
                reason.append("fav author")
            if b["genre"].lower() in top_genres:
                reason.append("fav genre")
            book_series = (b.get("series") or "").lower()
            if book_series and book_series in liked_series:
                reason.append("liked series")
            tag = f" ← {', '.join(reason)}" if reason else ""
            lines.append(f"  • {b['title']} — {b['author']}{tag}")
        return "\n".join(lines)
    
    # No candidates — suggest based on top authors via API
    if stats["top_authors"]:
        from mcp_book_lover.recommendations import get_recommendations_for_book
        author = stats["top_authors"][0]["author"]
        recs = get_recommendations_for_book(author=author)
        if recs:
            lines = [f"📖 Suggestions based on your favorite author ({author}):"]
            for r in recs[:5]:
                lines.append(f"  • {r['title']} — {r['author']}")
            return "\n".join(lines)
    
    return "Add some books and rate them to get personalized suggestions!"


@mcp.tool()
def bl_import_list(text: str) -> str:
    """Import multiple books from a text list. Each line: 'Title — Author' or 'Title - Author'.
    
    Args:
        text: Multi-line text with books, one per line (format: Title — Author)
    """
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    books = []
    for line in lines:
        # Try splitting by — or -
        for sep in ["—", "–", " - "]:
            if sep in line:
                parts = line.split(sep, 1)
                books.append({"title": parts[0].strip(), "author": parts[1].strip()})
                break
        else:
            books.append({"title": line, "author": "Unknown"})
    
    if not books:
        return "No books found in the text."
    
    count = db.add_books_bulk(books)
    return f"Imported {count} books into your library."


@mcp.tool()
def bl_export_library(format: str = "json") -> str:
    """Export your entire library.
    
    Args:
        format: Export format — json, csv, or markdown
    """
    books = db.list_books()
    if not books:
        return "Library is empty."
    
    if format == "json":
        return json.dumps(books, ensure_ascii=False, indent=2)
    
    if format == "csv":
        import csv, io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["title", "author", "genre", "status", "rating", "date_added", "date_read"])
        for b in books:
            writer.writerow([b["title"], b["author"], b["genre"], b["status"], b["rating"], b["date_added"], b.get("date_read", "")])
        return output.getvalue()
    
    if format == "markdown":
        lines = ["# My Library", ""]
        for status in ["reading", "finished", "want_to_read"]:
            filtered = [b for b in books if b["status"] == status]
            if not filtered:
                continue
            lines.append(f"## {status.replace('_', ' ').title()} ({len(filtered)})")
            for b in filtered:
                stars = f" {'⭐' * int(b['rating'])}" if b['rating'] else ""
                lines.append(f"- **{b['title']}** — {b['author']}{stars}")
            lines.append("")
        return "\n".join(lines)
    
    return "Supported formats: json, csv, markdown"


@mcp.tool()
def bl_set_goal(year: int, target: int) -> str:
    """Set a reading challenge goal for a year.
    
    Args:
        year: Year (e.g. 2026)
        target: Number of books to read
    """
    db.set_goal(year, target)
    return f"🎯 Goal set: read {target} books in {year}!"


@mcp.tool()
def bl_goal_progress(year: int = 0) -> str:
    """Check progress on your reading challenge.
    
    Args:
        year: Year to check (default: current year)
    """
    from datetime import datetime as dt
    if not year:
        year = dt.now().year
    goal = db.get_goal(year)
    if not goal:
        return f"No goal set for {year}. Use bl_set_goal to set one."
    finished = db.get_finished_count(year)
    target = goal["target"]
    pct = int(finished / target * 100) if target else 0
    bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
    remaining = target - finished
    return f"🎯 Reading Challenge {year}: {finished}/{target} books ({pct}%)\n[{bar}]\n{'📚 ' + str(remaining) + ' more to go!' if remaining > 0 else '🎉 Goal achieved!'}"


@mcp.tool()
def bl_find_download(query: str) -> str:
    """Find download links for a book across sources that offer direct downloads (LibGen, Flibusta).
    
    Args:
        query: Book title or 'title author' to search
    """
    results = _run_async(search_all(query, source_ids=["libgen", "flibusta"]))
    if not results:
        return "No download sources found for this query."
    lines = ["🔗 Download sources found:"]
    for r in results[:10]:
        lines.append(f"  • {r.title} — {r.author} [{r.source}]")
    lines.append("\nNote: Use the source websites to download. LibGen: libgen.is | Flibusta: flibusta.site")
    return "\n".join(lines)


@mcp.tool()
def bl_download_book(query: str, author: str = "", save_dir: str = "") -> str:
    """Download a book from searchfloor.org. Searches by title (and optionally author), then downloads the zip file.
    
    Args:
        query: Book title to search for
        author: Author name (if provided, searches author's page for exact match)
        save_dir: Directory to save the file (default: ~/Books)
    """
    import os
    import httpx

    if not save_dir:
        save_dir = os.path.expanduser("~/Books")
    os.makedirs(save_dir, exist_ok=True)

    # Find the book
    if author:
        results = _run_async(search_searchfloor_by_author(author))
    else:
        results = _run_async(search_all(query, source_ids=["searchfloor"]))

    if not results:
        return f"❌ No books found on Searchfloor for '{query}'"

    # Find best match
    query_lower = query.lower()
    match = None
    for r in results:
        if query_lower in r.title.lower() or r.title.lower() in query_lower:
            match = r
            break
    if not match:
        match = results[0]
        titles = "\n".join(f"  • {r.title} — {r.url}" for r in results[:10])
        return f"❌ No exact match for '{query}'. Found:\n{titles}"

    # Download
    download_url = match.url  # https://searchfloor.org/book/{id}
    if not download_url:
        return f"❌ No download URL for '{match.title}'"

    try:
        with httpx.Client(follow_redirects=True, timeout=60.0) as client:
            r = client.get(download_url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            })
            if r.status_code != 200:
                return f"❌ Download failed: HTTP {r.status_code}"
            if len(r.content) == 0:
                return f"❌ Download returned empty file (may require auth). URL: {download_url}"

            # Determine filename
            cd = r.headers.get("content-disposition", "")
            import re as _re
            from urllib.parse import unquote
            # RFC 5987: filename*=UTF-8''encoded_name
            fname_m = _re.search(r"filename\*=UTF-8''(.+?)(?:;|$)", cd, _re.IGNORECASE)
            if fname_m:
                filename = unquote(fname_m.group(1).strip())
            else:
                fname_m = _re.search(r'filename="?([^";\n]+)"?', cd)
                if fname_m:
                    filename = fname_m.group(1).strip()
                else:
                    ext = ".zip" if "zip" in r.headers.get("content-type", "") else ".fb2"
                    safe_title = _re.sub(r'[^\w\s\-.]', '', match.title)[:80]
                    filename = f"{safe_title}{ext}"

            filepath = os.path.join(save_dir, filename)
            with open(filepath, "wb") as f:
                f.write(r.content)

            size_kb = len(r.content) // 1024
            return f"✅ Downloaded: {match.title}\n📁 {filepath} ({size_kb} KB)"
    except Exception as e:
        return f"❌ Download error: {e}"


@mcp.tool()
def bl_review_series(series: str, text: str, rating: float) -> str:
    """Write a review for a book series.
    
    Args:
        series: Series name (e.g. "Антидемон", "Дисгардиум")
        text: Your review text
        rating: Rating from 1 to 5
    """
    from .db import add_series_review
    review = add_series_review(series, text, rating)
    return f"✅ Series review saved for '{series}' ({rating}/5)"


@mcp.tool()
def bl_get_series_reviews(series: str = "") -> str:
    """Get reviews for book series.
    
    Args:
        series: Filter by series name (optional, shows all if empty)
    """
    from .db import get_series_reviews
    reviews = get_series_reviews(series)
    if not reviews:
        return "No series reviews found."
    lines = ["📚 Series Reviews:"]
    for r in reviews:
        lines.append(f"  • {r['series']} ({r['rating']}/5) — {r['text'][:100]}")
    return "\n".join(lines)


@mcp.tool()
def bl_save_recommendation(title: str, author: str = "", reason: str = "", source: str = "") -> str:
    """Save a book recommendation for future reading.
    
    Args:
        title: Book title
        author: Author name
        reason: Why this book was recommended (e.g. "similar to Антидемон", "recommended by AI")
        source: Where the recommendation came from (e.g. "based on Дисгардиум review")
    """
    from .db import save_recommendation
    rec = save_recommendation(title, author, reason, source)
    return f"✅ Saved recommendation: '{title}' by {author or '?'} — {reason}"


@mcp.tool()
def bl_list_recommendations() -> str:
    """List all saved book recommendations for future reading."""
    from .db import list_recommendations
    recs = list_recommendations()
    if not recs:
        return "No saved recommendations yet."
    lines = [f"📋 Saved Recommendations ({len(recs)}):"]
    for r in recs:
        author = f" — {r['author']}" if r['author'] else ""
        reason = f" ({r['reason']})" if r['reason'] else ""
        lines.append(f"  [{r['id']}] {r['title']}{author}{reason}")
    return "\n".join(lines)


@mcp.tool()
def bl_delete_recommendation(rec_id: int) -> str:
    """Remove a recommendation from the list (e.g. after adding to library).
    
    Args:
        rec_id: Recommendation ID from bl_list_recommendations
    """
    from .db import delete_recommendation
    delete_recommendation(rec_id)
    return f"✅ Recommendation {rec_id} removed."


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
