"""Run the existing public-source collector plus explicitly authorized HTML adapters."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import signal
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT / "data"
JOBS_FILE = DATA_DIR / "jobs.json"
STATUS_FILE = DATA_DIR / "run_status.json"
CONFIG_FILE = ROOT / "config.yaml"
TEMPLATE_DIR = ROOT / "templates"
SITE_TEMPLATE = "index.html.j2"
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "run.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("info-loker.orchestrator")

UTC = timezone.utc
WIB = timezone(timedelta(hours=7))
STOP_REQUESTED = False


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_json(path: Path, default):
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    tmp.replace(path)


def signal_handler(signum, _frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True
    log.warning("Shutdown requested by signal %s; stopping new work", signum)
    raise KeyboardInterrupt(f"Received signal {signum}")


def slugify(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "_", (value or "").lower()).strip("_")
    return result or "unknown"


def parse_iso(value):
    if not value:
        return None
    try:
        from dateutil import parser as date_parser
        if isinstance(value, (float, int)):
            parsed = datetime.fromtimestamp(value, UTC)
        else:
            parsed = date_parser.parse(str(value), fuzzy=True)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def canonical_job_type(value):
    text = str(value or "").lower().replace("-", " ").replace("_", " ")
    if any(x in text for x in ("intern", "internship", "magang", "apprentice")):
        return "intern"
    if any(x in text for x in ("freelance", "freelancer")):
        return "freelance"
    if any(x in text for x in ("part time", "parttime", "paruh waktu")):
        return "parttime"
    if any(x in text for x in ("contract", "kontrak", "temporary", "temporer")):
        return "contract"
    if any(x in text for x in ("full time", "fulltime", "penuh waktu", "permanent", "tetap")):
        return "fulltime"
    return None


def normalize_record(original: dict, source_hint: str = "unknown") -> dict | None:
    """Add the required common schema and keep aliases used by the current website."""
    row = dict(original)
    title = str(row.get("title") or row.get("position") or "").strip()
    url = str(row.get("url") or row.get("listing_url") or row.get("source_url") or "").strip()
    if not title or not url:
        return None

    company = str(row.get("company") or row.get("company_name") or row.get("employer") or "").strip()
    location = str(row.get("location") or row.get("location_label") or "").strip()
    if not location:
        location = ", ".join(str(value).strip() for value in (row.get("city"), row.get("province")) if value and str(value).strip())

    source_name = str(row.get("source_name") or row.get("source") or source_hint or "unknown").strip()
    old_source = str(row.get("source") or "")
    source_aliases = {
        "Google News RSS": "google_news_rss",
        "Google News RSS search": "google_news_rss",
        "Jobicy API": "jobicy",
        "Jobicy public jobs API": "jobicy",
        "Remote OK API": "remoteok",
        "Remote OK public jobs API": "remoteok",
        "Approved RSS": "approved_rss",
        "Himalayas API": "himalayas",
        "Jobicy": "jobicy",
        "Remote OK": "remoteok",
    }
    if old_source.startswith("company:"):
        # Preserve the explicitly namespaced source identity for official career pages.
        source = old_source
    else:
        source = source_aliases.get(source_name, source_aliases.get(old_source, slugify(old_source or source_name)))
    posted = parse_iso(row.get("posted_at") or row.get("source_updated_at") or row.get("published_at") or row.get("source_date"))
    raw_salary = row.get("salary") if row.get("salary") not in (None, "") else row.get("salary_text")
    salary = str(raw_salary).strip() if raw_salary not in (None, "") else None
    raw_kind = row.get("job_type") or row.get("employment_type") or row.get("job_type_source")
    kind = canonical_job_type(raw_kind)
    description = str(row.get("description_snippet") or row.get("description_excerpt") or row.get("description") or "")
    description = " ".join(description.split())[:300].rstrip()
    scraped = parse_iso(row.get("scraped_at") or row.get("last_seen_at") or row.get("last_checked_at") or row.get("first_seen_at")) or utc_now()

    identity = hashlib.sha256((url + title + company).encode("utf-8")).hexdigest()[:16]
    prior_id = row.get("id")
    row.update({
        "id": identity,
        "title": title,
        "company": company,
        "location": location,
        "source": source,
        "url": url,
        "posted_at": posted,
        "salary": salary,
        "job_type": kind,
        "description_snippet": description,
        "scraped_at": scraped,
        # Stable key used by the original collector to merge hourly refreshes.
        "collector_id": row.get("collector_id") or prior_id or identity,
        # Compatibility aliases consumed by the existing INFO LOKER website and collector.
        "source_name": source_name,
        "listing_url": url,
        "application_url": row.get("application_url") or url,
        "company_name": company or None,
        "location_label": location or None,
        "salary_text": salary,
        "employment_type": raw_kind,
        "description_excerpt": description,
        "last_seen_at": scraped,
    })
    if prior_id and prior_id != identity:
        row["legacy_id"] = row.get("legacy_id") or prior_id
    return row


def deduplicate(records: list[dict]) -> list[dict]:
    merged = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        normalized = normalize_record(record)
        if not normalized:
            continue
        key = normalized["id"]
        old = merged.get(key)
        if not old:
            merged[key] = normalized
            continue
        combined = dict(old)
        for field, value in normalized.items():
            if value not in (None, "", []):
                combined[field] = value
        # Keep the earliest first-seen timestamp and the stable legacy collector key.
        combined["first_seen_at"] = old.get("first_seen_at") or normalized.get("first_seen_at")
        combined["collector_id"] = old.get("collector_id") or normalized.get("collector_id") or key
        merged[key] = combined
    output = list(merged.values())
    output.sort(key=lambda item: (item.get("posted_at") is not None, item.get("posted_at") or "", item.get("scraped_at") or ""), reverse=True)
    return output


def collect_authorized_sources(config: dict) -> tuple[list[dict], dict]:
    from scrapers import SCRAPER_CLASSES, SourceNotAllowed

    location_data = read_json(ROOT / "config" / "locations.json", {"regions": [], "cities": []})
    locations = ["Indonesia"]
    for item in location_data.get("regions", []):
        value = item.get("query") or item.get("province")
        if value and value not in locations:
            locations.append(value)
    for item in location_data.get("cities", []):
        value = item.get("query") or item.get("city")
        if value and value not in locations:
            locations.append(value)

    keywords = config.get("keywords") or ["lowongan kerja"]
    if not isinstance(keywords, list) or not keywords:
        keywords = ["lowongan kerja"]
    source_config = config.get("sources") or {}
    hour_slot = int(time.time() // 3600)
    tasks = []
    statuses = {}

    for index, scraper_cls in enumerate(SCRAPER_CLASSES):
        source_id = scraper_cls.source_id
        settings = source_config.get(source_id, {})
        if settings.get("enabled") is not True:
            statuses[source_id] = {"status": "skipped", "reason": "disabled in config.yaml"}
            continue
        if settings.get("authorized") is not True:
            statuses[source_id] = {"status": "skipped", "reason": "authorized is not true"}
            continue
        keyword = str(keywords[(hour_slot + index) % len(keywords)])
        location = str(locations[(hour_slot * 7 + index * 13) % len(locations)])
        tasks.append((source_id, scraper_cls(settings, keyword=keyword, location=location)))

    records = []
    if not tasks:
        return records, statuses

    def execute(source_id, instance):
        if STOP_REQUESTED:
            return source_id, [], {"status": "skipped", "reason": "shutdown requested"}
        try:
            document = instance.fetch()
            parsed = instance.parse(document)
            if not parsed:
                reason = (
                    "Parser returned zero records; the page may be JavaScript-rendered, "
                    "the search URL may have changed, or selectors/JSON-LD may need updating. "
                    "Source remains enabled for the next scheduled retry."
                )
                log.warning("Source %s returned zero records: %s", source_id, reason)
                return source_id, [], {
                    "status": "no_records",
                    "records_accepted": 0,
                    "reason": reason,
                    "location_query": instance.location,
                    "keyword_query": instance.keyword,
                }
            return source_id, parsed, {
                "status": "ok",
                "records_accepted": len(parsed),
                "location_query": instance.location,
                "keyword_query": instance.keyword,
            }
        except SourceNotAllowed as exc:
            log.warning("Source %s skipped: %s", source_id, exc)
            return source_id, [], {"status": "skipped", "reason": str(exc)[:240]}
        except Exception as exc:
            response = getattr(exc, "response", None)
            http_status = getattr(response, "status_code", None)
            if http_status in (403, 429):
                log.warning("Source %s blocked with HTTP %s; keeping adapter enabled for later retry", source_id, http_status)
                return source_id, [], {
                    "status": "blocked",
                    "http_status": http_status,
                    "error": str(exc)[:240],
                    "retry_on_next_scheduled_run": True,
                }
            log.exception("Source %s failed; continuing other scrapers", source_id)
            return source_id, [], {"status": "error", "error": str(exc)[:240]}

    with ThreadPoolExecutor(max_workers=min(4, len(tasks)), thread_name_prefix="loker-source") as pool:
        futures = {pool.submit(execute, source_id, instance): source_id for source_id, instance in tasks}
        for future in as_completed(futures):
            try:
                source_id, rows, status = future.result()
            except Exception as exc:
                source_id = futures[future]
                rows, status = [], {"status": "error", "error": str(exc)[:240]}
            statuses[source_id] = status
            records.extend(rows)
    return records, statuses


def render_website():
    """Render the existing static frontend from its Jinja template."""
    environment = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=False,
        undefined=StrictUndefined,
    )
    rendered = environment.get_template(SITE_TEMPLATE).render()
    target = ROOT / "index.html"
    current = target.read_text(encoding="utf-8") if target.exists() else ""
    if rendered != current:
        target.write_text(rendered, encoding="utf-8")


def main() -> int:
    run_started = time.monotonic()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, signal_handler)

    started_at = utc_now()
    config = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8")) or {}
    previous = read_json(JOBS_FILE, {"schema_version": "2.0", "jobs": []})
    backup = DATA_DIR / f"jobs_{datetime.now(WIB):%Y%m%d}.json"
    if JOBS_FILE.exists() and not backup.exists():
        backup.write_text(JOBS_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        log.info("Created daily backup %s", backup.name)

    legacy_code = None
    legacy_error = None
    legacy_settings = config.get("legacy_pipeline") or {}
    if legacy_settings.get("enabled", True):
        os.environ.setdefault("QUERY_BATCH_SIZE", str(legacy_settings.get("query_batch_size", 120)))
        os.environ.setdefault("DATA_RETENTION_DAYS", str(legacy_settings.get("retention_days", 120)))
        try:
            from scraper.main import main as legacy_main
            legacy_code = legacy_main()
            if legacy_code:
                legacy_error = f"existing public-source collector returned {legacy_code}"
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            legacy_error = str(exc)[:300]
            log.exception("Existing public-source collector failed; trying enabled authorized adapters")

    payload_after_legacy = read_json(JOBS_FILE, previous)
    existing_jobs = payload_after_legacy.get("jobs", []) if isinstance(payload_after_legacy, dict) else []
    if not isinstance(existing_jobs, list):
        existing_jobs = []

    module_records, module_statuses = collect_authorized_sources(config)
    try:
        from scrapers.company_sites import collect_company_sites
        company_records, company_status = collect_company_sites()
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        company_records = []
        company_status = {
            "status": "error",
            "reason": str(exc)[:300],
            "targets_configured": 0,
            "targets_checked": 0,
            "additional_records": 0,
            "companies": {},
        }
        log.exception("Company-site collection failed; continuing with the other sources")

    all_records = deduplicate(existing_jobs + module_records + company_records)
    if not all_records:
        log.error("No valid job records available after collection")
        return 1

    generated_at = utc_now()
    payload = {
        "schema_version": "2.0",
        "generated_at": generated_at,
        "timezone": "Asia/Jakarta",
        "total": len(all_records),
        "fresh_seen_in_this_run": int((payload_after_legacy or {}).get("fresh_seen_in_this_run", 0) or 0) + len(module_records) + len(company_records),
        "jobs": all_records,
    }
    write_json(JOBS_FILE, payload)
    render_website()

    status = read_json(STATUS_FILE, {})
    status["orchestration"] = {
        "status": "ok" if (legacy_code == 0 or module_records) else "partial",
        "started_at": started_at,
        "finished_at": generated_at,
        "legacy_pipeline_return_code": legacy_code,
        "legacy_pipeline_error": legacy_error,
        "additional_sources": module_statuses,
        "additional_records": len(module_records),
        "company_site_records": len(company_records),
        "company_sites": company_status,
        "records_after_deduplication": len(all_records),
        "output_schema": "common v2 plus compatibility aliases",
        "hourly_rotation_slot": int(time.time() // 3600),
        "elapsed_seconds": round(time.monotonic() - run_started, 2),
    }
    # Preserve the last complete per-company report on hourly runs that are not due.
    if company_status.get("status") != "skipped" or not status.get("company_sites"):
        status["company_sites"] = company_status
    else:
        status["company_sites"]["schedule_status"] = {
            "status": "skipped",
            "reason": company_status.get("reason"),
            "due_at": company_status.get("due_at"),
        }
    write_json(STATUS_FILE, status)

    counts = {}
    for record in all_records:
        key = record.get("source") or "unknown"
        counts[key] = counts.get(key, 0) + 1
    log.info("Finished run in %.1f seconds", time.monotonic() - run_started)
    log.info("Records after dedupe: %d; count by source: %s", len(all_records), counts)
    log.info("Additional adapter status: %s", module_statuses)
    log.info("Company-site status: %s", {k: v for k, v in company_status.items() if k != "companies"})
    return 0 if legacy_code == 0 or module_records or company_records else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        logging.getLogger("info-loker.orchestrator").warning("Graceful shutdown complete")
        raise SystemExit(130)
