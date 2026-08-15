
import pytest

from mcp_book_lover import db


@pytest.fixture
def fresh_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "_initialized", False)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "books.db")
    yield


def test_add_book_finished_sets_date_read(fresh_db):
    book = db.add_book("Тест", "Автор", status="finished")
    assert book["date_read"] is not None
    assert book["status"] == "finished"


def test_add_book_downloaded_leaves_date_read_null(fresh_db):
    book = db.add_book("Тест", "Автор", status="downloaded")
    assert book["date_read"] is None


def test_update_to_finished_sets_date_read(fresh_db):
    book = db.add_book("Тест", "Автор", status="downloaded")
    updated = db.update_book(book["id"], status="finished")
    assert updated["date_read"] is not None


def test_series_grouped_roundtrip(fresh_db):
    for i in range(1, 6):
        db.add_book(f"Наследие {i}", "В. Василенко", series="Наследие", series_order=i)
    series = db.list_series()
    ns = [s for s in series if s["series"] == "Наследие"]
    assert len(ns) == 1
    assert ns[0]["total"] == 5