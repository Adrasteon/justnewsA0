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
# Explicitly exclude known bad clusters from prior run
REJECT_CLUSTERS = {'CL-49033fea', 'CL-a837c3ae', 'CL-de3798e2', 'CL-fe266d6b', 'CL-6749b83e', 'CL-d5c593e6'}

OVERLAY_PATTERNS = [
    r'cookie', r'consent', r'accept all', r'reject all', r'privacy settings',
    r'manage preferences', r'we value your privacy', r'gdpr', r'sign in', r'subscribe now'
]
CORRUPTION_PATTERNS = [
    r'\ufffd', r'\\x[0-9a-fA-F]{2}', r'ID3\s+#TSSE', r'javascript disabled',
    r'enable javascript', r'loading\.\.\.', r'\bnull\b'
]
SUMMARY_PAGE_PATTERNS = [
    r'\bfull story\b', r'\bread more\b', r'\blive updates\b', r'\btop stories\b',
    r'\blatest news\b', r'\bworld\s*-\s*international\b', r'\bcategory\b', r'\bsection\b'
]
SUMMARY_URL_PATTERNS = [
    r'/category/', r'/categories/', r'/tag/', r'/tags/', r'/section/', r'/topics?',
    r'/world/international\.aspx', r'/latest', r'/news/?$'
]

overlay_re = re.compile('|'.join(OVERLAY_PATTERNS), re.IGNORECASE)
corrupt_re = re.compile('|'.join(CORRUPTION_PATTERNS), re.IGNORECASE)
summary_re = re.compile('|'.join(SUMMARY_PAGE_PATTERNS), re.IGNORECASE)
summary_url_re = re.compile('|'.join(SUMMARY_URL_PATTERNS), re.IGNORECASE)

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
            LIMIT 600
        ''')
        clusters = cur.fetchall()

        selected = []
        diagnostics = []

        for cid in CONTROL_CLUSTERS:
            row = next((r for r in clusters if r['cluster_id'] == cid), None)
            if row:
                selected.append(row)

        for row in clusters:
            cid = row['cluster_id']
            if cid in REJECT_CLUSTERS or cid in CONTROL_CLUSTERS:
                continue

            cur.execute('''
                SELECT content, title, source_url
                FROM articles
                WHERE JSON_UNQUOTE(JSON_EXTRACT(input_cluster_ids, '$[0]')) = %s
                  AND content IS NOT NULL
                  AND LENGTH(TRIM(content)) > 0
                ORDER BY created_at ASC
                LIMIT 12
            ''', (cid,))
            arts = cur.fetchall()
            texts = [a.get('content') or '' for a in arts]
            titles = [a.get('title') or '' for a in arts]
            urls = [a.get('source_url') or '' for a in arts]

            joined = '\n'.join(texts)
            overlay_hits = len(overlay_re.findall(joined))
            corrupt_hits = len(corrupt_re.findall(joined))
            summary_hits = len(summary_re.findall(joined))
            summary_url_hits = sum(1 for u in urls if summary_url_re.search(u or ''))
            avg_len = (sum(len(t) for t in texts) / max(1, len(texts))) if texts else 0.0

            generic_titles = sum(1 for t in titles if re.search(r'^(world\s*-\s*international|latest|news|home)$', (t or '').strip(), re.I))
            short_articles = sum(1 for t in texts if len((t or '').split()) < 120)

            quality_score = 1.0
            quality_score -= min(0.6, overlay_hits * 0.05)
            quality_score -= min(0.8, corrupt_hits * 0.12)
            quality_score -= min(0.6, summary_hits * 0.08)
            quality_score -= min(0.5, summary_url_hits * 0.10)
            quality_score -= min(0.3, generic_titles * 0.08)
            quality_score -= min(0.4, short_articles * 0.06)
            if avg_len < 450:
                quality_score -= 0.25
            if avg_len > 12000:
                quality_score -= 0.15

            diagnostics.append({
                'cluster_id': cid,
                'article_count': int(row['article_count']),
                'latest_created_at': str(row['latest_created_at']),
                'overlay_hits': overlay_hits,
                'corrupt_hits': corrupt_hits,
                'summary_hits': summary_hits,
                'summary_url_hits': summary_url_hits,
                'generic_titles': generic_titles,
                'short_articles': short_articles,
                'avg_article_len': round(avg_len, 1),
                'quality_score': round(max(0.0, quality_score), 4),
            })

        candidates = [
            d for d in diagnostics
            if d['corrupt_hits'] == 0
            and d['overlay_hits'] <= 1
            and d['summary_hits'] <= 1
            and d['summary_url_hits'] == 0
            and d['short_articles'] <= 1
            and d['avg_article_len'] >= 500
            and d['quality_score'] >= 0.82
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
