import pytest

from mcp_book_lover.search import SearchResult
from mcp_book_lover.server import _score_match


def _res(title: str, author: str = "Иван Катиш") -> SearchResult:
    return SearchResult(title=title, author=author, source="sf", url="http://x", description="")


RESULTS = [
    _res("Наследие #1: Статус D"),
    _res("Наследие #2: Статус С"),
    _res("Наследие #3: Статус B"),
    _res("Наследие #4: Статус А"),
    _res("Наследие #5: Статус S"),
    _res("Брутфорс 1"),
]


@pytest.mark.parametrize("query,expected", [
    ("Наследие Статус D", "Наследие #1: Статус D"),
    ("Статус А", "Наследие #4: Статус А"),
    ("Статус S", "Наследие #5: Статус S"),
    ("Статус B", "Наследие #3: Статус B"),
    ("Статус С", "Наследие #2: Статус С"),
    ("Брутфорс", "Брутфорс 1"),
])
def test_score_match_picks_best_result(query, expected):
    ranked = sorted(RESULTS, key=lambda r: _score_match(r, query), reverse=True)
    assert ranked[0].title == expected


def test_score_match_zero_for_unrelated():
    assert _score_match(_res("Домино 1"), "Привилегия местных жителей") == 0