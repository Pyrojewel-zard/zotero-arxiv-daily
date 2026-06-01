import logging
import re
import time

import numpy as np
from pyzotero.zotero import Zotero

from zotero_arxiv_daily.protocol import CorpusPaper, Paper

logger = logging.getLogger(__name__)


class ZoteroImporter:
    def __init__(self, zotero_id: str, zotero_key: str, collection_map: dict[str, str]):
        self.zot = Zotero(zotero_id, "user", zotero_key)
        self.collection_map = collection_map
        self.key_to_name = {v: k for k, v in collection_map.items()}

    def find_best_collection(self, paper: Paper, corpus: list[CorpusPaper], sim_matrix: np.ndarray, paper_idx: int) -> tuple[str, str] | None:
        collection_scores: dict[str, float] = {}

        for j, cp in enumerate(corpus):
            for path in cp.paths:
                if path in self.collection_map:
                    key = self.collection_map[path]
                    score = float(sim_matrix[paper_idx, j])
                    if key not in collection_scores or score > collection_scores[key]:
                        collection_scores[key] = score

        if not collection_scores:
            return None

        best_key = max(collection_scores, key=collection_scores.get)
        return (best_key, self.key_to_name[best_key])

    @staticmethod
    def _normalize_doi(doi: str) -> str:
        return doi.lower().strip().removeprefix("https://doi.org/").removeprefix("doi:")

    @staticmethod
    def _normalize_arxiv_id(arxiv_id: str) -> str:
        return re.sub(r"v\d+$", "", arxiv_id.strip())

    def is_duplicate(self, paper: Paper) -> bool:
        if paper.doi:
            normalized = self._normalize_doi(paper.doi)
            items = self.zot.items(q=normalized)
            for item in items:
                item_doi = item.get("data", {}).get("DOI", "")
                if self._normalize_doi(item_doi) == normalized:
                    return True

        if paper.arxiv_id:
            normalized = self._normalize_arxiv_id(paper.arxiv_id)
            items = self.zot.items(q=normalized)
            for item in items:
                extra = item.get("data", {}).get("extra", "")
                url = item.get("data", {}).get("url", "")
                if f"arXiv: {normalized}" in extra or f"arxiv.org/abs/{normalized}" in url:
                    return True

        return False

    def import_paper(self, paper: Paper, collection_key: str) -> dict:
        collection_name = self.key_to_name.get(collection_key, "Unknown")

        if self.is_duplicate(paper):
            logger.info(f"Duplicate skipped: {paper.title}")
            return {"status": "duplicate", "collection": collection_name, "title": paper.title}

        template = {
            "itemType": "preprint",
            "title": paper.title,
            "abstractNote": paper.abstract or "",
            "url": paper.url or "",
            "collections": [collection_key],
        }

        if paper.doi:
            template["DOI"] = paper.doi
        if paper.arxiv_id:
            template["extra"] = f"arXiv: {paper.arxiv_id}"

        try:
            resp = self.zot.create_items([template])
            if resp.get("successful"):
                logger.info(f"Imported: {paper.title} -> {collection_name}")
                return {"status": "ok", "collection": collection_name, "title": paper.title}
            else:
                failed = resp.get("failed", {})
                logger.warning(f"Import failed: {paper.title} — {failed}")
                return {"status": "failed", "collection": collection_name, "title": paper.title}
        except Exception as e:
            logger.warning(f"Import error: {paper.title} — {e}")
            return {"status": "failed", "collection": collection_name, "title": paper.title}

    def import_papers(
        self,
        papers: list[Paper],
        corpus: list[CorpusPaper],
        sim_matrix: np.ndarray,
        score_threshold: float = 5.0,
    ) -> list[dict]:
        results = []

        for i, paper in enumerate(papers):
            score = getattr(paper, "score", 0)
            if score < score_threshold:
                continue

            match = self.find_best_collection(paper, corpus, sim_matrix, paper_idx=i)
            if match is None:
                continue

            collection_key, collection_name = match
            result = self.import_paper(paper, collection_key)
            results.append(result)

            time.sleep(0.5)

        logger.info(f"Import summary: {len([r for r in results if r['status'] == 'ok'])} ok, "
                     f"{len([r for r in results if r['status'] == 'duplicate'])} dup, "
                     f"{len([r for r in results if r['status'] == 'failed'])} failed")
        return results
