#!/usr/bin/env python3
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import mysql.connector

OUT = Path(os.environ.get('EXPERIMENT_DIR', '.')).resolve()
TARGET_COUNT = int(os.environ.get('TARGET_CLUSTER_COUNT', '5'))

cfg = {
    'user': os.environ.get('MARIADB_USER', 'justnews'),
    'password': os.environ.get('MARIADB_PASSWORD', 'dev_justnews_password'),
    'host': os.environ.get('MARIADB_HOST', 'mariadb'),
    'port': int(os.environ.get('MARIADB_PORT', 3306)),
    'database': os.environ.get('MARIADB_DB', 'justnews'),
}

with mysql.connector.connect(**cfg) as conn:
    with conn.cursor(dictionary=True) as cur:
        cur.execute('''
            SELECT
              JSON_UNQUOTE(JSON_EXTRACT(input_cluster_ids, '$[0]')) AS cluster_id,
              COUNT(*) AS article_count,
              MAX(created_at) AS latest_created_at
            FROM articles
            WHERE input_cluster_ids IS NOT NULL
              AND input_cluster_ids != '[]'
              AND input_cluster_ids != ''
              AND content IS NOT NULL
              AND LENGTH(TRIM(content)) > 0
            GROUP BY cluster_id
            HAVING cluster_id IS NOT NULL
            ORDER BY latest_created_at DESC
            LIMIT 300
        ''')
        rows = cur.fetchall()

multi = [r for r in rows if int(r['article_count']) >= 2]
single = [r for r in rows if int(r['article_count']) == 1]
selected = multi[:TARGET_COUNT]
if len(selected) < TARGET_COUNT:
    selected.extend(single[: (TARGET_COUNT - len(selected))])
selected = selected[:TARGET_COUNT]

result = {
    'generated_at_utc': datetime.now(UTC).isoformat(),
    'target_count': TARGET_COUNT,
    'selected': selected,
}

(OUT / 'selected_clusters.json').write_text(json.dumps(result, indent=2, default=str))
print(f"Wrote {(OUT / 'selected_clusters.json')}")
print('Selected cluster_ids:', ', '.join([s['cluster_id'] for s in selected]))
