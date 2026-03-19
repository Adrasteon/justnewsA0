#!/usr/bin/env python3
"""Reset runtime dev data while preserving sources.

This script clears pipeline runtime data (crawl/artifacts/articles/synthesis/publisher/embeddings)
without deleting rows from the sources table.

By default, it also resets sources.last_crawl_at to NULL.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from common.observability import get_logger
from database.utils.migrated_database_utils import create_database_service

logger = get_logger("reset_dev_data_preserve_sources")

# Ordered from children -> parents where relevant.
TARGET_TABLES = [
    "publisher_keywords",
    "publisher_articles",
    "crawler_task_articles",
    "crawler_crawl_results",
    "crawler_tasks",
    "crawler_jobs",
    "pending_articles_pool",
    "synthesizer_jobs",
    "synthesized_articles",
    "embeddings_document",
    "embeddings_collection",
    "articles",
]


@dataclass
class TableResetResult:
    table: str
    exists: bool
    affected_rows: int = 0


def _table_exists(cursor, table_name: str) -> bool:
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = DATABASE() AND table_name = %s
        LIMIT 1
        """,
        (table_name,),
    )
    return cursor.fetchone() is not None


def _clear_tables(cursor, table_names: list[str]) -> list[TableResetResult]:
    results: list[TableResetResult] = []
    for table_name in table_names:
        exists = _table_exists(cursor, table_name)
        if not exists:
            results.append(TableResetResult(table=table_name, exists=False, affected_rows=0))
            continue

        cursor.execute(f"DELETE FROM {table_name}")
        results.append(
            TableResetResult(table=table_name, exists=True, affected_rows=int(cursor.rowcount or 0))
        )
    return results


def _reset_sources_last_crawl_at(cursor) -> int:
    if not _table_exists(cursor, "sources"):
        return 0

    cursor.execute("UPDATE sources SET last_crawl_at = NULL WHERE last_crawl_at IS NOT NULL")
    return int(cursor.rowcount or 0)


def _reset_chroma_collection(service, dry_run: bool) -> tuple[bool, str]:
    client = getattr(service, "chroma_client", None)
    collection = getattr(service, "collection", None)
    if client is None or collection is None:
        return False, "Chroma client/collection unavailable; skipped Chroma reset."

    collection_name = getattr(collection, "name", None)
    if not collection_name:
        return False, "Chroma collection name unavailable; skipped Chroma reset."

    base_collection_name = str(getattr(service, "config", {}).get("database", {}).get("chromadb", {}).get("collection", "articles") or "articles").strip()
    if not base_collection_name:
        base_collection_name = "articles"

    scoped_collection_name = base_collection_name
    get_scoped = getattr(service, "get_scoped_collection_name", None)
    if callable(get_scoped):
        try:
            scoped_collection_name = str(get_scoped(base_collection_name) or base_collection_name)
        except Exception:
            scoped_collection_name = base_collection_name

    targets: list[str] = []
    for name in (base_collection_name, scoped_collection_name):
        if name and name not in targets:
            targets.append(name)

    if dry_run:
        return True, f"[dry-run] Would recreate Chroma collections {targets}."

    metadata = getattr(collection, "metadata", None) or {
        "description": "Article embeddings for semantic search"
    }

    existing = {c.name for c in client.list_collections()}
    for target in targets:
        if target in existing:
            client.delete_collection(name=target)
    recreated: list[str] = []
    for target in targets:
        client.create_collection(name=target, metadata=metadata)
        recreated.append(target)

    preferred = scoped_collection_name if scoped_collection_name in recreated else recreated[0]
    new_collection = client.get_collection(name=preferred)
    try:
        service.collection = new_collection
    except Exception:
        pass

    return True, f"Recreated Chroma collections {recreated}; active collection set to '{preferred}'."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Clear dev runtime data while preserving sources rows. "
            "sources.last_crawl_at is always reset to NULL."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed, then roll back MariaDB writes.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    service = create_database_service()
    conn = None
    cursor = None

    try:
        conn = service.get_connection()
        cursor = conn.cursor()

        print("== JustNews Dev Data Reset (Preserve Sources) ==")
        if args.dry_run:
            print("Mode: dry-run (MariaDB changes will be rolled back)")

        table_results = _clear_tables(cursor, TARGET_TABLES)
        sources_rows_reset = _reset_sources_last_crawl_at(cursor)

        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()

        print("\nMariaDB actions:")
        for result in table_results:
            if result.exists:
                print(f"- cleared {result.table}: {result.affected_rows} row(s)")
            else:
                print(f"- skipped {result.table}: table not present")
        print(f"- reset sources.last_crawl_at: {sources_rows_reset} row(s)")

        chroma_ok, chroma_message = _reset_chroma_collection(service, args.dry_run)
        print("\nChroma action:")
        print(f"- {chroma_message}")

        print("\nReset complete.")
        if not chroma_ok:
            print("Note: relational embedding tables were cleared, but Chroma reset was skipped.")
        return 0

    except Exception as exc:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        logger.exception("Reset failed: %s", exc)
        print(f"Reset failed: {exc}")
        return 1
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
