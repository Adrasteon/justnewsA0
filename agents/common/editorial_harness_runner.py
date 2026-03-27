from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from agents.common.agent_chain_harness import AgentChainHarness, AgentChainResult
from agents.common.normalized_article_repository import (
    NormalizedArticleRepository,
)
from common.observability import get_logger
from common.stage_b_metrics import StageBMetrics, get_stage_b_metrics

logger = get_logger(__name__)


class HarnessResultPersistence:
    """Persist harness output back into the articles table."""

    def __init__(self, db_service) -> None:
        self.db_service = db_service

    def save(self, article_row: dict, result: AgentChainResult) -> None:
        self.db_service.ensure_conn()
        cursor = self.db_service.mb_conn.cursor()
        timestamp = datetime.now(UTC).isoformat()
        fact_check_payload = {
            "timestamp": timestamp,
            "claims": result.fact_checks,
            "acceptance_score": result.acceptance_score,
            "needs_followup": result.needs_followup,
        }
        synth_payload = {
            "timestamp": timestamp,
            "story_brief": result.story_brief,
            "draft": result.draft,
        }
        critic_payload = {
            "timestamp": timestamp,
            "source": "agent_chain_harness",
            "article_id": article_row.get("id"),
            "notes": "Dry-run harness output"
            if result.needs_followup
            else "Harness draft accepted",
        }
        fact_check_status = "needs_followup" if result.needs_followup else "accepted"
        try:
            cursor.execute(
                """
                UPDATE articles
                SET fact_check_status = %s,
                    fact_check_trace = %s,
                    critic_result = %s,
                    synth_trace = %s,
                    is_synthesized = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    fact_check_status,
                    json.dumps(fact_check_payload),
                    json.dumps(critic_payload),
                    json.dumps(synth_payload),
                    1 if result.draft else 0,
                    article_row.get("id"),
                ),
            )
            self.db_service.mb_conn.commit()
        finally:
            cursor.close()


class ArtifactWriter:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path.cwd() / "output" / "agent_chain_runs"
        self.root.mkdir(parents=True, exist_ok=True)

    def write(
        self, article_id: str | int, result: AgentChainResult, article_row: dict
    ) -> Path:
        payload = {
            "article_id": article_id,
            "metadata": article_row,
            "result": asdict(result),
        }
        path = self.root / f"{article_id}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True))
        return path


class AgentChainRunner:
    """Coordinate fetching articles, running the harness, persisting results, and emitting metrics."""

    def __init__(
        self,
        repository: NormalizedArticleRepository | None = None,
        harness: AgentChainHarness | None = None,
        *,
        persistence: HarnessResultPersistence | None = None,
        metrics: StageBMetrics | None = None,
        artifact_writer: ArtifactWriter | None = None,
        write_artifacts: bool = True,
        publish_on_accept: bool = False,
        publish_token: str | None = None,
    ) -> None:
        self.repository = repository or NormalizedArticleRepository()
        self.harness = harness or AgentChainHarness()
        self.persistence = persistence or HarnessResultPersistence(
            self.repository.db_service
        )
        self.metrics = metrics or get_stage_b_metrics()
        self.artifacts = (
            (artifact_writer or ArtifactWriter()) if write_artifacts else None
        )
        self.publish_on_accept = publish_on_accept
        self.publish_token = publish_token

    def run(
        self, *, limit: int = 5, article_ids: Sequence[int | str] | None = None
    ) -> list[AgentChainResult]:
        candidates = self.repository.fetch_candidates(
            limit=limit, article_ids=article_ids
        )
        if not candidates:
            logger.info("No normalized articles ready for the editorial harness.")
            return []

        results: list[AgentChainResult] = []
        for candidate in candidates:
            article_id = candidate.row.get("id")
            try:
                result = self.harness.run_article(candidate.article)
                self.persistence.save(candidate.row, result)
                # optionally publish accepted drafts
                if (
                    self.publish_on_accept
                    and not result.needs_followup
                    and result.acceptance_score
                    and result.acceptance_score >= 0.5
                ):
                    try:
                        from agents.common.publisher_integration import (
                            publish_normalized_article,
                            verify_publish_token,
                        )

                        # If a publish_token was supplied to the runner, verify it before publishing.
                        # If no token was supplied we allow publishing in environments where
                        # the operator intentionally did not set a gating token (e.g. local dev).
                        if self.publish_token is not None and not verify_publish_token(
                            self.publish_token
                        ):
                            logger.info(
                                "Publish skipped for article %s: approval token invalid or missing",
                                article_id,
                            )
                            try:
                                self.metrics.record_publish_result("skipped")
                            except Exception:
                                pass
                            raise RuntimeError("publish approval token invalid")
                        start = __import__("time").time()
                        ok = publish_normalized_article(
                            candidate.article,
                            author=candidate.row.get("authors") or "Editorial Harness",
                        )
                        elapsed = __import__("time").time() - start
                        try:
                            self.metrics.record_publish_result(
                                "success" if ok else "failure"
                            )
                            self.metrics.observe_publish_latency(elapsed)
                        except Exception:
                            logger.debug("Failed to record publish metrics")
                    except Exception:
                        logger.exception("Failed to publish article %s", article_id)
                        try:
                            self.metrics.record_publish_result("failure")
                        except Exception:
                            pass
                if self.artifacts:
                    self.artifacts.write(article_id, result, candidate.row)
                self._record_metrics(result)
                results.append(result)
                logger.info(
                    "Harness run completed for article %s (acceptance=%.3f, followup=%s)",
                    article_id,
                    result.acceptance_score,
                    result.needs_followup,
                )
            except Exception:
                logger.exception("Harness run failed for article %s", article_id)
                self.metrics.record_editorial_result("error")
        return results

    def _record_metrics(self, result: AgentChainResult) -> None:
        status = "needs_followup" if result.needs_followup else "accepted"
        self.metrics.record_editorial_result(status)
        self.metrics.observe_editorial_acceptance(result.acceptance_score)
