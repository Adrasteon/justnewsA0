"""
Chief Editor Tools - Utility Functions for Editorial Operations

This module provides utility functions for editorial workflow orchestration,
content analysis, and multi-agent coordination.

Key Functions:
- assess_content_quality: Qwen-based quality assessment
- categorize_content: Qwen-based categorization
- analyze_editorial_sentiment: Qwen-based sentiment analysis
- generate_editorial_commentary: Qwen-based commentary generation
- make_editorial_decision: Comprehensive editorial decision making
- request_story_brief: Story brief generation
- publish_story: Publishing coordination
- review_evidence: Evidence review queue management

All functions include robust error handling, validation, and fallbacks.
"""

import json
import os
import time
import re
from datetime import datetime
import mysql.connector
from typing import Any

from common.observability import get_logger
from agents.common.headline_adapter import HeadlineAdapter

from .chief_editor_engine import ChiefEditorConfig, ChiefEditorEngine

logger = get_logger(__name__)

_HEADLINE_ADAPTER = HeadlineAdapter(name="chief_editor_title_llm")


_PLACEHOLDER_SYNTH_TITLE = re.compile(
    r"^\s*(\[brief\]\s*)?synthesis\s+report\s*:\s*cl-[a-f0-9]+\s*$",
    re.IGNORECASE,
)


def _generate_llm_title_candidates(summary: str, body: str) -> list[str]:
    context = "\n".join(part for part in [summary.strip(), body.strip()[:1500]] if part).strip()
    if not context:
        return []
    return _HEADLINE_ADAPTER.generate_candidates(context)


def _derive_publication_title(raw_title: str, summary: str, body: str) -> str:
    title = (raw_title or "").strip()
    if title and not _PLACEHOLDER_SYNTH_TITLE.match(title):
        seeded = HeadlineAdapter.headlineize(title)
        if seeded and not HeadlineAdapter.is_sensational(seeded):
            return seeded

    llm_candidates = _generate_llm_title_candidates(summary, body)
    headline = HeadlineAdapter.select_best_headline(
        llm_candidates,
        min_len=10,
        disallowed_pattern=_PLACEHOLDER_SYNTH_TITLE,
    )
    if headline:
        return headline

    for candidate in (summary, body):
        normalized = re.sub(r"\s+", " ", (candidate or "").strip())
        if not normalized:
            continue
        sentence = re.split(r"(?<=[.!?])\s+", normalized, maxsplit=1)[0].strip()
        if len(sentence) < 12:
            continue
        fallback = HeadlineAdapter.headlineize(sentence)
        if fallback and not HeadlineAdapter.is_sensational(fallback):
            return fallback

    return "Developing Story"


def _derive_publication_summary(body: str, max_words: int = 42) -> str:
    normalized = re.sub(r"\s+", " ", (body or "").strip())
    if not normalized:
        return ""

    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    summary = " ".join(sentences[:2]).strip() or normalized
    words = summary.split()
    if len(words) > max_words:
        summary = " ".join(words[:max_words]).rstrip(" ,;:-") + "…"
    return summary


def _resolve_publication_summary(body: str, source_summary: str, title: str) -> str:
    summary = _derive_publication_summary(body)
    if summary:
        return summary

    normalized_source = re.sub(r"\s+", " ", (source_summary or "").strip())
    if normalized_source:
        return normalized_source

    normalized_title = re.sub(r"\s+", " ", (title or "").strip())
    if normalized_title:
        return normalized_title

    return "Developing story updates are being verified."


def _is_collapsed_publication_body(body: str, summary: str) -> bool:
    normalized_body = re.sub(r"\s+", " ", (body or "")).strip().lower()
    normalized_summary = re.sub(r"\s+", " ", (summary or "")).strip().lower()

    if not normalized_body:
        return True

    body_words = len(normalized_body.split())
    if body_words < 80:
        return True

    if normalized_summary and normalized_body == normalized_summary:
        return True

    if normalized_summary and len(normalized_summary) >= 40:
        overlap = normalized_body[: len(normalized_summary)]
        if overlap == normalized_summary and len(normalized_body) <= int(len(normalized_summary) * 1.2):
            return True

    return False


def _expand_publication_body_from_sources(
    source: dict[str, Any],
    cursor: Any | None,
    body: str,
    summary: str,
) -> str:
    snippets: list[str] = []

    normalized_summary = re.sub(r"\s+", " ", (summary or "")).strip()
    if normalized_summary:
        snippets.append(normalized_summary)

    raw_input_articles = source.get("input_articles")
    parsed_items = []
    if isinstance(raw_input_articles, str) and raw_input_articles.strip():
        try:
            parsed_items = json.loads(raw_input_articles)
        except Exception:
            parsed_items = []
    elif isinstance(raw_input_articles, list):
        parsed_items = raw_input_articles

    article_ids: list[int] = []
    for item in parsed_items if isinstance(parsed_items, list) else []:
        if isinstance(item, dict):
            local_text = " ".join(
                str(item.get(key) or "").strip()
                for key in ["title", "summary", "content", "body"]
            ).strip()
            if local_text:
                snippets.append(local_text)
            candidate_id = item.get("id")
            if str(candidate_id).isdigit():
                article_ids.append(int(candidate_id))
        elif str(item).isdigit():
            article_ids.append(int(item))

    if cursor is not None and article_ids:
        try:
            placeholders = ",".join(["%s"] * len(article_ids))
            cursor.execute(
                f"""
                SELECT title, summary, content
                FROM articles
                WHERE id IN ({placeholders})
                ORDER BY created_at DESC
                LIMIT 40
                """,
                tuple(article_ids),
            )
            for row in cursor.fetchall() or []:
                row_text = " ".join(
                    str((row.get(key) if isinstance(row, dict) else "") or "").strip()
                    for key in ["title", "summary", "content"]
                ).strip()
                if row_text:
                    snippets.append(row_text)
        except Exception:
            pass

    sentences: list[str] = []
    seen: set[str] = set()
    for raw in snippets:
        normalized = re.sub(r"\s+", " ", str(raw or "")).strip()
        if not normalized:
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", normalized):
            candidate = re.sub(r"\s+", " ", sentence).strip()
            if len(candidate) < 35:
                continue
            key = candidate.lower()
            if key in seen:
                continue
            seen.add(key)
            sentences.append(candidate)
            if len(sentences) >= 20:
                break
        if len(sentences) >= 20:
            break

    if not sentences:
        return body

    paragraphs: list[str] = []
    for index in range(0, len(sentences), 3):
        paragraph = " ".join(sentences[index : index + 3]).strip()
        if paragraph:
            paragraphs.append(paragraph)

    expanded = "\n\n".join(paragraphs).strip()
    return expanded if len(expanded) > len((body or "").strip()) else body


_CATEGORY_ALIASES = {
    "world": "world",
    "international": "world",
    "global": "world",
    "uk": "uk",
    "britain": "uk",
    "business": "business",
    "economy": "business",
    "finance": "business",
    "markets": "business",
    "politics": "politics",
    "policy": "politics",
    "government": "politics",
    "health": "health",
    "medicine": "health",
    "science": "science",
    "technology": "technology",
    "tech": "technology",
    "entertainment": "entertainment",
    "culture": "entertainment",
    "sport": "sport",
    "sports": "sport",
    "general": "world",
}


_CATEGORY_SIGNAL_KEYWORDS = {
    "politics": [
        "election",
        "parliament",
        "congress",
        "senate",
        "minister",
        "policy",
        "government",
        "vote",
    ],
    "business": [
        "market",
        "inflation",
        "interest rate",
        "stock",
        "shares",
        "earnings",
        "merger",
        "bank",
        "economy",
    ],
    "technology": [
        "ai",
        "artificial intelligence",
        "chip",
        "software",
        "cyber",
        "startup",
        "cloud",
        "openai",
    ],
    "science": [
        "research",
        "study",
        "scientists",
        "laboratory",
        "climate",
        "physics",
        "space",
        "nasa",
    ],
    "health": [
        "hospital",
        "vaccine",
        "disease",
        "virus",
        "medical",
        "nhs",
        "patient",
        "health",
    ],
    "sport": [
        "match",
        "league",
        "tournament",
        "goal",
        "coach",
        "premier league",
        "fifa",
        "olympic",
    ],
    "entertainment": [
        "film",
        "movie",
        "music",
        "celebrity",
        "tv",
        "streaming",
        "festival",
        "box office",
    ],
    "uk": [
        "uk",
        "britain",
        "british",
        "london",
        "westminster",
        "england",
        "scotland",
        "wales",
    ],
    "world": [
        "un",
        "nato",
        "international",
        "global",
        "diplomatic",
        "foreign",
    ],
}


def _compute_keyword_category_scores(title: str, summary: str, body: str) -> dict[str, float]:
    text = " ".join(part for part in [title or "", summary or "", body or ""] if part).lower()
    if not text:
        return {}

    def keyword_present(haystack: str, needle: str) -> bool:
        escaped = re.escape(needle.lower())
        return bool(re.search(rf"\b{escaped}\b", haystack, flags=re.IGNORECASE))

    scores: dict[str, float] = {}
    for category, needles in _CATEGORY_SIGNAL_KEYWORDS.items():
        hits = 0
        for needle in needles:
            if keyword_present(text, needle):
                hits += 1
        if hits:
            scores[category] = min(1.0, hits / 3.0)
    return scores


def _normalize_publication_category(raw_category: Any) -> str:
    if raw_category is None:
        return "world"
    normalized = str(raw_category).strip().lower()
    if not normalized:
        return "world"
    if normalized in _CATEGORY_ALIASES:
        return _CATEGORY_ALIASES[normalized]

    keyword_map = {
        "politic": "politics",
        "elect": "politics",
        "government": "politics",
        "business": "business",
        "econom": "business",
        "market": "business",
        "finance": "business",
        "tech": "technology",
        "science": "science",
        "health": "health",
        "medical": "health",
        "sport": "sport",
        "entertain": "entertainment",
        "culture": "entertainment",
        "world": "world",
        "international": "world",
        "uk": "uk",
        "brit": "uk",
    }
    for needle, mapped in keyword_map.items():
        if needle in normalized:
            return mapped
    return "world"


def _derive_publication_category(
    source: dict[str, Any],
    title: str,
    summary: str,
    body: str,
    cursor: Any | None = None,
) -> str:
    weighted_scores: dict[str, float] = {}

    def add_score(category_value: Any, weight: float):
        normalized = _normalize_publication_category(category_value)
        weighted_scores[normalized] = weighted_scores.get(normalized, 0.0) + max(0.0, float(weight))

    metadata_category = None
    if source.get("synth_metadata"):
        try:
            meta = json.loads(source["synth_metadata"])
            if isinstance(meta, dict):
                metadata_category = meta.get("category")
        except Exception:
            metadata_category = None

    normalized_from_meta = _normalize_publication_category(metadata_category)
    if metadata_category is not None and normalized_from_meta:
        add_score(normalized_from_meta, 0.35)

    if cursor is not None:
        try:
            raw_input_articles = source.get("input_articles")
            parsed_ids = json.loads(raw_input_articles) if isinstance(raw_input_articles, str) else raw_input_articles
            article_ids = [int(item) for item in (parsed_ids or []) if str(item).isdigit()]
            if article_ids:
                placeholders = ",".join(["%s"] * len(article_ids))
                cursor.execute(
                    f"""
                    SELECT section, COUNT(*) AS c
                    FROM articles
                    WHERE id IN ({placeholders})
                      AND section IS NOT NULL
                      AND TRIM(section) <> ''
                    GROUP BY section
                    ORDER BY c DESC
                    LIMIT 10
                    """,
                    tuple(article_ids),
                )
                rows = cursor.fetchall() or []
                total = sum(
                    float((row.get("c") if isinstance(row, dict) else (row[1] if len(row) > 1 else 0)) or 0)
                    for row in rows
                )
                if total > 0:
                    for row in rows:
                        section_value = (
                            row.get("section") if isinstance(row, dict) else (row[0] if len(row) > 0 else None)
                        )
                        count_value = float(
                            (row.get("c") if isinstance(row, dict) else (row[1] if len(row) > 1 else 0)) or 0
                        )
                        if section_value and count_value > 0:
                            add_score(section_value, 0.45 * (count_value / total))
        except Exception:
            pass

    keyword_scores = _compute_keyword_category_scores(title, summary, body)
    for keyword_category, keyword_score in keyword_scores.items():
        add_score(keyword_category, 0.35 * keyword_score)

    try:
        classification = categorize_content("\n\n".join([title or "", summary or "", body or ""]))
        predicted = classification.get("category") if isinstance(classification, dict) else None
        confidence = classification.get("confidence", 0.0) if isinstance(classification, dict) else 0.0
        normalized_predicted = _normalize_publication_category(predicted)
        clamped_confidence = min(1.0, max(0.0, float(confidence or 0.0)))
        if normalized_predicted:
            add_score(normalized_predicted, 0.20 + (0.80 * clamped_confidence))
    except Exception:
        pass

    if weighted_scores:
        ordered = sorted(weighted_scores.items(), key=lambda item: item[1], reverse=True)
        winner, winner_score = ordered[0]
        if winner == "world" and len(ordered) > 1:
            runner_up, runner_score = ordered[1]
            if runner_up != "world" and (winner_score - runner_score) <= 0.12:
                return runner_up
        return winner

    return "world"


def _resolve_publication_evidence(source: dict[str, Any], cursor: Any | None = None) -> str:
    raw_input_articles = source.get("input_articles")
    parsed_items: list[Any] = []
    if isinstance(raw_input_articles, str) and raw_input_articles.strip():
        try:
            loaded = json.loads(raw_input_articles)
            if isinstance(loaded, list):
                parsed_items = loaded
        except Exception:
            return raw_input_articles
    elif isinstance(raw_input_articles, list):
        parsed_items = raw_input_articles

    if not parsed_items:
        return str(raw_input_articles or "")

    evidence_lines: list[str] = []
    article_ids: list[int] = []
    seen_urls: set[str] = set()

    for item in parsed_items:
        if isinstance(item, dict):
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or item.get("source_url") or "").strip()
            item_id = item.get("id")
            if str(item_id).isdigit():
                article_ids.append(int(item_id))

            if url:
                seen_urls.add(url)
                if title and item_id:
                    evidence_lines.append(f"[{item_id}] {title} — {url}")
                elif title:
                    evidence_lines.append(f"{title} — {url}")
                elif item_id:
                    evidence_lines.append(f"[{item_id}] {url}")
                else:
                    evidence_lines.append(url)
            elif title:
                evidence_lines.append(f"[{item_id}] {title}" if item_id else title)
        elif str(item).isdigit():
            article_ids.append(int(item))

    if cursor is not None and article_ids:
        try:
            placeholders = ",".join(["%s"] * len(article_ids))
            cursor.execute(
                f"""
                SELECT id, title, source_url
                FROM articles
                WHERE id IN ({placeholders})
                ORDER BY created_at DESC
                LIMIT 50
                """,
                tuple(article_ids),
            )
            rows = cursor.fetchall() or []
            for row in rows:
                row_id = row.get("id") if isinstance(row, dict) else None
                title = str((row.get("title") if isinstance(row, dict) else "") or "").strip()
                url = str((row.get("source_url") if isinstance(row, dict) else "") or "").strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                if title and row_id:
                    evidence_lines.append(f"[{row_id}] {title} — {url}")
                elif title:
                    evidence_lines.append(f"{title} — {url}")
                elif row_id:
                    evidence_lines.append(f"[{row_id}] {url}")
                else:
                    evidence_lines.append(url)
        except Exception:
            pass

    if evidence_lines:
        return "\n".join(evidence_lines)

    compact_ids = [str(item) for item in parsed_items if str(item).isdigit()]
    if compact_ids:
        return "Source article IDs: " + ", ".join(compact_ids)

    return str(raw_input_articles or "")

# Global engine instance
_engine: ChiefEditorEngine | None = None


def get_chief_editor_engine() -> ChiefEditorEngine:
    """Get or create the global chief editor engine instance."""
    global _engine
    if _engine is None:
        config = ChiefEditorConfig()
        _engine = ChiefEditorEngine(config)
    return _engine


async def process_editorial_request(
    content: str, operation_type: str, **kwargs
) -> dict[str, Any]:
    """
    Process an editorial request using the chief editor engine.

    Args:
        content: Content to process
        operation_type: Type of editorial operation to perform
        **kwargs: Additional parameters for operation

    Returns:
        Editorial operation results dictionary
    """
    engine = get_chief_editor_engine()

    try:
        logger.info(
            f"🎯 Processing {operation_type} editorial operation for {len(content)} characters"
        )

        if operation_type == "quality":
            result = engine.assess_content_quality(content)
        elif operation_type == "categorize":
            result = engine.categorize_content(content)
        elif operation_type == "sentiment":
            result = engine.analyze_editorial_sentiment(content)
        elif operation_type == "commentary":
            context = kwargs.get("context", "news article")
            result = engine.generate_editorial_commentary(content, context)
        elif operation_type == "decision":
            metadata = kwargs.get("metadata")
            result = engine.make_editorial_decision(content, metadata)
        else:
            result = {"error": f"Unknown operation type: {operation_type}"}

        logger.info(f"✅ {operation_type.capitalize()} editorial operation completed")
        return result

    except Exception as e:
        logger.error(f"❌ {operation_type} editorial operation failed: {e}")
        return {"error": str(e)}


def assess_content_quality(
    content: str, metadata: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Assess content quality using Qwen-based analysis.

    This function evaluates the overall quality of news content using
    advanced NLP models to determine publication readiness.

    Args:
        content: Content to assess for quality
        metadata: Additional metadata for context

    Returns:
        Dictionary containing quality assessment results
    """
    if not content or not content.strip():
        return {
            "overall_quality": 0.0,
            "assessment": "empty",
            "error": "Empty content provided",
        }

    engine = get_chief_editor_engine()
    return engine.assess_content_quality(content)


def categorize_content(
    content: str, metadata: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Categorize content using Qwen-based classification.

    This function automatically categorizes news content into appropriate
    editorial categories for workflow routing.

    Args:
        content: Content to categorize
        metadata: Additional metadata for context

    Returns:
        Dictionary containing categorization results
    """
    if not content or not content.strip():
        return {
            "category": "unknown",
            "confidence": 0.0,
            "error": "Empty content provided",
        }

    engine = get_chief_editor_engine()
    return engine.categorize_content(content)


def analyze_editorial_sentiment(
    content: str, metadata: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Analyze editorial sentiment using Qwen-based analysis.

    This function determines the editorial tone and sentiment of content
    to inform publication decisions.

    Args:
        content: Content to analyze for sentiment
        metadata: Additional metadata for context

    Returns:
        Dictionary containing sentiment analysis results
    """
    if not content or not content.strip():
        return {
            "sentiment": "neutral",
            "confidence": 0.0,
            "error": "Empty content provided",
        }

    engine = get_chief_editor_engine()
    return engine.analyze_editorial_sentiment(content)


def generate_editorial_commentary(
    content: str, context: str = "news article"
) -> dict[str, Any]:
    """
    Generate editorial commentary using Qwen-based generation.

    This function creates editorial notes and commentary for content
    to guide the editorial workflow.

    Args:
        content: Content for commentary generation
        context: Context for commentary (e.g., "news article", "breaking news")

    Returns:
        Dictionary containing generated commentary
    """
    if not content or not content.strip():
        return {"commentary": "", "error": "Empty content provided"}

    engine = get_chief_editor_engine()
    commentary = engine.generate_editorial_commentary(content, context)

    return {
        "commentary": commentary,
        "context": context,
        "content_length": len(content),
        "model": "qwen-14b",
    }


def make_editorial_decision(
    content: str, metadata: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Make comprehensive editorial decision using Qwen-based multi-task analysis.

    This function provides a complete editorial assessment including
    quality, categorization, sentiment, and workflow recommendations.

    Args:
        content: Content for editorial decision
        metadata: Additional metadata for context

    Returns:
        Dictionary containing comprehensive editorial decision
    """
    if not content or not content.strip():
        return {"error": "Empty content provided for editorial decision"}

    engine = get_chief_editor_engine()
    decision = engine.make_editorial_decision(content, metadata)

    # Convert dataclass to dictionary
    return {
        "priority": decision.priority.value,
        "stage": decision.stage.value,
        "confidence": decision.confidence,
        "reasoning": decision.reasoning,
        "next_actions": decision.next_actions,
        "agent_assignments": list(decision.agent_assignments.keys()),
        "metadata": decision.metadata,
        "decision_timestamp": time.time(),
    }


def request_story_brief(topic: str, scope: str) -> dict[str, Any]:
    """
    Generate a story brief for editorial planning.

    This function creates structured story briefs to guide content development
    and editorial planning across the newsroom.

    Args:
        topic: Story topic
        scope: Story scope/coverage area

    Returns:
        Dictionary containing generated story brief
    """
    if not topic or not topic.strip():
        return {"error": "Empty topic provided for story brief"}

    try:
        # Use the engine for brief generation if available, otherwise fallback
        engine = get_chief_editor_engine()

        brief_content = engine.generate_editorial_commentary(
            f"Generate a story brief for topic: {topic} with scope: {scope}",
            "story brief",
        )

        brief = {
            "topic": topic,
            "scope": scope,
            "brief": brief_content,
            "generated_at": time.time(),
            "status": "generated",
        }

        # Log feedback for training
        engine.log_feedback(
            "request_story_brief",
            {"topic": topic, "scope": scope, "brief_length": len(brief_content)},
        )

        # Collect prediction for training
        try:
            from training_system import collect_prediction

            collect_prediction(
                agent_name="chief_editor",
                task_type="story_brief_generation",
                input_text=f"Topic: {topic}, Scope: {scope}",
                prediction={"brief": brief_content},
                confidence=0.8,
                source_url="",
            )
            logger.debug("📊 Training data collected for story brief generation")
        except ImportError:
            logger.debug("Training system not available - skipping data collection")
        except Exception as e:
            logger.warning(f"Failed to collect training data: {e}")

        return brief

    except Exception as e:
        logger.error(f"Error generating story brief: {e}")
        return {"error": str(e)}


def publish_story(story_id: str) -> dict[str, Any]:
    """
    Coordinate story publishing across the editorial workflow.

    This function manages the publishing process, coordinating with
    other agents and updating editorial timelines.

    Args:
        story_id: ID of the story to publish

    Returns:
        Dictionary containing publishing results
    """
    if not story_id or not story_id.strip():
        return {"error": "Empty story ID provided for publishing"}

    try:
        # Connect to JustNews MariaDB to publish the article
        db_config = {
            'user': os.environ.get("MARIADB_USER", "justnews"),
            'password': os.environ.get("MARIADB_PASSWORD", "dev_justnews_password"),
            'host': os.environ.get("MARIADB_HOST", "mariadb"),
            'port': int(os.environ.get("MARIADB_PORT", 3306)),
            'database': os.environ.get("MARIADB_DB", "justnews"),
            'autocommit': True,
            'use_pure': True
        }

        # Use context managers for automatic cleanup
        with mysql.connector.connect(**db_config) as conn:
            with conn.cursor(dictionary=True) as cursor:
                # 1. Fetch from synthesized_articles
                cursor.execute("SELECT * FROM synthesized_articles WHERE story_id = %s", (story_id,))
                source = cursor.fetchone()

                if not source:
                     return {"error": f"Story ID {story_id} not found in synthesized_articles"}

                # 2. Extract and Transform
                title = source.get('title') or "Untitled Story"
                body = source.get('body') or ""
                summary = _resolve_publication_summary(
                    body=body,
                    source_summary=source.get('summary') or "",
                    title=title,
                )

                if _is_collapsed_publication_body(body, summary):
                    body = _expand_publication_body_from_sources(source, cursor, body, summary)
                    summary = _resolve_publication_summary(
                        body=body,
                        source_summary=source.get('summary') or "",
                        title=title,
                    )

                title = _derive_publication_title(title, summary, body)

                headline_input = "\n".join(
                    part
                    for part in [summary.strip(), body.strip()[:1500]]
                    if isinstance(part, str) and part.strip()
                ).strip()
                if headline_input:
                    HeadlineAdapter.collect_training_example(
                        input_text=headline_input,
                        prediction={
                            "headline": title,
                            "story_id": story_id,
                            "source": "publish_story",
                        },
                        confidence=0.88,
                        source_url="",
                    )

                # Create stable slug (reuse existing story slug when republishing)
                story_suffix = story_id[:8]
                cursor.execute(
                    """
                    SELECT slug
                    FROM news_article
                    WHERE slug LIKE %s
                    ORDER BY updated_at DESC, id DESC
                    LIMIT 1
                    """,
                    (f"%-{story_suffix}",),
                )
                existing_slug_row = cursor.fetchone()
                if existing_slug_row and existing_slug_row.get("slug"):
                    slug = str(existing_slug_row["slug"])
                else:
                    slug_base = re.sub(r'[^a-zA-Z0-9]+', '-', title.lower()).strip('-')
                    slug = f"{slug_base[:40]}-{story_suffix}"

                evidence = _resolve_publication_evidence(source, cursor=cursor)
                
                category = _derive_publication_category(source, title, summary, body, cursor=cursor)
                
                now = datetime.now()
                author = "Chief Editor"
                score = 0.9  # Default score

                # 3. Upsert into news_article
                upsert_sql = """
                    INSERT INTO news_article 
                    (title, slug, summary, body, published_at, updated_at, author, score, evidence, is_featured, category)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    title=VALUES(title),
                    summary=VALUES(summary),
                    body=VALUES(body),
                    published_at=VALUES(published_at),
                    updated_at=VALUES(updated_at),
                    author=VALUES(author),
                    score=VALUES(score),
                    evidence=VALUES(evidence),
                    category=VALUES(category)
                """
                cursor.execute(upsert_sql, (
                    title, slug, summary, body, now, now, author, score, evidence, 0, category
                ))

                cursor.execute(
                    """
                    SELECT id
                    FROM news_article
                    WHERE slug = %s
                    ORDER BY updated_at DESC, id DESC
                    LIMIT 1
                    """,
                    (slug,),
                )
                article_row = cursor.fetchone()
                article_id = article_row.get("id") if article_row else None

                publish_provenance = {
                    "timestamp": now.isoformat() + "Z",
                    "actor": "chief_editor",
                    "story_id": story_id,
                    "article_id": article_id,
                    "slug": slug,
                    "category": category,
                    "source_model": "rule_based",
                }

                # 4. Mark as Published
                cursor.execute(
                    """
                    UPDATE synthesized_articles
                    SET is_published = 1,
                        published_at = %s,
                        summary = CASE
                            WHEN COALESCE(TRIM(summary), '') = '' THEN %s
                            ELSE summary
                        END
                    WHERE story_id = %s AND is_published = 0
                    """,
                    (now, summary, story_id)
                )
                publish_marked = cursor.rowcount > 0

                try:
                    raw_meta = source.get("synth_metadata")
                    existing_meta = json.loads(raw_meta) if isinstance(raw_meta, str) and raw_meta.strip() else (raw_meta if isinstance(raw_meta, dict) else {})
                except Exception:
                    existing_meta = {}
                publish_meta = existing_meta.get("publish") if isinstance(existing_meta.get("publish"), dict) else {}
                history = publish_meta.get("history") if isinstance(publish_meta.get("history"), list) else []
                history.append(publish_provenance)
                existing_meta["publish"] = {
                    "last_event": publish_provenance,
                    "history": history[-25:],
                }
                cursor.execute(
                    """
                    UPDATE synthesized_articles
                    SET synth_metadata = %s
                    WHERE story_id = %s
                    """,
                    (json.dumps(existing_meta), story_id),
                )

                try:
                    payload = {
                        "story_id": story_id,
                        "slug": slug,
                        "title": title,
                        "category": category,
                        "status": "success" if publish_marked else "skipped",
                        "source": "chief_editor.publish_story",
                        "model": "rule_based",
                    }
                    cursor.execute(
                        """
                        INSERT INTO news_publishaudit
                        (article_id, status, actor, token, latency_seconds, payload, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, NOW())
                        """,
                        (
                            article_id,
                            "success" if publish_marked else "skipped",
                            "chief_editor",
                            "",
                            None,
                            json.dumps(payload),
                        ),
                    )
                except Exception as audit_error:
                    logger.warning(f"Failed to persist publish audit for {story_id}: {audit_error}")

        status = "published" if publish_marked else "published_already"
        result = {
            "status": status,
            "story_id": story_id,
            "message": "Story published to website successfully" if publish_marked else "Story already published; publication refreshed successfully",
            "published_at": time.time(),
            "timestamp": time.time(),
            "model": "rule_based"
        }

        # Log feedback for training
        engine = get_chief_editor_engine()
        engine.log_feedback("publish_story", {"story_id": story_id, "status": status})

        # Collect prediction for training
        try:
            from training_system import collect_prediction

            collect_prediction(
                agent_name="chief_editor",
                task_type="story_publishing",
                input_text=story_id,
                prediction=result,
                confidence=0.9,
                source_url="",
            )
            logger.debug("📊 Training data collected for story publishing")
        except ImportError:
            logger.debug("Training system not available - skipping data collection")
        except Exception as e:
            logger.warning(f"Failed to collect training data: {e}")

        return result

    except Exception as e:
        logger.error(f"Error publishing story: {e}")
        return {"error": str(e)}


def review_evidence(evidence_manifest: str, reason: str) -> dict[str, Any]:
    """
    Queue evidence for human review and editorial oversight.

    This function manages the evidence review queue, notifying editors
    and maintaining audit trails for editorial decisions.

    Args:
        evidence_manifest: Path or identifier for evidence
        reason: Reason for requesting review

    Returns:
        Dictionary containing review queue results
    """
    if not evidence_manifest or not evidence_manifest.strip():
        return {"error": "Empty evidence manifest provided"}

    try:
        # Import the handler function
        from agents.chief_editor.handler import handle_review_request

        # Queue the review request
        result = handle_review_request(
            {"evidence_manifest": evidence_manifest, "reason": reason}
        )

        # Add timestamp and additional metadata
        result.update(
            {
                "queued_at": time.time(),
                "evidence_manifest": evidence_manifest,
                "reason": reason,
            }
        )

        # Log feedback
        engine = get_chief_editor_engine()
        engine.log_feedback(
            "review_evidence",
            {"evidence_manifest": evidence_manifest, "reason": reason},
        )

        return result

    except Exception as e:
        logger.error(f"Error queuing evidence review: {e}")
        return {"error": str(e)}


async def health_check() -> dict[str, Any]:
    """
    Perform health check on chief editor components.

    Returns:
        Health check results with component status
    """
    try:
        engine = get_chief_editor_engine()

        model_status = engine.get_model_status()

        health_status = {
            "timestamp": time.time(),
            "overall_status": "healthy",
            "components": {
                "engine": "healthy",
                "mcp_bus": "healthy",  # Assume healthy unless proven otherwise
                "evidence_queue": "healthy",
            },
            "model_status": model_status,
            "processing_stats": engine.processing_stats,
        }

        # Check for any unhealthy components
        unhealthy_components = [
            k for k, v in health_status["components"].items() if v == "unhealthy"
        ]
        if unhealthy_components:
            health_status["overall_status"] = "degraded"
            health_status["issues"] = [
                f"Component {comp} is unhealthy" for comp in unhealthy_components
            ]

        # Check primary model availability
        if not model_status.get("qwen_adapter", False):
            health_status["overall_status"] = "degraded"
            health_status["issues"] = health_status.get("issues", []) + [
                "Qwen adapter is disabled or unavailable"
            ]

        logger.info(f"🏥 Chief Editor health check: {health_status['overall_status']}")
        return health_status

    except Exception as e:
        logger.error(f"🏥 Chief Editor health check failed: {e}")
        return {
            "timestamp": time.time(),
            "overall_status": "unhealthy",
            "error": str(e),
        }


def validate_editorial_result(
    result: dict[str, Any], expected_fields: list[str] = None
) -> bool:
    """
    Validate editorial result structure.

    Args:
        result: Editorial result to validate
        expected_fields: List of expected fields (optional)

    Returns:
        True if result is valid, False otherwise
    """
    if not isinstance(result, dict):
        return False

    if "error" in result:
        return True  # Error results are valid

    if expected_fields:
        return all(field in result for field in expected_fields)

    # Basic validation for common fields
    common_fields = ["model", "processing_time", "timestamp"]
    return any(field in result for field in common_fields)


def format_editorial_output(result: dict[str, Any], format_type: str = "json") -> str:
    """
    Format editorial result for output.

    Args:
        result: Editorial result to format
        format_type: Output format ("json", "text", "markdown")

    Returns:
        Formatted output string
    """
    try:
        if format_type == "json":
            return json.dumps(result, indent=2, default=str)

        elif format_type == "text":
            if "error" in result:
                return f"Error: {result['error']}"

            lines = []
            if "overall_quality" in result:
                lines.append(f"Quality Score: {result['overall_quality']:.2f}")
                lines.append(f"Assessment: {result.get('assessment', 'N/A')}")

            if "category" in result:
                lines.append(f"Category: {result['category']}")
                lines.append(f"Confidence: {result.get('confidence', 0):.2f}")

            if "sentiment" in result:
                lines.append(f"Sentiment: {result['sentiment']}")
                lines.append(f"Editorial Tone: {result.get('editorial_tone', 'N/A')}")

            if "priority" in result:
                lines.append(f"Editorial Priority: {result['priority']}")
                lines.append(f"Workflow Stage: {result.get('stage', 'N/A')}")

            if "brief" in result:
                lines.append(f"Story Brief: {result['brief']}")

            return "\n".join(lines)

        elif format_type == "markdown":
            if "error" in result:
                return f"## Editorial Analysis Error\n\n{result['error']}"

            lines = ["# Editorial Analysis Results\n"]

            if "overall_quality" in result:
                lines.append("## Quality Assessment")
                lines.append(f"- **Quality Score**: {result['overall_quality']:.2f}")
                lines.append(f"- **Assessment**: {result.get('assessment', 'N/A')}")

            if "category" in result:
                lines.append("## Content Categorization")
                lines.append(f"- **Category**: {result['category']}")
                lines.append(f"- **Confidence**: {result.get('confidence', 0):.2f}")

            if "sentiment" in result:
                lines.append("## Editorial Sentiment")
                lines.append(f"- **Sentiment**: {result['sentiment']}")
                lines.append(
                    f"- **Editorial Tone**: {result.get('editorial_tone', 'N/A')}"
                )

            if "priority" in result:
                lines.append("## Editorial Decision")
                lines.append(f"- **Priority**: {result['priority']}")
                lines.append(f"- **Workflow Stage**: {result.get('stage', 'N/A')}")
                lines.append(f"- **Confidence**: {result.get('confidence', 0):.2f}")

                if "next_actions" in result and result["next_actions"]:
                    lines.append("- **Next Actions**:")
                    for action in result["next_actions"][:5]:
                        lines.append(f"  - {action}")

            if "brief" in result:
                lines.append("## Story Brief")
                lines.append(f"{result['brief']}")

            return "\n".join(lines)

        else:
            return f"Unsupported format: {format_type}"

    except Exception as e:
        return f"Formatting error: {e}"


# Export main functions
__all__ = [
    "assess_content_quality",
    "categorize_content",
    "analyze_editorial_sentiment",
    "generate_editorial_commentary",
    "make_editorial_decision",
    "request_story_brief",
    "publish_story",
    "review_evidence",
    "health_check",
    "validate_editorial_result",
    "format_editorial_output",
    "get_chief_editor_engine",
]
