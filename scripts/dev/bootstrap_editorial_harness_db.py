#!/usr/bin/env python3
"""Create the minimal articles schema and seed a sample row for the editorial harness."""

from __future__ import annotations

import json
import os
import textwrap
from datetime import UTC, datetime

import mysql.connector

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS articles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    url TEXT,
    title TEXT,
    content LONGTEXT,
    summary LONGTEXT,
    metadata JSON,
    structured_metadata JSON,
    authors JSON,
    publication_date DATETIME NULL,
    needs_review TINYINT(1) DEFAULT 0,
    fact_check_status VARCHAR(64) DEFAULT NULL,
    fact_check_trace JSON,
    critic_result JSON,
    synth_trace JSON,
    is_synthesized TINYINT(1) DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;
"""

INSERT_SQL = """
INSERT INTO articles (
    url,
    title,
    content,
    summary,
    metadata,
    structured_metadata,
    authors,
    publication_date,
    needs_review,
    fact_check_status,
    is_synthesized
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, NULL, 0);
"""


def build_connection() -> mysql.connector.MySQLConnection:
    host = os.environ.get("MARIADB_HOST", "127.0.0.1")
    port = int(os.environ.get("MARIADB_PORT", "3306"))
    user = os.environ.get("MARIADB_USER", "root")
    password = os.environ.get("MARIADB_PASSWORD", "")
    database = (
        os.environ.get("MARIADB_DB") or os.environ.get("MARIADB_DATABASE") or "justnews"
    )
    return mysql.connector.connect(
        host=host, port=port, user=user, password=password, database=database
    )


def ensure_schema(conn) -> None:
    cursor = conn.cursor()
    try:
        cursor.execute(SCHEMA_SQL)
        conn.commit()
    finally:
        cursor.close()


def seed_sample_row(conn) -> None:
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM articles LIMIT 1")
        if cursor.fetchone():
            return

        content = textwrap.dedent(
            """
            The JustNews investigation team confirmed that the city council approved a comprehensive clean-energy ordinance
            after months of public comment, setting aside $120 million for neighborhood retrofits. The measure requires
            utilities to submit quarterly transparency reports and triggers a citizen oversight panel whenever outages exceed
            90 minutes. Analysts expect the policy to accelerate private investment in the regional grid while watchdogs warn
            that enforcement will hinge on timely publication of the promised data portals.
            """
        ).strip()
        summary = "Council passes clean-energy package with funding for neighborhood retrofits and new oversight triggers."
        metadata = {
            "url": "https://example.com/local/clean-energy-ordinance",
            "canonical_url": "https://example.com/local/clean-energy-ordinance",
            "language": "en",
        }
        structured = {
            "title": "City approves clean-energy overhaul",
            "section": "Local",
        }
        authors = ["JustNews Desk"]
        cursor.execute(
            INSERT_SQL,
            (
                metadata["url"],
                "City approves clean-energy overhaul",
                content,
                summary,
                json.dumps(metadata),
                json.dumps(structured),
                json.dumps(authors),
                datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        conn.commit()
    finally:
        cursor.close()


def main() -> None:
    conn = build_connection()
    try:
        ensure_schema(conn)
        seed_sample_row(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
