# MCP Book Lover

An MCP server for managing your personal book library. Track what you read, write reviews, get recommendations, search across multiple sources, and convert between formats — all from your AI assistant.

## Features

- **Book tracking** — manage your library with statuses: want to read → downloaded → reading → finished
- **Series support** — track progress through book series with ordering and series-level reviews
- **Library search** — find books in your library by title, author, series, or description
- **Reviews & quotes** — rate books and series (1–5), write reviews, save favourite quotes
- **Recommendations** — personalized suggestions based on your ratings and series reviews; save recommendations for later
- **Multi-source search** — search online across 8 sources (Google Books, Open Library, Author.Today, Knigogo, Searchfloor, LibGen, Flibusta, Project Gutenberg)
- **Download** — download books directly from searchfloor.org to `~/Books`
- **Format conversion** — convert between epub, fb2, txt, pdf with full preservation of chapters, bold/italic, inline images, cover and metadata
- **Reading stats** — yearly progress, top authors/genres, average rating
- **Reading challenge** — set yearly goals and track progress
- **Import/Export** — bulk import from text, export to JSON/CSV/Markdown

## Installation

No installation needed if you use `uvx` — it fetches the package automatically.

Or install manually (requires Python 3.11+):

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install mcp-book-lover
```

## Connecting to MCP clients

### Claude Code

```bash
claude mcp add book-lover uvx mcp-book-lover
```

To make it available in all projects, add to `~/.claude/mcp.json`:

```json
{
  "mcpServers": {
    "book-lover": {
      "command": "uvx",
      "args": ["mcp-book-lover"]
    }
  }
}
```

### Claude Desktop / Kiro / Cursor

Add to the MCP config file of your client:

```json
{
  "mcpServers": {
    "book-lover": {
      "command": "uvx",
      "args": ["mcp-book-lover"]
    }
  }
}
```

## Development

```bash
git clone https://github.com/MIt9/mcp-book-lover
cd mcp-book-lover
uv sync
```

Test interactively with the MCP inspector:

```bash
mcp dev src/mcp_book_lover/server.py
```

## Tools

| Tool | Description |
|------|-------------|
| `bl_add_book` | Add a book to your library (with series/order support) |
| `bl_list_books` | List books with filters (status, author, genre) |
| `bl_find_in_library` | Search YOUR library by title, author, series, description |
| `bl_update_book_status` | Change reading status |
| `bl_delete_book` | Delete a book with all its reviews and quotes |
| `bl_list_series` | List all series with progress |
| `bl_series_books` | Show books in a series with order and status |
| `bl_review_book` | Write a review + rating (1–5) |
| `bl_get_reviews` | View reviews for a book |
| `bl_review_series` | Write a review for a book series |
| `bl_get_series_reviews` | View series reviews |
| `bl_save_recommendation` | Save a recommendation for future reading |
| `bl_list_recommendations` | List saved recommendations |
| `bl_delete_recommendation` | Remove a recommendation from the list |
| `bl_add_quote` | Save a quote from a book |
| `bl_list_quotes` | View saved quotes |
| `bl_get_recommendations` | Get recommendations by author/genre via Open Library |
| `bl_search_books` | Search online across 8 sources |
| `bl_suggest_next` | What to read next (scored by ratings, series reviews, fav authors/genres) |
| `bl_find_download` | Find download links (LibGen, Flibusta) |
| `bl_download_book` | Download a book from searchfloor.org to ~/Books |
| `bl_convert_book` | Convert book file — preserves chapters, formatting, images |
| `bl_reading_stats` | Reading statistics |
| `bl_set_goal` | Set a yearly reading challenge |
| `bl_goal_progress` | Check reading challenge progress |
| `bl_import_list` | Import books from text list |
| `bl_export_library` | Export library (json/csv/markdown) |

## Book Statuses

| Status | Meaning |
|--------|---------|
| `want_to_read` | On the wishlist, don't have the file yet |
| `downloaded` | File ready, queued for reading |
| `reading` | Currently reading/listening |
| `finished` | Done |

## Format Conversion

All conversions preserve chapter structure, metadata (title, author, language), cover image, bold/italic text, and inline images.

| From \ To | epub | fb2 | pdf | txt |
|-----------|------|-----|-----|-----|
| **fb2**   | ✅   | —   | ✅  | ✅  |
| **epub**  | —    | ✅  | ✅  | ✅  |
| **txt**   | ✅   | ✅  | ✅  | —   |
| **pdf**   | ✅   | ✅  | —   | ✅  |

PDF output uses a system Unicode font (Arial on macOS, DejaVu on Linux) for Cyrillic support.

## Search Sources

Sources are auto-selected based on query language (Cyrillic → uk/ru sources, Latin → en sources):

| Source | Languages | Type |
|--------|-----------|------|
| Google Books | en, uk, ru | API |
| Open Library | en, uk, ru | API |
| Author.Today | uk, ru | Scraping |
| Knigogo | uk, ru | Scraping |
| Searchfloor | uk, ru | Scraping + download |
| LibGen | en, uk, ru | Scraping |
| Flibusta | ru | Scraping |
| Project Gutenberg | en | Scraping |

## Storage

SQLite database at `~/.mcp-book-lover/books.db`. Downloaded books go to `~/Books` by default.

## Requirements

- Python ≥ 3.10
- No external services or API keys required
- System Unicode font (Arial/DejaVu) for PDF output with Cyrillic

## License

MIT
