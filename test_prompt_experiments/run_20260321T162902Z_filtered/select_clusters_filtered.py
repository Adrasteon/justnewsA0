#!/usr/bin/env python3
import os
import re
import json
from datetime import datetime, timezone
from pathlib import Path
import mysql.connector

OUT = Path(os.environ.get('EXPERIMENT_DIR', '.')).resolve()
TARGET_COUNT = int(os.environ.get('TARGET_CLUSTER_COUNT', '5'))
CONTROL_CLUSTERS = ['CL-e2dae2b2', 'CL-c3ceed21']
REJECT_CLUSTERS = {'CL-49033fea', 'CL-a837c3ae', 'CL-de3798e2'}

OVERLAY_PATTERNS = [
    r'cookie', r'consent', r'accept all', r'reject all', r'privacy settings',
    r'subscribe now', r'sign in', r'allow all', r'manage preferences', r'gdpr',
    r'we value your privacy', r'continue without accepting', r'ad blocker'
]
CORRUPTION_PATTERNS = [
    r'\ufffd', r'\\x[0-9a-fA-F]{2}', r'\bnull\b', r'lorem ipsum', r'click here',
    r'javascript disabled', r'enable javascript', r'loading\.\.\.', r'404', r'forbidden'
]

overlay_re = re.compile('|'.join(OVERLAY_PATTERNS), re.IGNORECASE)
corrupt_re = re.compile('|'.join(CORRUPTION_PATTERNS), re.IGNORECASE)

cfg = {
    'user': os.environ.get('MARIADB_USER', 'justnews'),
    'password': os.environ.get('MARIADB_PASSWORD', 'dev_justnews_password'),
    'host': os.environ.get('MARIADB_HOST', 'mariadb'),
    'port': int(os.environ.get('MARIADB_PORT', 3306)),
    'database': os.environ.get('MARIADB_DB', 'justnews'),
}

def clean_ratio(text: str) -> float:
    if not text:
        return 0.0
    bad = len(overlay_re.findall(text)) + len(corrupt_re.findall(text))
    length_factor = max(1, len(text) // 600)
    return max(0.0, 1.0 - (bad / (8.0 * length_factor)))

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
            LIMIT 400
        ''')
        clusters = cur.fetchall()

        selected = []
        diagnostics = []

        # Add controls first (if still present)
        for cid in CONTROL_CLUSTERS:
            row = next((r for r in clusters if r['cluster_id'] == cid), None)
            if row:
                selected.append(row)

        # Score candidates and pick 3 replacements
        for row in clusters:
            cid = row['cluster_id']
            if cid in REJECT_CLUSTERS or cid in CONTROL_CLUSTERS:
                continue

            cur.execute('''
                SELECT content
                FROM articles
                WHERE JSON_UNQUOTE(JSON_EXTRACT(input_cluster_ids, '$[0]')) = %s
                  AND content IS NOT NULL
                  AND LENGTH(TRIM(content)) > 0
                ORDER BY created_at ASC
                LIMIT 12
            ''', (cid,))
            texts = [r['content'] or '' for r in cur.fetchall()]
            joined = '\n'.join(texts)

            overlay_hits = len(overlay_re.findall(joined))
            corrupt_hits = len(corrupt_re.findall(joined))
            avg_len = sum(len(t) for t in texts) / max(1, len(texts))
            quality = clean_ratio(joined)

            diagnostics.append({
                'cluster_id': cid,
                'article_count': int(row['article_count']),
                'latest_created_at': str(row['latest_created_at']),
                'overlay_hits': overlay_hits,
                'corrupt_hits': corrupt_hits,
                'avg_article_len': round(avg_len, 1),
                'quality_score': round(quality, 4),
            })

        candidates = [
            d for d in diagnostics
            if d['overlay_hits'] <= 1 and d['corrupt_hits'] == 0 and d['avg_article_len'] >= 450 and d['quality_score'] >= 0.78
        ]
        candidates.sort(key=lambda d: (d['quality_score'], d['article_count']), reverse=True)

        needed = TARGET_COUNT - len(selected)
        for d in candidates:
            if needed <= 0:
                break
            row = next((r for r in clusters if r['cluster_id'] == d['cluster_id']), None)
            if row:
                selected.append(row)
                needed -= 1

result = {
    'generated_at_utc': datetime.now(timezone.utc).isoformat(),
    'target_count': TARGET_COUNT,
    'control_clusters': CONTROL_CLUSTERS,
    'excluded_clusters': sorted(list(REJECT_CLUSTERS)),
    'selected': selected[:TARGET_COUNT],
}
(OUT / 'selected_clusters.json').write_text(json.dumps(result, indent=2, default=str))
(OUT / 'selection_diagnostics.json').write_text(json.dumps(diagnostics, indent=2, default=str))

print(f"Wrote {(OUT / 'selected_clusters.json')}")
print('Selected cluster_ids:', ', '.join([s['cluster_id'] for s in result['selected']]))
