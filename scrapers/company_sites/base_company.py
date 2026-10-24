"""Robots-aware HTTPS client, persisted blocked-domain registry, and per-domain pacing."""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_UA = "InfoLokerBot/1.0 (+https://github.com/reybyoo-maker/SCRAPING-INFO-LOKER)"
UTC = timezone.utc
logger = logging.getLogger("info-loker.company-sites.http")
_BLOCKED_LOCK = threading.RLock()
_ROBOTS_LOCK = threading.RLock()
_ROBOTS_CACHE: dict[str, tuple[float, str, RobotFileParser | None]] = {}


def domain_key(url_or_domain: str) -> str:
    raw = str(url_or_domain or "").strip()
    parsed = urlparse(raw if "://" in raw else "https://" + raw)
    return (parsed.hostname or "").lower().rstrip(".")


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class RobotsDisallowed(RuntimeError):
    """The site's robots.txt forbids a URL or its rules could not be verified."""


class DomainBlocked(RuntimeError):
    def __init__(self, domain: str, status_code: int | None, message: str):
        super().__init__(message)
        self.domain = domain
        self.status_code = status_code


class DomainRequestLimit(RuntimeError):
    """The per-domain request cap for this run was reached."""


class BlockedDomainRegistry:
    def __init__(self, path: Path | None = None):
        self.path = path or ROOT / "data" / "blocked_domains.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.entries = self._read()

    def _read(self):
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("domains"), dict):
                return payload["domains"]
            return payload if isinstance(payload, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def is_blocked(self, url_or_domain: str) -> bool:
        key = domain_key(url_or_domain)
        with _BLOCKED_LOCK:
            return key in self.entries

    def is_blocked_from_exception(self, exc: BaseException) -> bool:
        domain = getattr(exc, "domain", "")
        return bool(domain and self.is_blocked(domain))

    def add(self, url_or_domain: str, reason: str, status_code: int | None = None):
        key = domain_key(url_or_domain)
        if not key:
            return
        with _BLOCKED_LOCK:
            self.entries.setdefault(key, {
                "blocked_at": utc_now(),
                "reason": str(reason)[:300],
                "http_status": status_code,
                "retry_policy": "manual_review_required",
            })
            self._write_locked()

    def _write_locked(self):
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps({"domains": self.entries}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)

    def save(self):
        with _BLOCKED_LOCK:
            self._write_locked()


class DomainRateLimiter:
    def __init__(self):
        self._state_lock = threading.RLock()
        self._domain_locks: dict[str, threading.Lock] = {}
        self._last_start: dict[str, float] = {}
        self._counts: dict[str, int] = {}
        self.delay_seconds = 2.0
        self.max_requests = 50

    def reset(self, delay_seconds: float = 2.0, max_requests: int = 50):
        with self._state_lock:
            self._last_start.clear()
            self._counts.clear()
            self.delay_seconds = max(2.0, float(delay_seconds))
            self.max_requests = min(50, max(1, int(max_requests)))

    def _lock_for(self, domain: str):
        with self._state_lock:
            return self._domain_locks.setdefault(domain, threading.Lock())

    def wait_for_slot(self, url: str):
        domain = domain_key(url)
        domain_lock = self._lock_for(domain)
        domain_lock.acquire()
        with self._state_lock:
            count = self._counts.get(domain, 0)
            if count >= self.max_requests:
                domain_lock.release()
                raise DomainRequestLimit("Per-domain request cap (%d) reached for %s" % (self.max_requests, domain))
            previous = self._last_start.get(domain)
            delay = self.delay_seconds - (time.monotonic() - previous) if previous else 0.0
            if delay > 0:
                time.sleep(delay)
            self._last_start[domain] = time.monotonic()
            self._counts[domain] = count + 1
        return domain_lock

    def finish_slot(self, lock):
        lock.release()


RATE_LIMITER = DomainRateLimiter()


class CompanySiteClient:
    def __init__(self, target: dict, *, blocked_registry: BlockedDomainRegistry | None = None):
        self.target = target
        self.blocked_registry = blocked_registry or BlockedDomainRegistry()
        self.timeout = min(25, max(5, int(target.get("timeout_seconds", 15))))
        self.user_agent = DEFAULT_UA
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.6",
            "Accept-Language": "id-ID,id;q=0.9,en;q=0.7",
        })

    def _send(self, url: str, *, robots_request: bool = False):
        domain = domain_key(url)
        if self.blocked_registry.is_blocked(domain):
            item = self.blocked_registry.entries.get(domain, {})
            raise DomainBlocked(domain, item.get("http_status"), "Domain %s is already blocked; manual review is required" % domain)
        lock = RATE_LIMITER.wait_for_slot(url)
        try:
            response = self.session.get(url, timeout=self.timeout, allow_redirects=False)
        finally:
            RATE_LIMITER.finish_slot(lock)
        if response.status_code in (403, 429):
            self.blocked_registry.add(domain, "HTTP %d; requests paused until manual review" % response.status_code, response.status_code)
            raise DomainBlocked(domain, response.status_code, "Domain %s returned HTTP %d" % (domain, response.status_code))
        return response

    def robots_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            return False
        host = domain_key(url)
        now = time.monotonic()
        with _ROBOTS_LOCK:
            cached = _ROBOTS_CACHE.get(host)
            if cached and now - cached[0] < 3600:
                text, parser = cached[1], cached[2]
                self.robots_text = text
                return parser is None or parser.can_fetch(self.user_agent, url)

        robots_url = "https://%s/robots.txt" % host
        response = self._send(robots_url, robots_request=True)
        if response.status_code in (404, 410):
            robots_text = ""
            parser = None
        elif 200 <= response.status_code < 300:
            robots_text = response.text
            parser = RobotFileParser()
            parser.set_url(robots_url)
            parser.parse(robots_text.splitlines())
        elif response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("Location")
            if not location:
                raise RobotsDisallowed("%s robots.txt redirected without a Location" % host)
            redirected = urljoin(robots_url, location)
            if domain_key(redirected) != host or urlparse(redirected).scheme != "https":
                raise RobotsDisallowed("%s robots.txt redirected outside its host" % host)
            redirected_response = self._send(redirected, robots_request=True)
            if not 200 <= redirected_response.status_code < 300:
                raise RobotsDisallowed("%s robots.txt returned HTTP %d" % (host, redirected_response.status_code))
            robots_text = redirected_response.text
            parser = RobotFileParser()
            parser.set_url(redirected)
            parser.parse(robots_text.splitlines())
        else:
            raise RobotsDisallowed("%s robots.txt returned HTTP %d; fail closed" % (host, response.status_code))
        with _ROBOTS_LOCK:
            _ROBOTS_CACHE[host] = (time.monotonic(), robots_text, parser)
        self.robots_text = robots_text
        return parser is None or parser.can_fetch(self.user_agent, url)

    def get(self, url: str, *, max_redirects: int = 6):
        current = str(url).strip()
        if not current.startswith("https://"):
            raise ValueError("Only HTTPS career URLs are allowed")
        for _ in range(max_redirects + 1):
            if not self.robots_allowed(current):
                raise RobotsDisallowed("robots.txt disallows %s" % current)
            response = self._send(current)
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                if not location:
                    return response
                current = urljoin(current, location)
                if urlparse(current).scheme != "https":
                    raise ValueError("Redirect left HTTPS; request refused")
                continue
            return response
        raise ValueError("Too many redirects while resolving %s" % url)
