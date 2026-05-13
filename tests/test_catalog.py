"""Catalog module sanity tests — no network, no API key required."""

from app import catalog


def test_search_by_author_returns_books():
    results = catalog.search("Borges")
    assert results, "expected at least one Borges title"
    assert all("Borges" in b.author for b in results)


def test_search_case_insensitive():
    assert catalog.search("borges") == catalog.search("BORGES")


def test_search_empty_query_returns_empty():
    assert catalog.search("") == []


def test_search_respects_limit():
    assert len(catalog.search("a", limit=3)) <= 3


def test_get_unknown_id_returns_none():
    assert catalog.get("does-not-exist") is None


def test_similar_excludes_base_book():
    base = next(iter(catalog.all_books()))
    related = catalog.similar(base.id)
    assert all(b.id != base.id for b in related)


def test_similar_shares_genre():
    base = next(iter(catalog.all_books()))
    related = catalog.similar(base.id)
    assert all(b.genre == base.genre for b in related)


def test_summary_mentions_total_count():
    total = len(catalog.all_books())
    assert str(total) in catalog.summary()
