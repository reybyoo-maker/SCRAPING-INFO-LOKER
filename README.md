# INFO LOKER Indonesia — website and automated collector

INFO LOKER is a static job-search website backed by a daily/hourly collector. It gathers public RSS/API metadata, normalizes job records, deduplicates records, keeps source links, and publishes `data/jobs.json` plus `index.html`.

## Current collection sources

These sources are enabled in the current default configuration:
- Google News RSS search for Indonesian vacancy/recruitment terms, rotated across provinces and cities. The collector stores source links and metadata; it does not crawl every linked article.
- Jobicy public jobs API.
- Remote OK public jobs API.

Latest source health and run counts are recorded in `data/run_status.json`. A previous run's record count is not the same as the number of new jobs discovered by that run.

Optional sources:
- Jooble is skipped unless `JOOBLE_API_KEY` is configured.
- Adzuna is skipped unless both credentials are configured and the account/API supports Indonesia.
- Additional public employer RSS/Atom feeds can be added to `config/approved_feeds.json`, only when their feed terms and permissions allow aggregation.
- Remotive is disabled because redistribution to third-party job boards is restricted by its API terms.
- Himalayas is disabled in the public GitHub data pipeline. It must be integrated only in a way that follows the provider's attribution, original application-link, expiry, and no-redistribution requirements.

## Multi-source adapter framework

The repository includes 11 separate adapter modules under `scrapers/`:
`jobstreet`, `indeed`, `glints`, `kalibrr`, `karir`, `dealls`, `linkedin`, `lokerid`, `disnakerja`, `techinasia`, and `maganghub`.

They inherit from `scrapers/base.py` and share the normalized schema:
`id`, `title`, `company`, `location`, `source`, `url`, `posted_at`, `salary`, `job_type`, `description_snippet`, and `scraped_at`.
Compatibility aliases are retained for the existing website, so the adapter framework does not discard existing fields.

**These 11 site-specific adapters are present but disabled by default.** In `config.yaml`, each adapter requires both `enabled: true` and `authorized: true`. The adapter then checks the source's `robots.txt`, uses HTTPS on the declared source domain, uses a descriptive User-Agent, spaces requests by 2–5 seconds, times out after 30 seconds, and retries transient errors at most three attempts. A disabled or failing adapter does not block the other sources.

Do not enable an adapter without verifying the site's current terms and obtaining permission where required. JobStreet prohibits automated data gathering without prior written consent; Glints also prohibits screen scraping without prior written consent; LinkedIn prohibits unauthorized scraping and bypassing access controls:
- https://id.jobstreet.com/id/terms
- https://glints.com/about/terms
- https://www.linkedin.com/legal/user-agreement

There is deliberately **no stealth browser, fake-user-agent rotation, private/internal endpoint probing, login automation, or anti-bot bypass**. JavaScript-heavy pages may return no records through ordinary public HTML; use an authorized API/partner feed instead.

## Architecture

- `scraper/main.py` remains the active public RSS/API collector.
- `scripts/run_all.py` runs the existing collector, optionally runs enabled and authorized adapters using at most four workers, normalizes the unified schema, deduplicates, writes a daily backup, updates the run status, and renders `templates/index.html.j2` to `index.html`.
- `data/jobs.json` is the website dataset. The wrapper metadata includes `generated_at`, `timezone`, `total`, and `jobs`.
- `data/run_status.json` records source outcomes and orchestration status.
- `index.html` is a static frontend. It reads the local static JSON asset and contains keyword search, source/location/job filters, sorting, pagination, saved jobs, and a details dialog.
- `config.yaml` controls the 11 optional HTML adapters and rotation settings. Existing public RSS/API source settings remain in the original collector and `config/source_registry.json`.

## Automatic workflows

- `.github/workflows/scrape.yml`: schedule `0 * * * *` (hourly) plus manual trigger. It installs pinned dependencies, runs `python scripts/run_all.py`, and commits changed dataset/status/website/daily-backup files.
- `.github/workflows/deploy.yml`: deploys the validated static bundle to GitHub Pages after successful scraper completion, after relevant direct pushes, or manually.
- `.github/workflows/healthcheck.yml`: runs every six hours and manually. It checks JSON validity, at least 100 records, and that the newest `scraped_at` is less than three hours old. A failed check creates an issue labeled `scraper-broken`; if one is already open, it adds a comment instead of flooding duplicate issues.

GitHub Actions scheduled jobs are best-effort, not a real-time service-level guarantee. The repository must have Actions enabled and workflow permissions configured. Scheduled workflows in public repositories can be paused by GitHub after prolonged repository inactivity; review the Actions tab periodically.

## First-time setup

1. In repository Settings → Actions → General, enable Actions and allow workflows to write repository contents.
2. In Settings → Pages, choose **GitHub Actions** as the build/deploy source if it has not already been selected.
3. Open Actions → **INFO LOKER Hourly Scraping** → Run workflow once to test the collection and deploy flow.
4. Open Actions → **INFO LOKER Health Check** → Run workflow once to test the alert path/data freshness.
5. For Jooble or Adzuna, add the required provider credentials under Settings → Secrets and variables → Actions. Never store API keys in tracked files.
6. For an HTML adapter, verify permission/terms first; then set that source's `enabled` and `authorized` values to `true` in `config.yaml`. If `robots.txt` disallows its URL, the adapter will skip it.

## Local run

Python 3.12+:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/run_all.py
python scripts/healthcheck.py
python3 -m http.server 8000
```

Then open `http://localhost:8000`. Keep the terminal process running during testing. Open the page through the local server rather than double-clicking `index.html`, because browsers may block local JSON fetches.

## Adding an authorized RSS feed

Edit `config/approved_feeds.json` and append a feed object supported by the current collector, following the existing parser's fields and respecting the feed's terms. Store source names and original outbound links, avoid copying full protected descriptions, and never add private or login-required feeds.

## Troubleshooting

- Check Actions → the latest **INFO LOKER Hourly Scraping** run for HTTP/source errors.
- Inspect `data/run_status.json` for per-source counts and skip reasons.
- `JOOBLE_API_KEY not configured` or `Adzuna credentials not configured` means that optional connector is not active.
- A disabled adapter is intentional; it will not send a request until both required flags are explicitly enabled.
- A `robots.txt blocks` message means the adapter must be skipped or switched to an authorized API/feed.
- If the health-check alert says data is stale, inspect the hourly scrape run and Pages deployment rather than assuming that previously stored records are newly found jobs.
