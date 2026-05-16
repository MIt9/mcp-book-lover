# MCP Book Lover 📚

An MCP server for managing your personal book library. Track what you read, write reviews, get recommendations, search across multiple sources, and convert between formats — all from your AI assistant.

## Features

- **Book tracking** — manage your library with statuses: want to read → downloaded → reading → finished
- **Series support** — track progress through book series with ordering
- **Library search** — find books in your library by title, author, series, or description
- **Reviews & quotes** — rate books and series, write reviews, save favorite quotes
- **Recommendations** — get personalized suggestions based on series reviews, save recommendations for later
- **Multi-source search** — search online across 7 sources (Google Books, Open Library, Author.Today, Knigogo, LibGen, Flibusta, Project Gutenberg)
- **Format conversion** — convert between epub, fb2, and txt (pdf read-only)
- **Reading stats** — yearly progress, top authors/genres, average rating
- **Reading challenge** — set yearly goals and track progress
- **Import/Export** — bulk import from text, export to JSON/CSV/Markdown

## Installation

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Usage

```bash
mcp-book-lover
```

## MCP Client Configuration

Add to your MCP client config (Claude Desktop, Kiro, etc.):

```json
{
  "mcpServers": {
    "book-lover": {
      "command": "/path/to/mcp-book-lover/.venv/bin/python3.11",
      "args": ["-m", "mcp_book_lover.server"]
    }
  }
}
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
| `bl_review_book` | Write a review + rating (1-5) |
| `bl_get_reviews` | View reviews for a book |
| `bl_review_series` | Write a review for a book series |
| `bl_get_series_reviews` | View series reviews |
| `bl_save_recommendation` | Save a recommendation for future reading |
| `bl_list_recommendations` | List saved recommendations |
| `bl_delete_recommendation` | Remove a recommendation from the list |
| `bl_add_quote` | Save a quote from a book |
| `bl_list_quotes` | View saved quotes |
| `bl_get_recommendations` | Get recommendations by author/genre |
| `bl_search_books` | Search online across 7 sources (Google Books, Open Library, etc.) |
| `bl_suggest_next` | What to read next (personalized) |
| `bl_find_download` | Find download sources for a book |
| `bl_convert_book` | Convert book file (epub, fb2, txt) |
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

## Search Sources

Sources are auto-selected based on query language (Cyrillic → uk/ru sources, Latin → en sources):

| Source | Languages | Type |
|--------|-----------|------|
| Google Books | en, uk, ru | API |
| Open Library | en, uk, ru | API |
| Author.Today | uk, ru | Scraping |
| Knigogo | uk, ru | Scraping |
| LibGen | en, uk, ru | Scraping |
| Flibusta | ru | Scraping |
| Project Gutenberg | en | Scraping |

## Storage

SQLite database stored at `~/.mcp-book-lover/books.db`

## Requirements

- Python ≥ 3.10
- No external services or API keys required

## License

MIT
