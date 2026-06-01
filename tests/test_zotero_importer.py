"""Tests for ZoteroImporter."""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
import numpy as np

from zotero_arxiv_daily.zotero_importer import ZoteroImporter
from zotero_arxiv_daily.protocol import Paper, CorpusPaper
from tests.canned_responses import make_sample_paper


def _make_paper(**kwargs):
    defaults = dict(
        source="arxiv",
        title="Test Paper",
        authors=["Author A"],
        abstract="Test abstract",
        url="https://arxiv.org/abs/2401.12345",
    )
    defaults.update(kwargs)
    return Paper(**defaults)


def _make_corpus(**kwargs):
    defaults = dict(
        title="Corpus Paper",
        abstract="Corpus abstract",
        paths=["RF-Circuit"],
        added_date=datetime(2024, 1, 1),
    )
    defaults.update(kwargs)
    return CorpusPaper(**defaults)


@pytest.fixture
def importer():
    collection_map = {
        "RF-Circuit": "KEY_RF",
        "Passive-Device": "KEY_PD",
    }
    with patch("zotero_arxiv_daily.zotero_importer.Zotero") as mock_zotero_cls:
        mock_zot = MagicMock()
        mock_zotero_cls.return_value = mock_zot
        imp = ZoteroImporter(
            zotero_id="12345",
            zotero_key="testkey",
            collection_map=collection_map,
        )
        yield imp


def test_find_best_collection_highest_sim(importer):
    paper = _make_paper(title="RF Paper", arxiv_id="2401.00001")
    corpus = [
        _make_corpus(title="Corpus RF 1", abstract="RF", paths=["RF-Circuit"]),
        _make_corpus(title="Corpus RF 2", abstract="RF", paths=["RF-Circuit"]),
        _make_corpus(title="Corpus PD 1", abstract="PD", paths=["Passive-Device"]),
    ]
    sim_matrix = np.array([[0.9, 0.85, 0.3]])

    result_key, result_name = importer.find_best_collection(paper, corpus, sim_matrix, paper_idx=0)
    assert result_name == "RF-Circuit"
    assert result_key == "KEY_RF"


def test_find_best_collection_no_match_returns_none(importer):
    paper = _make_paper(title="Unknown Paper", arxiv_id="2401.00002")
    corpus = [
        _make_corpus(title="Corpus 1", abstract="test", paths=["SomeOtherCollection"]),
    ]
    sim_matrix = np.array([[0.8]])

    result = importer.find_best_collection(paper, corpus, sim_matrix, paper_idx=0)
    assert result is None


def test_is_duplicate_by_doi(importer):
    paper = _make_paper(doi="10.1109/TMTT.2023.123")
    importer.zot.items.return_value = [{"data": {"DOI": "10.1109/TMTT.2023.123"}}]
    assert importer.is_duplicate(paper) is True


def test_is_duplicate_by_arxiv_id(importer):
    paper = _make_paper(arxiv_id="2401.12345")
    importer.zot.items.return_value = [{"data": {"extra": "arXiv: 2401.12345"}}]
    assert importer.is_duplicate(paper) is True


def test_is_not_duplicate(importer):
    paper = _make_paper(arxiv_id="2401.99999")
    importer.zot.items.return_value = []
    assert importer.is_duplicate(paper) is False


def test_import_paper_with_doi(importer):
    paper = _make_paper(
        title="Test Paper",
        doi="10.1109/TMTT.2023.123",
        arxiv_id="2401.12345",
        url="https://arxiv.org/abs/2401.12345",
    )
    importer.zot.items.return_value = []
    importer.zot.create_items.return_value = {
        "successful": {"0": {"key": "NEWKEY1"}},
        "failed": {},
    }
    result = importer.import_paper(paper, "KEY_RF")
    assert result["status"] == "ok"
    assert result["collection"] == "RF-Circuit"


def test_import_paper_with_arxiv_id_only(importer):
    paper = _make_paper(
        title="ArXiv Paper",
        arxiv_id="2401.12345",
        url="https://arxiv.org/abs/2401.12345",
    )
    importer.zot.items.return_value = []
    importer.zot.create_items.return_value = {
        "successful": {"0": {"key": "NEWKEY2"}},
        "failed": {},
    }
    result = importer.import_paper(paper, "KEY_RF")
    assert result["status"] == "ok"
    call_args = importer.zot.create_items.call_args[0][0]
    assert "arXiv: 2401.12345" in call_args[0].get("extra", "")


def test_import_paper_duplicate_skipped(importer):
    paper = _make_paper(
        title="Dup Paper",
        arxiv_id="2401.12345",
    )
    importer.zot.items.return_value = [{"data": {"extra": "arXiv: 2401.12345"}}]
    result = importer.import_paper(paper, "KEY_RF")
    assert result["status"] == "duplicate"


def test_import_paper_api_failure(importer):
    paper = _make_paper(
        title="Fail Paper",
        arxiv_id="2401.12345",
        url="https://arxiv.org/abs/2401.12345",
    )
    importer.zot.items.return_value = []
    importer.zot.create_items.return_value = {
        "successful": {},
        "failed": {"0": {"code": 500, "message": "Server error"}},
    }
    result = importer.import_paper(paper, "KEY_RF")
    assert result["status"] == "failed"


def test_import_papers_batch(importer):
    papers = [
        _make_paper(title="High Score", arxiv_id="2401.00001"),
        _make_paper(title="Low Score", arxiv_id="2401.00002"),
    ]
    papers[0].score = 7.0
    papers[1].score = 3.0

    corpus = [
        _make_corpus(title="Corpus RF", abstract="RF", paths=["RF-Circuit"]),
    ]
    sim_matrix = np.array([[0.9], [0.2]])

    importer.zot.items.return_value = []
    importer.zot.create_items.return_value = {
        "successful": {"0": {"key": "NEWKEY"}},
        "failed": {},
    }

    results = importer.import_papers(
        papers=papers,
        corpus=corpus,
        sim_matrix=sim_matrix,
        score_threshold=5.0,
    )
    assert len(results) == 1
    assert results[0]["status"] == "ok"