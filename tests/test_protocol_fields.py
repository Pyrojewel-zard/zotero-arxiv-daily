"""Tests for Paper doi and arxiv_id fields."""

from zotero_arxiv_daily.protocol import Paper


def test_paper_has_doi_field():
    p = Paper(title="Test", abstract="test abstract", doi="10.1109/TMTT.2023.123")
    assert p.doi == "10.1109/TMTT.2023.123"


def test_paper_has_arxiv_id_field():
    p = Paper(title="Test", abstract="test abstract", arxiv_id="2401.12345")
    assert p.arxiv_id == "2401.12345"


def test_paper_doi_and_arxiv_id_default_none():
    p = Paper(title="Test", abstract="test abstract")
    assert p.doi is None
    assert p.arxiv_id is None