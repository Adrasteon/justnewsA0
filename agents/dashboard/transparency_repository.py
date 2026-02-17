"""Transparency data access layer for the dashboard service.

This repository surfaces fact-level provenance, evidence, and cluster
information to the transparency API. It is intentionally file-system driven so
operators can inspect and publish audit artefacts even before the database
schemas are finalized. When relational tables are available, the loader will
prefer them but still fall back to the archived JSON assets stored under
``archive_storage/transparency``.

The repository performs lightweight validation to ensure that every fact has
matching article, cluster, and evidence payloads prior to being returned to API
consumers. Missing artefacts are reported explicitly so the transparency
portal can fail safe without hiding gaps from the end user.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from common.observability import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class TransparencyRepository:
    """File-backed repository exposing transparency artefacts."""

    base_dir: Path
    require_strict: bool = True
    facts_dir: Path = field(init=False)
    articles_dir: Path = field(init=False)
    clusters_dir: Path = field(init=False)
    evidence_dir: Path = field(init=False)
    index_file: Path = field(init=False)

    def __post_init__(self) -> None:
        self.base_dir = self.base_dir.expanduser().resolve()
        self.facts_dir = self.base_dir / "facts"
        self.articles_dir = self.base_dir / "articles"
        self.clusters_dir = self.base_dir / "clusters"
        self.evidence_dir = self.base_dir / "evidence"

        if not self.base_dir.exists():
            raise FileNotFoundError(f"Transparency archive not found: {self.base_dir}")

        # Ensure sub-directories exist even when empty so operators notice gaps.
        for directory in (
            self.facts_dir,
            self.articles_dir,
            self.clusters_dir,
            self.evidence_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        self.index_file = self.base_dir / "index.json"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_status(self) -> dict[str, Any]:
        """Summarise repository health and artefact counts."""
        index_payload = self._load_index()
        facts = self._list_entities(self.facts_dir)
        clusters = self._list_entities(self.clusters_dir)
        articles = self._list_entities(self.articles_dir)
        evidences = self._list_entities(self.evidence_dir)

        last_updated = self._compute_last_updated(
            [
                index_payload.get("generated_at"),
                *(fact.get("last_updated") for fact in facts),
            ]
        )

        missing_assets = self._find_missing_assets(facts)

        integrity = {
            "status": "ok" if not missing_assets else "degraded",
            "missing_assets": missing_assets,
            "dataset_version": index_payload.get("dataset_version"),
        }

        status_payload = {
            "base_dir": str(self.base_dir),
            "counts": {
                "facts": len(facts),
                "clusters": len(clusters),
                "articles": len(articles),
                "evidence": len(evidences),
            },
            "last_updated": last_updated,
            "generated_at": index_payload.get("generated_at"),
            "integrity": integrity,
        }

        logger.debug("Transparency repository status computed: %s", status_payload)
        return status_payload

    def list_facts(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return most recent fact summaries."""
        index_payload = self._load_index()
        facts = index_payload.get("facts", [])
        facts_sorted = sorted(
            facts, key=lambda fact: fact.get("last_updated", ""), reverse=True
        )
        return facts_sorted[:limit]

    def get_fact(self, fact_id: str) -> dict[str, Any]:
        """Return full fact payload with linked article, cluster, and evidence."""
        fact_payload = self._load_entity(self.facts_dir, fact_id, entity_label="fact")

        article_id = fact_payload.get("article_id")
        cluster_id = fact_payload.get("cluster_id")
        evidence_ids = fact_payload.get("evidence_ids", [])

        article_payload = self._load_optional_entity(
            self.articles_dir, article_id, "article"
        )
        cluster_payload = self._load_optional_entity(
            self.clusters_dir, cluster_id, "cluster"
        )
        evidence_payloads = [
            self._load_optional_entity(self.evidence_dir, evidence_id, "evidence")
            for evidence_id in evidence_ids
        ]

        missing: list[str] = [
            label
            for label, payload in (
                ("article", article_payload),
                ("cluster", cluster_payload),
            )
            if payload is None
        ]

        missing.extend(
            f"evidence:{evidence_id}"
            for evidence_id, payload in zip(
                evidence_ids, evidence_payloads, strict=True
            )
            if payload is None
        )

        response = {
            "fact": fact_payload,
            "article": article_payload,
            "cluster": cluster_payload,
            "evidence": [
                payload for payload in evidence_payloads if payload is not None
            ],
            "missing_assets": missing,
        }

        if missing and self.require_strict:
            logger.warning("Fact %s missing referenced artefacts: %s", fact_id, missing)

        return response

    def get_cluster(self, cluster_id: str) -> dict[str, Any]:
        """Return cluster payload plus linked facts."""
        cluster_payload = self._load_entity(
            self.clusters_dir, cluster_id, entity_label="cluster"
        )
        fact_ids = cluster_payload.get("fact_ids", [])
        facts = [
            self._load_optional_entity(self.facts_dir, fact_id, "fact")
            for fact_id in fact_ids
        ]
        return {
            "cluster": cluster_payload,
            "facts": [fact for fact in facts if fact is not None],
            "missing_facts": [
                fact_id
                for fact_id, fact in zip(fact_ids, facts, strict=True)
                if fact is None
            ],
        }

    def get_article(self, article_id: str) -> dict[str, Any]:
        """Return article payload plus associated fact and cluster references."""
        article_payload = self._load_entity(
            self.articles_dir, article_id, entity_label="article"
        )
        index_payload = self._load_index()

        facts = [
            fact
            for fact in index_payload.get("facts", [])
            if fact.get("article_id") == article_id
        ]
        clusters = [
            cluster
            for cluster in index_payload.get("clusters", [])
            if any(
                member.get("article_id") == article_id
                for member in cluster.get("member_articles", [])
            )
        ]

        return {
            "article": article_payload,
            "related_facts": facts,
            "related_clusters": clusters,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_index(self) -> dict[str, Any]:
        if not self.index_file.exists():
            logger.warning("Transparency index missing: %s", self.index_file)
            return {}
        return self._load_json(self.index_file)

    def _load_entity(
        self, directory: Path, entity_id: str, *, entity_label: str
    ) -> dict[str, Any]:
        payload = self._load_optional_entity(directory, entity_id, entity_label)
        if payload is None:
            raise FileNotFoundError(
                f"{entity_label.capitalize()} {entity_id} not found in {directory}"
            )
        return payload

    def _load_optional_entity(
        self, directory: Path, entity_id: str | None, entity_label: str
    ) -> dict[str, Any] | None:
        if not entity_id:
            return None
        path = directory / f"{entity_id}.json"
        if not path.exists():
            logger.warning("Missing %s artefact at %s", entity_label, path)
            return None
        return self._load_json(path)

    def _load_json(self, path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _list_entities(self, directory: Path) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for path in sorted(directory.glob("*.json")):
            try:
                payloads.append(self._load_json(path))
            except json.JSONDecodeError as exc:
                logger.error("Failed to parse %s: %s", path, exc)
                if self.require_strict:
                    raise
        return payloads

    @staticmethod
    def _compute_last_updated(timestamps: list[str | None]) -> str | None:
        filtered = [ts for ts in timestamps if ts]
        if not filtered:
            return None
        try:
            return max(
                filtered,
                key=lambda ts: datetime.fromisoformat(ts.replace("Z", "+00:00")),
            )
        except ValueError:
            logger.debug("Unable to parse timestamps for last_updated: %s", filtered)
            return max(filtered)

    def _find_missing_assets(self, fact_summaries: list[dict[str, Any]]) -> list[str]:
        missing: list[str] = []
        for summary in fact_summaries:
            fact_id = summary.get("fact_id")
            article_id = summary.get("article_id")
            cluster_id = summary.get("cluster_id")
            evidence_ids = summary.get("evidence_ids", [])

            if article_id and not (self.articles_dir / f"{article_id}.json").exists():
                missing.append(f"fact:{fact_id}:article:{article_id}")
            if cluster_id and not (self.clusters_dir / f"{cluster_id}.json").exists():
                missing.append(f"fact:{fact_id}:cluster:{cluster_id}")
            for evidence_id in evidence_ids:
                if not (self.evidence_dir / f"{evidence_id}.json").exists():
                    missing.append(f"fact:{fact_id}:evidence:{evidence_id}")

        return missing


def default_repository() -> TransparencyRepository:
    """Factory using environment variables for path resolution."""
    base_path = os.environ.get("TRANSPARENCY_DATA_DIR")
    if base_path:
        return TransparencyRepository(Path(base_path))

    project_root = Path(__file__).resolve().parents[2]
    default_path = project_root / "archive_storage" / "transparency"
    return TransparencyRepository(default_path)


__all__ = ["TransparencyRepository", "default_repository"]
