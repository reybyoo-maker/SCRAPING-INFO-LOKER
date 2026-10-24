"""Validate the published job dataset and fail when data is missing or stale."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOBS_FILE = ROOT / "data" / "jobs.json"
MINIMUM_JOBS = int(os.getenv("HEALTHCHECK_MINIMUM_JOBS", "100"))
MAX_AGE_HOURS = float(os.getenv("HEALTHCHECK_MAX_AGE_HOURS", "3"))


def parse_datetime(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def main() -> int:
    problems = []
    if not JOBS_FILE.is_file():
        print("FAIL: data/jobs.json does not exist")
        return 1
    try:
        payload = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: data/jobs.json is not valid JSON: {exc}")
        return 1

    jobs = payload if isinstance(payload, list) else payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(jobs, list):
        print("FAIL: expected a jobs list or an object containing jobs")
        return 1
    if len(jobs) < MINIMUM_JOBS:
        problems.append(f"Only {len(jobs)} jobs found; minimum is {MINIMUM_JOBS}")

    now = datetime.now(timezone.utc)
    times = [parse_datetime(job.get("scraped_at")) for job in jobs if isinstance(job, dict)]
    times = [value for value in times if value is not None]
    latest = max(times) if times else None
    if latest is None:
        problems.append("No valid jobs[].scraped_at timestamps found")
    else:
        age_hours = (now - latest).total_seconds() / 3600
        if age_hours > MAX_AGE_HOURS:
            problems.append(f"Latest scraped_at is {age_hours:.2f} hours old; maximum is {MAX_AGE_HOURS:.2f} hours")
        if age_hours < -0.25:
            problems.append("Latest scraped_at timestamp is implausibly in the future")

    if problems:
        print("FAIL: INFO LOKER health check")
        for problem in problems:
            print(f"- {problem}")
        return 1

    print(f"PASS: {len(jobs)} jobs; newest scraped_at={latest.isoformat()}; max age={MAX_AGE_HOURS:.2f} hours")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
