import pytest

from mcp_book_lover.search import SearchResult, extract_series, group_by_series


def _res(title: str, author: str = "Автор") -> SearchResult:
    return SearchResult(title=title, author=author, source="t", url="http://x", description="")


@pytest.mark.parametrize("title,expected", [
    ("Брутфорс 1", ("Брутфорс", 1)),
    ("Брутфорс1", ("Брутфорс", 1)),
    ("Брутфорс#6", ("Брутфорс", 6)),
    ("Наследие #1: Статус D", ("Наследие", 1)),
    ("Серия №2: Название", ("Серия", 2)),
    ("Сайберия. Книга 1: Байстрюк", ("Сайберия", 1)),
    ("Книга 2. Название", ("Название", 2)),
    ("Том 3 Название", ("Название", 3)),
    ("Название. Том 4", ("Название", 4)),
    ("Одиночная книга", ("Одиночная книга", None)),
])
def test_extract_series(title, expected):
    assert extract_series(title) == expected


def test_group_by_series_groups_numbered_parts():
    results = [
        _res("Наследие #1: Статус D"),
        _res("Наследие #2: Статус С"),
        _res("Брутфорс 1"),
    ]
    groups = group_by_series(results)
    assert [(g["series"], [p["num"] for p in g["parts"]]) for g in groups] == [
        ("Брутфорс", [1]),
        ("Наследие", [1, 2]),
    ]


def test_group_by_series_drops_standalone_single():
    results = [_res("Одиночная книга")]
    assert group_by_series(results) == []