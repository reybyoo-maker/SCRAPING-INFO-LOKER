"""One-shot validation of curated company career URLs.

Usage:
  python scripts/discover_company_careers.py          # discover and validate career URLs only
  python scripts/discover_company_careers.py --scrape # discover and collect listings
  python scripts/discover_company_careers.py --scrape --force
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scrapers.company_sites import collect_company_sites, discover_company_careers, write_json, read_json, REGISTRY_FILE, ROOT as COMPANY_ROOT
from scripts.run_all import deduplicate, render_website


def main():
    parser = argparse.ArgumentParser(description="Discover/validate official company career pages.")
    parser.add_argument("--scrape", action="store_true", help="also parse public vacancy metadata")
    parser.add_argument("--force", action="store_true", help="run even if the six-hour interval has not elapsed")
    args = parser.parse_args()
    if not args.scrape:
        result = discover_company_careers()
        print(json.dumps({k: v for k, v in result.items() if k != "targets"}, ensure_ascii=False, indent=2))
        return 0

    records, status = collect_company_sites(force=args.force)
    jobs_path = COMPANY_ROOT / "data" / "jobs.json"
    payload = read_json(jobs_path, {"schema_version": "2.0", "jobs": []})
    existing = payload.get("jobs", []) if isinstance(payload, dict) else payload
    all_jobs = deduplicate(list(existing or []) + records)
    payload = {
        "schema_version": "2.0",
        "generated_at": status.get("finished_at"),
        "timezone": "Asia/Jakarta",
        "total": len(all_jobs),
        "fresh_seen_in_this_run": len(records),
        "jobs": all_jobs,
    }
    write_json(jobs_path, payload)
    status_path = COMPANY_ROOT / "data" / "run_status.json"
    run_status = read_json(status_path, {})
    run_status["company_sites"] = status
    write_json(status_path, run_status)
    render_website()
    print(json.dumps({
        "status": status.get("status"),
        "targets_checked": status.get("targets_checked", 0),
        "records_accepted": len(records),
        "dataset_total": len(all_jobs),
        "status_counts": status.get("status_counts", {}),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
