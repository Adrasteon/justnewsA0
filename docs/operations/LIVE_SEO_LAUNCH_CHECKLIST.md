# Live SEO Launch Checklist

**Purpose**: Keep high-impact crawl and ranking actions visible at go-live time.

**When to use**: Immediately before DNS cutover, at launch, and through the first 14 days after launch.

---

## 1) Pre-Go-Live (Blockers)

- [ ] **Set production canonical host policy** (single preferred host, e.g. `https://www.example.com`)
- [ ] **Verify robots on production domain**: `https://<domain>/robots.txt`
  - Must include:
    - `Sitemap: https://<domain>/sitemap.xml`
    - `Sitemap: https://<domain>/sitemap-static.xml`
    - `Feed: https://<domain>/feed.xml`
- [ ] **Verify sitemap index and children on production domain**:
  - `https://<domain>/sitemap.xml`
  - `https://<domain>/sitemap-static.xml`
  - `https://<domain>/sitemap-articles-1.xml`
- [ ] **Verify RSS feed**: `https://<domain>/feed.xml`
- [ ] **Ensure all key page types return indexable metadata exactly once**:
  - Home, archive, category, article pages
  - One canonical, one meta description, one OG set, one Twitter set

---

## 2) Launch-Day Actions (High Impact)

- [ ] **Google Search Console**
  - Add/verify domain property
  - Submit `https://<domain>/sitemap.xml`
  - Use URL Inspection to request indexing for:
    - Home page
    - 2-3 top category pages
    - 5-10 highest-value article pages
- [ ] **Bing Webmaster Tools**
  - Add/verify site
  - Submit `https://<domain>/sitemap.xml`
  - Request crawl for home + key sections
- [ ] **Recrawl trigger after first major publish burst**
  - Re-request indexing for homepage + newest major article URLs

---

## 3) First 72 Hours (Crawl Frequency)

- [ ] Publish steadily (fresh URLs help bots increase revisit cadence)
- [ ] Keep homepage and top sections visibly updated with latest content
- [ ] Confirm newest stories appear in:
  - `sitemap-articles-1.xml`
  - `feed.xml`
- [ ] Check server logs for bot activity:
  - `Googlebot`, `Bingbot`, `Google-InspectionTool`
- [ ] Resolve any accidental `noindex`/canonical mistakes immediately

---

## 4) First 14 Days (Ranking Readiness)

- [ ] Monitor Search Console:
  - Index coverage
  - Crawled vs discovered URLs
  - Any canonical selection conflicts
- [ ] Monitor Bing indexing status and crawl stats
- [ ] Fix soft-404/thin pages (especially short/empty summaries)
- [ ] Maintain strong internal links:
  - Home → category → article
  - Related coverage links on article pages
- [ ] Keep article metadata complete:
  - non-empty description
  - NewsArticle JSON-LD present

---

## 5) Smoke Commands (Production)

```bash
# Robots
curl -sS https://<domain>/robots.txt

# Sitemap index + child samples
curl -sS https://<domain>/sitemap.xml | head -n 40
curl -sS https://<domain>/sitemap-static.xml | head -n 40
curl -sS https://<domain>/sitemap-articles-1.xml | head -n 40

# Feed
curl -sS https://<domain>/feed.xml | head -n 40
```

---

## 6) Current JustNews SEO Endpoints

- `/robots.txt`
- `/sitemap.xml` (sitemap index)
- `/sitemap-static.xml`
- `/sitemap-articles-<page>.xml`
- `/feed.xml`

If these endpoints are healthy on the production domain and submitted in Google/Bing tools, crawl discovery and revisit frequency are materially improved.
