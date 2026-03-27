#!/usr/bin/env python3
import json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path

import mysql.connector
import requests

ROOT = Path(os.environ.get('EXPERIMENT_DIR', '.')).resolve()
selected_path = ROOT / 'selected_clusters.json'
if not selected_path.exists():
    raise SystemExit(f'Missing {selected_path}. Run select_clusters_filtered.py first.')

selected = json.loads(selected_path.read_text())
clusters = selected.get('selected') or []
if not clusters:
    raise SystemExit('No clusters selected')

model = os.environ.get('VLLM_MODEL', 'Qwen/Qwen2.5-14B-Instruct-AWQ')
base_url = os.environ.get('VLLM_BASE_URL', 'http://vllm:8010/v1').rstrip('/')
api_key = os.environ.get('VLLM_API_KEY', 'unused')
chat_url = f'{base_url}/chat/completions'

variants = [
    {
        'name': 'baseline_t03',
        'temperature': 0.3,
        'system': (
            'You are the JustNews synthesis lead. Given multiple article snippets, '
            'produce JSON with body (full neutral synthesis), summary (2 sentence abstract), '
            'narrative_voice, key_points (list), cautions (list), '
            'and pull_quotes (list). Emphasize factual consistency and note any gaps. '
            'The body must be substantially longer than the summary (target 220-450 words).'
        ),
        'mode': 'baseline',
    },
    {
        'name': 'strict_t02',
        'temperature': 0.2,
        'system': (
            'You are a neutral news synthesis editor. '
            'Use only facts in provided snippets. '
            'If snippets conflict, report conflict explicitly and do not guess. '
            'If evidence is insufficient, state insufficient evidence. '
            'Do not invent names, numbers, quotes, dates, or locations. '
            'Output valid JSON only with keys: title, summary, body, key_points, conflicts, cautions, source_attribution.'
        ),
        'mode': 'strict',
    },
    {
        'name': 'strict_t01',
        'temperature': 0.1,
        'system': (
            'You are a neutral news synthesis editor. '
            'Use only facts in provided snippets. '
            'If snippets conflict, report conflict explicitly and do not guess. '
            'If evidence is insufficient, state insufficient evidence. '
            'Do not invent names, numbers, quotes, dates, or locations. '
            'Output valid JSON only with keys: title, summary, body, key_points, conflicts, cautions, source_attribution.'
        ),
        'mode': 'strict',
    },
]

headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
cfg = {
    'user': os.environ.get('MARIADB_USER', 'justnews'),
    'password': os.environ.get('MARIADB_PASSWORD', 'dev_justnews_password'),
    'host': os.environ.get('MARIADB_HOST', 'mariadb'),
    'port': int(os.environ.get('MARIADB_PORT', 3306)),
    'database': os.environ.get('MARIADB_DB', 'justnews'),
}

run_manifest = {
    'run_generated_at_utc': datetime.now(UTC).isoformat(),
    'model': model,
    'base_url': base_url,
    'chat_url': chat_url,
    'clusters': clusters,
    'variants': [{'name': v['name'], 'temperature': v['temperature']} for v in variants],
}
(ROOT / 'manifest.json').write_text(json.dumps(run_manifest, indent=2, default=str))

with mysql.connector.connect(**cfg) as conn:
    with conn.cursor(dictionary=True) as cur:
        for c in clusters:
            cid = c['cluster_id']
            cdir = ROOT / 'clusters' / cid
            cdir.mkdir(parents=True, exist_ok=True)

            cur.execute('''
                SELECT id, title, source_url, created_at, content
                FROM articles
                WHERE JSON_UNQUOTE(JSON_EXTRACT(input_cluster_ids, '$[0]')) = %s
                  AND content IS NOT NULL
                  AND LENGTH(TRIM(content)) > 0
                ORDER BY created_at ASC
                LIMIT 20
            ''', (cid,))
            articles = cur.fetchall()

            input_blob = {
                'cluster_id': cid,
                'article_count': len(articles),
                'articles': [
                    {
                        'id': a.get('id'),
                        'title': a.get('title'),
                        'url': a.get('source_url'),
                        'created_at': str(a.get('created_at')),
                        'content': a.get('content') or '',
                    }
                    for a in articles
                ],
            }
            (cdir / 'cluster_input.json').write_text(json.dumps(input_blob, indent=2, ensure_ascii=False))

            snippets = [re.sub(r'\s+', ' ', (a.get('content') or '').strip())[:2800] for a in articles]
            joined = '\n---\n'.join(snippets)

            for v in variants:
                if v['mode'] == 'baseline':
                    user_prompt = f"Context: cluster\nArticles:\n'''{joined}'''\n\nReturn valid JSON."
                else:
                    lines = ['Context: cluster', 'You are given indexed sources. Use source indices in source_attribution.', 'SOURCES:']
                    lines.extend([f'[{i}] {s}' for i, s in enumerate(snippets)])
                    lines.extend(['Focus on confirmed facts, conflicts, and uncertainties.', 'Return valid JSON only.'])
                    user_prompt = '\n'.join(lines)

                payload = {
                    'model': model,
                    'temperature': v['temperature'],
                    'max_tokens': 1400,
                    'messages': [{'role': 'system', 'content': v['system']}, {'role': 'user', 'content': user_prompt}],
                }

                t0 = time.time()
                req_error = None
                response_blob = None
                model_text = ''
                parsed_json = None
                try:
                    resp = requests.post(chat_url, headers=headers, json=payload, timeout=240)
                    ct = (resp.headers.get('content-type') or '').lower()
                    body = resp.json() if 'application/json' in ct else resp.text
                    response_blob = {'status_code': resp.status_code, 'body': body}
                    if isinstance(body, dict):
                        choices = body.get('choices') or []
                        if choices:
                            model_text = (((choices[0] or {}).get('message') or {}).get('content') or '').strip()
                except Exception as exc:
                    req_error = str(exc)

                clean = model_text.replace('```json', '').replace('```', '').strip()
                if clean:
                    try:
                        parsed_json = json.loads(clean)
                    except Exception:
                        parsed_json = None

                artifact = {
                    'cluster_id': cid,
                    'variant': v['name'],
                    'temperature': v['temperature'],
                    'elapsed_seconds': round(time.time() - t0, 3),
                    'request_error': req_error,
                    'request_payload': payload,
                    'response': response_blob,
                    'model_text': model_text,
                    'parsed_json': parsed_json,
                }
                (cdir / f"{v['name']}.json").write_text(json.dumps(artifact, indent=2, ensure_ascii=False))

                if isinstance(parsed_json, dict):
                    title = str(parsed_json.get('title') or '').strip()
                    summary = str(parsed_json.get('summary') or '').strip()
                    body_txt = str(parsed_json.get('body') or '').strip()
                    md = f"# {title or '[no title]'}\n\n## Summary\n{summary or '[no summary]'}\n\n## Body\n{body_txt or '[no body]'}\n"
                else:
                    md = model_text or '[no model text]'
                (cdir / f"{v['name']}.article.md").write_text(md)

(ROOT / 'README.md').write_text(
    '# Prompt Experiment (Filtered v2)\n\n'
    'Scripts:\n'
    '- select_clusters_filtered.py\n'
    '- run_inference_variants.py\n\n'
    'Rerun:\n'
    f'1. cd {ROOT}\n'
    '2. /app/.venv/bin/python select_clusters_filtered.py\n'
    '3. VLLM_BASE_URL=http://vllm:8010/v1 /app/.venv/bin/python run_inference_variants.py\n'
)
print(f'Completed experiment in: {ROOT}')
