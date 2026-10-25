"""Collection runner for official company career pages.

The runner is robots-aware, domain-rate-limited, and isolated per company so one
failing host cannot stop the remaining targets.
"""
from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from .base_company import BlockedDomainRegistry, CompanySiteClient, RATE_LIMITER
from .discovery import discover_target
from .generic_parser import GenericCompanyParser
from .specific import SPECIFIC_PARSERS
from .categories import CATEGORY_PARSERS

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
TARGETS_FILE = ROOT / "config" / "company_targets.yaml"
BLOCKED_FILE = DATA_DIR / "blocked_domains.json"
REGISTRY_FILE = DATA_DIR / "company_career_registry.json"
STATE_FILE = DATA_DIR / "company_scrape_state.json"
logger = logging.getLogger("info-loker.company-sites")
UTC = timezone.utc


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_targets(path: Path = TARGETS_FILE) -> tuple[dict, list[dict]]:
    config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    targets = [
        item for item in (config.get("targets") or [])
        if isinstance(item, dict) and item.get("enabled", True) is True
        and item.get("domain") and item.get("name") and item.get("website")
    ]
    # Do not issue repeated page scans for multiple brands sharing an identical host.
    unique = {}
    for target in targets:
        domain = str(target["domain"]).lower().strip().removeprefix("www.")
        unique.setdefault(domain, target)
    return config, list(unique.values())


def scrape_target(target: dict, client: CompanySiteClient | None = None) -> tuple[list[dict], dict]:
    client = client or CompanySiteClient(target)
    base_status = {
        "company": target["name"],
        "domain": target["domain"],
        "category": target.get("category", "Corporate"),
        "status": "no-career-page",
        "records_accepted": 0,
    }
    try:
        discovery = discover_target(target, client)
        base_status.update(discovery.get("status_detail") or {})
        if not discovery.get("pages"):
            base_status["status"] = discovery.get("status", "no-career-page")
            base_status["reason"] = discovery.get("reason", "No permitted career page found by URL-pattern and sitemap checks.")
            base_status["career_url"] = discovery.get("career_url")
            return [], base_status

        parser_class = SPECIFIC_PARSERS.get(target.get("specific_parser")) or CATEGORY_PARSERS.get(target.get("category"), GenericCompanyParser)
        parser = parser_class(target)
        records = []
        seen = set()
        for page_url, html in discovery["pages"]:
            for record in parser.parse(html, page_url):
                key = (record.get("url"), record.get("title"))
                if key not in seen:
                    seen.add(key)
                    records.append(record)
        base_status["career_url"] = discovery.get("career_url")
        base_status["pages_checked"] = len(discovery["pages"])
        if records:
            base_status["status"] = "ok"
            base_status["records_accepted"] = len(records)
            return records, base_status
        base_status["status"] = "no-career-page"
        base_status["reason"] = "Career page was reachable but no supported vacancy record was parsed."
        return [], base_status
    except Exception as exc:
        code = getattr(exc, "status_code", None)
        if code in (403, 429) or client.blocked_registry.is_blocked_from_exception(exc):
            base_status["status"] = "blocked"
            base_status["http_status"] = code
        elif exc.__class__.__name__ == "RobotsDisallowed":
            base_status["status"] = "no-career-page"
            base_status["reason"] = str(exc)[:300]
        else:
            base_status["status"] = "parse-error"
            base_status["error"] = str(exc)[:300]
        logger.warning("Company target %s (%s) %s: %s", target.get("name"), target.get("domain"), base_status["status"], str(exc)[:240])
        return [], base_status


def collect_company_sites(force: bool = False, *, targets_path: Path = TARGETS_FILE) -> tuple[list[dict], dict]:
    """Run company collection no more often than configured unless force=True."""
    config, targets = load_targets(targets_path)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    state = read_json(STATE_FILE, {})
    now = datetime.now(UTC)
    interval_hours = max(1, int(config.get("run_every_hours", 6)))
    previous = state.get("finished_at")
    if not force and previous:
        try:
            last = datetime.fromisoformat(str(previous).replace("Z", "+00:00"))
            due_at = last + timedelta(hours=interval_hours)
            if now < due_at:
                return [], {
                    "status": "skipped",
                    "reason": "Company-site collection runs every %s hours." % interval_hours,
                    "due_at": due_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
                    "targets_configured": len(targets),
                    "additional_records": 0,
                    "companies": {},
                }
        except (ValueError, TypeError):
            pass

    max_workers = min(8, max(1, int(config.get("max_workers", 8))))
    max_requests = min(50, max(1, int(config.get("max_requests_per_domain_per_run", 50))))
    delay = max(2.0, float(config.get("min_seconds_between_requests_per_domain", 2)))
    RATE_LIMITER.reset(delay_seconds=delay, max_requests=max_requests)
    blocked = BlockedDomainRegistry(BLOCKED_FILE)
    # Every target gets its own client/session, but clients share the per-domain limiter
    # and persisted blocked-domain registry.
    for target in targets:
        target["_company_site_client"] = CompanySiteClient(target, blocked_registry=blocked)
    run_started = utc_now()
    records = []
    statuses = {}
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="company-site") as pool:
        futures = {
            pool.submit(scrape_target, target, target["_company_site_client"]): target
            for target in targets
        }
        for future in as_completed(futures):
            target = futures[future]
            key = str(target.get("id") or target.get("domain"))
            try:
                rows, status = future.result()
            except Exception as exc:
                rows, status = [], {
                    "company": target.get("name"),
                    "domain": target.get("domain"),
                    "category": target.get("category"),
                    "status": "parse-error",
                    "error": str(exc)[:300],
                    "records_accepted": 0,
                }
            statuses[key] = status
            logger.info(
                "Company target %s (%s): status=%s records=%d career_url=%s reason=%s",
                status.get("company") or target.get("name"),
                status.get("domain") or target.get("domain"),
                status.get("status"),
                int(status.get("records_accepted", len(rows)) or 0),
                status.get("career_url") or "-",
                (status.get("reason") or status.get("error") or "-")[:180],
            )
            records.extend(rows)

    finished = utc_now()
    prior_registry = read_json(REGISTRY_FILE, {})
    registry_targets = prior_registry.get("targets", {}) if isinstance(prior_registry, dict) else {}
    for key, status in statuses.items():
        registry_targets[key] = {
            "company": status.get("company"),
            "domain": status.get("domain"),
            "category": status.get("category"),
            "career_url": status.get("career_url"),
            "status": status.get("status"),
            "checked_at": finished,
            "records_accepted": status.get("records_accepted", 0),
            "reason": status.get("reason") or status.get("error"),
        }
    write_json(REGISTRY_FILE, {"generated_at": finished, "targets": registry_targets})
    write_json(STATE_FILE, {
        "started_at": state.get("started_at") or finished,
        "finished_at": finished,
        "targets_checked": len(statuses),
        "records_accepted": len(records),
        "status_counts": {
            code: sum(1 for value in statuses.values() if value.get("status") == code)
            for code in sorted({value.get("status", "unknown") for value in statuses.values()})
        },
    })
    blocked.save()
    summary = {
        "status": "ok" if records else "partial",
        "started_at": run_started,
        "finished_at": finished,
        "targets_configured": len(targets),
        "targets_checked": len(statuses),
        "additional_records": len(records),
        "status_counts": {
            code: sum(1 for value in statuses.values() if value.get("status") == code)
            for code in sorted({value.get("status", "unknown") for value in statuses.values()})
        },
        "blocked_domains": len(blocked.entries),
        "companies": statuses,
    }
    logger.info("Company-site run done: targets=%d records=%d statuses=%s", len(targets), len(records), summary["status_counts"])
    return records, summary


def discover_company_careers(*, targets_path: Path = TARGETS_FILE, blocked_path: Path = BLOCKED_FILE) -> dict:
    """Run discovery/URL validation without parsing all resulting vacancy pages."""
    config, targets = load_targets(targets_path)
    max_workers = min(8, max(1, int(config.get("max_workers", 8))))
    RATE_LIMITER.reset(
        delay_seconds=max(2.0, float(config.get("min_seconds_between_requests_per_domain_per_run", 2))),
        max_requests=min(50, max(1, int(config.get("max_requests_per_domain_per_run", 50)))),
    )
    blocked = BlockedDomainRegistry(blocked_path)
    results = {}
    def worker(target):
        client = CompanySiteClient(target, blocked_registry=blocked)
        detail = discover_target(target, client)
        return str(target.get("id") or target.get("domain")), {
            "company": target["name"],
            "domain": target["domain"],
            "category": target.get("category"),
            "career_url": detail.get("career_url"),
            "status": detail.get("status", "no-career-page"),
            "reason": detail.get("reason"),
            "checked_at": utc_now(),
        }
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="career-discovery") as pool:
        futures = [pool.submit(worker, t) for t in targets]
        for future in as_completed(futures):
            try:
                key, result = future.result()
            except Exception as exc:
                key, result = "unknown-%d" % len(results), {"status": "parse-error", "reason": str(exc)[:300]}
            results[key] = result
    write_json(REGISTRY_FILE, {"generated_at": utc_now(), "targets": results})
    blocked.save()
    return {"targets_checked": len(results), "status_counts": {
        code: sum(1 for v in results.values() if v.get("status") == code)
        for code in sorted({v.get("status", "unknown") for v in results.values()})
    }, "targets": results}
