"""SQLite database layer for book tracking."""

import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path.home() / ".mcp-book-lover" / "books.db"


_initialized = False


def get_db() -> sqlite3.Connection:
    global _initialized
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    if not _initialized:
        _init_tables(conn)
        _initialized = True
    return conn


def _init_tables(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            genre TEXT DEFAULT '',
            language TEXT DEFAULT '',
            status TEXT DEFAULT 'want_to_read',
            rating REAL DEFAULT 0,
            date_added TEXT NOT NULL,
            date_read TEXT,
            file_path TEXT DEFAULT '',
            cover_url TEXT DEFAULT '',
            description TEXT DEFAULT '',
            series TEXT DEFAULT '',
            series_order REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            rating REAL NOT NULL,
            date_created TEXT NOT NULL,
            FOREIGN KEY (book_id) REFERENCES books(id)
        );
        CREATE TABLE IF NOT EXISTS quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            page TEXT DEFAULT '',
            date_added TEXT NOT NULL,
            FOREIGN KEY (book_id) REFERENCES books(id)
        );
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            year INTEGER NOT NULL UNIQUE,
            target INTEGER NOT NULL,
            date_created TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            tag TEXT NOT NULL,
            FOREIGN KEY (book_id) REFERENCES books(id),
            UNIQUE(book_id, tag)
        );
        CREATE TABLE IF NOT EXISTS series_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            series TEXT NOT NULL,
            text TEXT NOT NULL,
            rating REAL NOT NULL,
            date_created TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT DEFAULT '',
            reason TEXT DEFAULT '',
            source TEXT DEFAULT '',
            date_added TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_books_series ON books(series);
    """)
    # Migrate: add series columns if missing
    cols = [r[1] for r in conn.execute("PRAGMA table_info(books)").fetchall()]
    if "series" not in cols:
        conn.execute("ALTER TABLE books ADD COLUMN series TEXT DEFAULT ''")
    if "series_order" not in cols:
        conn.execute("ALTER TABLE books ADD COLUMN series_order REAL DEFAULT 0")
    conn.commit()


def add_book(title: str, author: str, genre: str = "", language: str = "",
             status: str = "want_to_read", file_path: str = "",
             description: str = "", series: str = "", series_order: float = 0) -> dict:
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO books (title, author, genre, language, status, file_path, description, series, series_order, date_added) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (title, author, genre, language, status, file_path, description,
             series, series_order, datetime.now().isoformat())
        )
        conn.commit()
        book = conn.execute("SELECT * FROM books WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(book)
    finally:
        conn.close()


def list_books(status=None, author=None, genre=None) -> list:
    conn = get_db()
    try:
        query = "SELECT * FROM books WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if author:
            query += " AND author LIKE ?"
            params.append(f"%{author}%")
        if genre:
            query += " AND genre LIKE ?"
            params.append(f"%{genre}%")
        query += " ORDER BY date_added DESC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_book(book_id: int):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_book(book_id: int, **fields):
    conn = get_db()
    try:
        allowed = {"title", "author", "genre", "language", "status", "rating",
                   "date_read", "file_path", "description", "series", "series_order"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return get_book(book_id)
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(f"UPDATE books SET {set_clause} WHERE id = ?",
                     [*updates.values(), book_id])
        conn.commit()
        book = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
        return dict(book) if book else None
    finally:
        conn.close()


def add_review(book_id: int, text: str, rating: float) -> dict:
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO reviews (book_id, text, rating, date_created) VALUES (?, ?, ?, ?)",
            (book_id, text, rating, datetime.now().isoformat())
        )
        conn.execute("UPDATE books SET rating = ? WHERE id = ?", (rating, book_id))
        conn.commit()
        review = conn.execute("SELECT * FROM reviews WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(review)
    finally:
        conn.close()


def get_reviews(book_id: int) -> list[dict]:
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM reviews WHERE book_id = ? ORDER BY date_created DESC",
            (book_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_authors() -> list[str]:
    conn = get_db()
    try:
        rows = conn.execute("SELECT DISTINCT author FROM books ORDER BY author").fetchall()
        return [r["author"] for r in rows]
    finally:
        conn.close()


def list_series() -> list:
    """Get all series with book counts and progress."""
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT series, author, COUNT(*) as total,
                   SUM(CASE WHEN status = 'finished' THEN 1 ELSE 0 END) as finished,
                   SUM(CASE WHEN status = 'reading' THEN 1 ELSE 0 END) as reading,
                   SUM(CASE WHEN status = 'downloaded' THEN 1 ELSE 0 END) as downloaded
            FROM books WHERE series != '' GROUP BY series ORDER BY series
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_series_books(series: str) -> list:
    """Get all books in a series, ordered by series_order."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM books WHERE series LIKE ? ORDER BY series_order, date_added",
            (f"%{series}%",)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# --- Quotes ---

def add_quote(book_id: int, text: str, page: str = "") -> dict:
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO quotes (book_id, text, page, date_added) VALUES (?, ?, ?, ?)",
            (book_id, text, page, datetime.now().isoformat())
        )
        conn.commit()
        row = conn.execute("SELECT * FROM quotes WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def get_quotes(book_id: int = 0) -> list:
    conn = get_db()
    try:
        if book_id:
            rows = conn.execute("SELECT q.*, b.title, b.author FROM quotes q JOIN books b ON q.book_id = b.id WHERE q.book_id = ? ORDER BY q.date_added DESC", (book_id,)).fetchall()
        else:
            rows = conn.execute("SELECT q.*, b.title, b.author FROM quotes q JOIN books b ON q.book_id = b.id ORDER BY q.date_added DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# --- Goals ---

def set_goal(year: int, target: int) -> dict:
    conn = get_db()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO goals (year, target, date_created) VALUES (?, ?, ?)",
            (year, target, datetime.now().isoformat())
        )
        conn.commit()
        row = conn.execute("SELECT * FROM goals WHERE year = ?", (year,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def get_goal(year: int):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM goals WHERE year = ?", (year,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_finished_count(year: int) -> int:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM books WHERE status = 'finished' AND date_read LIKE ?",
            (f"{year}%",)
        ).fetchone()
        return row["cnt"] if row else 0
    finally:
        conn.close()


# --- Stats ---

def get_stats() -> dict:
    conn = get_db()
    try:
        total = conn.execute("SELECT COUNT(*) as cnt FROM books").fetchone()["cnt"]
        finished = conn.execute("SELECT COUNT(*) as cnt FROM books WHERE status = 'finished'").fetchone()["cnt"]
        reading = conn.execute("SELECT COUNT(*) as cnt FROM books WHERE status = 'reading'").fetchone()["cnt"]
        want = conn.execute("SELECT COUNT(*) as cnt FROM books WHERE status = 'want_to_read'").fetchone()["cnt"]
        avg_rating = conn.execute("SELECT AVG(rating) as avg FROM books WHERE rating > 0").fetchone()["avg"] or 0
        top_authors = conn.execute(
            "SELECT author, COUNT(*) as cnt FROM books GROUP BY author ORDER BY cnt DESC LIMIT 5"
        ).fetchall()
        top_genres = conn.execute(
            "SELECT genre, COUNT(*) as cnt FROM books WHERE genre != '' GROUP BY genre ORDER BY cnt DESC LIMIT 5"
        ).fetchall()
        year = datetime.now().year
        this_year = conn.execute(
            "SELECT COUNT(*) as cnt FROM books WHERE status = 'finished' AND date_read LIKE ?",
            (f"{year}%",)
        ).fetchone()["cnt"]
        return {
            "total": total, "finished": finished, "reading": reading,
            "want_to_read": want, "avg_rating": round(avg_rating, 1),
            "this_year_finished": this_year,
            "top_authors": [{"author": r["author"], "count": r["cnt"]} for r in top_authors],
            "top_genres": [{"genre": r["genre"], "count": r["cnt"]} for r in top_genres],
        }
    finally:
        conn.close()


# --- Bulk import ---

def add_series_review(series: str, text: str, rating: float) -> dict:
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO series_reviews (series, text, rating, date_created) VALUES (?, ?, ?, ?)",
            (series, text, rating, datetime.now().isoformat())
        )
        conn.commit()
        row = conn.execute("SELECT * FROM series_reviews WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def get_series_reviews(series: str = "") -> list:
    conn = get_db()
    try:
        if series:
            rows = conn.execute(
                "SELECT * FROM series_reviews WHERE series = ? ORDER BY date_created DESC",
                (series,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM series_reviews ORDER BY date_created DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def save_recommendation(title: str, author: str = "", reason: str = "", source: str = "") -> dict:
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO recommendations (title, author, reason, source, date_added) VALUES (?, ?, ?, ?, ?)",
            (title, author, reason, source, datetime.now().isoformat())
        )
        conn.commit()
        row = conn.execute("SELECT * FROM recommendations WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def list_recommendations() -> list:
    conn = get_db()
    try:
        rows = conn.execute("SELECT * FROM recommendations ORDER BY date_added DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_recommendation(rec_id: int):
    conn = get_db()
    try:
        conn.execute("DELETE FROM recommendations WHERE id = ?", (rec_id,))
        conn.commit()
    finally:
        conn.close()


def delete_book(book_id: int) -> bool:
    """Delete a book and all related reviews, quotes, tags."""
    conn = get_db()
    try:
        conn.execute("DELETE FROM reviews WHERE book_id = ?", (book_id,))
        conn.execute("DELETE FROM quotes WHERE book_id = ?", (book_id,))
        conn.execute("DELETE FROM tags WHERE book_id = ?", (book_id,))
        conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def search_library(query: str, status: str = "", limit: int = 50) -> list:
    """Full-text search across own library (title, author, series, description, genre)."""
    conn = get_db()
    try:
        q = f"%{query}%"
        sql = """SELECT * FROM books WHERE 
            (title LIKE ? OR author LIKE ? OR series LIKE ? OR description LIKE ? OR genre LIKE ?)"""
        params = [q, q, q, q, q]
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY CASE WHEN title LIKE ? THEN 1 WHEN series LIKE ? THEN 2 WHEN author LIKE ? THEN 3 ELSE 4 END LIMIT ?"
        params.extend([q, q, q, limit])
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_books_bulk(books_data: list) -> int:
    conn = get_db()
    try:
        count = 0
        for b in books_data:
            conn.execute(
                "INSERT INTO books (title, author, genre, language, status, description, date_added) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (b.get("title", ""), b.get("author", ""), b.get("genre", ""),
                 b.get("language", ""), b.get("status", "want_to_read"),
                 b.get("description", ""), datetime.now().isoformat())
            )
            count += 1
        conn.commit()
        return count
    finally:
        conn.close()
