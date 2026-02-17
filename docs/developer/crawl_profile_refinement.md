# Crawl Profile Refinement Playbook

This guide explains the repeatable workflow we use to tune Crawl4AI profiles for high-volume news domains such as BBC.
Follow the same sequence when onboarding a new site, revalidating an existing profile, or reacting to structural changes
on the publisher site.

## 1. Environment Checklist

- Activate the project environment: `conda run -n ${CANONICAL_ENV:-justnews-py312} ...` or use the preconfigured tasks
  in the repo.

- Ensure Playwright browsers are installed for the environment (`playwright install chromium`).

- Confirm the target domain has a profile file under `config/crawl_profiles/`and that you understand any
  custom`extra`flags already applied (e.g.,`skip_seed_articles`).

## 2. Quick Variant Probe

1. Load the current crawl profile and exercise the standard variants:

```bash PYTHONPATH=. conda run -n ${CANONICAL_ENV:-justnews-py312} python
scripts/dev/crawl4ai_profile_variants_probe.py \ --domain bbc.co.uk \ --max-
articles 30 ```

1. Inspect the JSON summary for each variant:

   - `link_preview_only` is the most sensitive to include/exclude patterns and generally surfaces slugs for article pages.

   - `adaptive_default` and `adaptive_deep` show how the existing thresholds behave when traversal is enabled.

1. Capture the CLI output in a scratch pad or ticket so you can compare later runs after making YAML adjustments.

## 3. Link Discovery Tuning

- **Include patterns**: Target canonical article URL structures (`/news/articles/`, `/news/world-…`, etc.). Add new patterns when you encounter valid articles that were filtered out. Use conservative substrings to avoid broad matches.

- **Exclude patterns**: Block live blogs, video hubs, topic indexes, and account flows that pollute the queue (`/news/live/`, `/news/av/`, `/sport/`, etc.).

- **Max link budget**: Start high (200) to see what the crawler can discover, then reduce if Playwright stability suffers or you need to throttle requests.

- **Concurrency**: Drop to `1-2` when the browser crashes with `BrowserContext.new_page`. Raise only after stability is confirmed.

## 4. Seed Handling

- Enable `extra.skip_seed_articles` when the landing pages are not true articles. This buffers seed fetches until the crawler gathers enough downstream articles, keeping the final dataset article-heavy.

- Track how many seeds still leak through by counting URLs without `/news/` (or the site’s article marker). Update include/exclude rules to close the gap.

## 5. Validation Loop

1. Re-run the probe (or the targeted inline script) with the revised YAML.

1. Check for:

   - **Article count**: Goal ≥50 distinct article URLs for BBC.

   - **Uniqueness**: Compare total vs. unique URL counts.

   - **Quality**: Spot-check titles to ensure they are full articles, not section fronts.

   - **Crawler health**: Watch for Playwright `Connection closed` errors. If they persist, back off concurrency or max links before continuing.

1. Repeat small edits + verification until the metrics stabilize.

## 6. Scheduled Crawl Smoke Test

- Use the scheduler with the updated profile to mimic production:

```bash set -a && source global.env && set +a conda run -n
${CANONICAL_ENV:-justnews-py312} python scripts/ops/run_crawl_schedule.py \ --schedule /tmp/crawl_schedule_bbc.yaml \
--testrun --no-wait --timeout 2400
```

- Review logs for section coverage, dedupe behaviour, and extractor output quality.

## 7. Recording Changes

- Document the rationale for each YAML adjustment in the PR description and/or `refactor_progress.md`.

- When major filters change, add a short entry in `CHANGELOG.md` so downstream teams know to expect different article mixes.

## 8. Ongoing Maintenance Cadence

- **BBC**: Re-run the probe monthly or after major site redesigns (navigation facelift, URL pattern shifts, live blog surge).

- **New Sites**: Follow this playbook during onboarding, then schedule quarterly validations.

- **Regression Watch**: Set alerts on repeated Playwright crashes or sudden drops in harvested articles; rerun the probe when triggered.

## 9. Validation Snapshots

- **2025-11-01**: `link_preview_only`probe with`max_articles=100`harvested 100 unique URLs (98 article details, 2 seed landings). Domain split favoured`www.bbc.co.uk`(76) over`www.bbc.com`(24). Run log and full URL list live in`docs/developer/crawl_profile_tuning_log.md`.

- **2025-11-01**: Follow-up probe after enabling `strict_skip_seed_articles`, reducing link-preview concurrency to 1 (max links 120), and adding per-request crawler retries. Harvested 98 unique article URLs with zero seed leakage; Playwright remained stable after the change.

By standardising these steps we can quickly adapt the crawler as publishers evolve, minimise manual triage, and keep
article output consistent across domains.
