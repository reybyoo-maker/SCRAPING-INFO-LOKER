"""Common safe HTML scraper utilities for explicitly authorized sources.

No stealth browser, credential reuse, proxy rotation, or access-control bypass is used.
A source is contacted only when both enabled and authorized are true in config.yaml,
and only when the source robots.txt permits the configured URL.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import threading
import unicodedata
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

UTC = timezone.utc
DEFAULT_USER_AGENT = (
    "INFOLOKERIndonesiaBot/2.0 "
    "(public job metadata; contact: https://github.com/reybyoo-maker/SCRAPING-INFO-LOKER)"
)
MAX_ATTEMPTS = 3
HTTP_TIMEOUT = 30
_REQUEST_LOCK = threading.Lock()
_LAST_REQUEST_START = 0.0
_ROBOTS_CACHE: dict[tuple[str, str], tuple[float, bool]] = {}
_ROBOTS_LOCK = threading.Lock()
logger = logging.getLogger("info-loker.scrapers")


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def clean(value, limit: int | None = None) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    text = BeautifulSoup(str(value), "html.parser").get_text(" ", strip=True)
    text = " ".join(text.split())
    if limit is not None:
        text = text[:limit].rstrip()
    return text


# Exact navigation/CTA labels that career-site scrapers must never publish as job titles.
# Keep this list conservative so real roles such as "English Teacher" remain valid.
_NOISE_JOB_TITLES = frozenset({
    "english", "english us", "indonesian", "bahasa", "bahasa indonesia", "select language",
    "apply", "apply now", "apply here", "apply online", "apply for this job", "quick apply",
    "sign up", "sign in", "sign up now", "login", "log in", "log out", "logout",
    "register", "register now", "create account",
    "see more", "see all", "view more", "view all", "show more", "read more", "learn more",
    "more", "details", "home", "about", "about us", "contact", "contact us",
    "privacy policy", "terms and conditions", "cookie policy", "search", "search jobs",
    "career", "careers", "job", "jobs", "job search", "job openings", "join us",
    "join our team", "job alerts", "corporate", "academics", "faculty", "faculties",
    "admission", "admissions", "student", "students", "program", "programs", "programmes",
    "research", "news", "blog", "overview",
    "pendaftaran", "daftar", "masuk", "lamar", "lamar sekarang", "lihat lowongan",
    "lihat selengkapnya", "baca selengkapnya", "selengkapnya", "lompat ke konten utama",
    "skip to main content", "jump to main content",
})


def is_noise_job_title(value) -> bool:
    """Return True for exact navigation/CTA labels misread as job titles."""
    text = unicodedata.normalize("NFKD", clean(value)).lower()
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = " ".join("".join(char if char.isalnum() else " " for char in text).split())
    return text in _NOISE_JOB_TITLES


def parse_iso(value) -> str | None:
    if not value:
        return None
    try:
        if isinstance(value, (int, float)):
            dt = datetime.fromtimestamp(value, tz=UTC)
        else:
            dt = date_parser.parse(str(value), fuzzy=True)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            dt = dt.astimezone(UTC)
        return dt.isoformat(timespec="seconds").replace("+00:00", "Z")
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def canonical_job_type(value) -> str | None:
    text = clean(value).lower().replace("_", " ").replace("-", " ")
    if not text:
        return None
    if any(word in text for word in ("intern", "internship", "magang", "apprentice")):
        return "intern"
    if any(word in text for word in ("freelance", "freelancer", "contractor independent")):
        return "freelance"
    if any(word in text for word in ("part time", "parttime", "paruh waktu")):
        return "parttime"
    if any(word in text for word in ("contract", "kontrak", "temporary", "temporer")):
        return "contract"
    if any(word in text for word in ("full time", "fulltime", "penuh waktu", "permanent", "tetap")):
        return "fulltime"
    return None


class SourceNotAllowed(RuntimeError):
    """Raised when an adapter is not explicitly enabled or robots.txt disallows it."""


class BaseScraper:
    source_id = "unknown"
    source_label = "Unknown source"
    base_domain = ""
    card_selectors = (
        "article",
        "li[data-job-id]",
        "[data-job-id]",
        "[data-testid*='job']",
        "[data-automation*='jobListing']",
        ".job-card",
        ".job-item",
        ".vacancy",
    )
    title_selectors = (
        "[data-automation='jobTitle']",
        "[data-testid*='job-title']",
        "h2",
        "h3",
        ".job-title",
        ".title",
    )
    company_selectors = (
        "[data-automation='jobCompany']",
        "[data-testid*='company']",
        ".company",
        ".company-name",
        "[class*='company']",
    )
    location_selectors = (
        "[data-automation='jobLocation']",
        "[data-testid*='location']",
        ".location",
        ".job-location",
        "[class*='location']",
    )
    salary_selectors = (
        "[data-automation='jobSalary']",
        "[data-testid*='salary']",
        ".salary",
        "[class*='salary']",
        "[class*='compensation']",
    )
    date_selectors = ("time[datetime]", "time", "[class*='date']", "[class*='posted']")
    description_selectors = (
        "[data-automation='jobShortDescription']",
        "[data-testid*='description']",
        ".description",
        ".job-description",
        "[class*='description']",
    )

    def __init__(self, settings: dict | None = None, keyword: str = "lowongan kerja",
                 location: str = "Indonesia"):
        self.settings = settings or {}
        self.keyword = keyword
        self.location = location
        self.enabled = self.settings.get("enabled") is True
        self.authorized = self.settings.get("authorized") is True
        self.timeout = min(HTTP_TIMEOUT, max(5, int(self.settings.get("timeout_seconds", HTTP_TIMEOUT))))
        try:
            self.min_delay_seconds = max(0.0, float(self.settings.get("min_delay_seconds", 2.0)))
            self.max_delay_seconds = max(self.min_delay_seconds, float(self.settings.get("max_delay_seconds", 5.0)))
        except (TypeError, ValueError):
            self.min_delay_seconds, self.max_delay_seconds = 2.0, 5.0
        self.user_agent = os.getenv("USER_AGENT", DEFAULT_USER_AGENT).strip() or DEFAULT_USER_AGENT
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "id-ID,id;q=0.9,en;q=0.7",
        })

    def build_url(self) -> str:
        template = str(self.settings.get("search_url") or "").strip()
        if not template:
            raise SourceNotAllowed(f"{self.source_id}: no search_url is configured")
        url = template.format(
            keyword=quote_plus(self.keyword),
            location=quote_plus(self.location),
            page=1,
        )
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise SourceNotAllowed(f"{self.source_id}: only HTTPS source URLs are accepted")
        host = parsed.hostname.lower()
        root = self.base_domain.lower().lstrip(".")
        if not root or not (host == root or host.endswith("." + root)):
            raise SourceNotAllowed(f"{self.source_id}: URL host is outside the declared source domain")
        return url

    @staticmethod
    def _paced_request(session: requests.Session, method: str, url: str, timeout: int, **kwargs):
        """Pace HTTP requests using per-source bounds, with bounded retries for transient errors."""
        global _LAST_REQUEST_START
        min_delay = max(0.0, float(kwargs.pop("min_delay_seconds", 2.0)))
        max_delay = max(min_delay, float(kwargs.pop("max_delay_seconds", 5.0)))
        last_error = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            with _REQUEST_LOCK:
                now = time.monotonic()
                if _LAST_REQUEST_START:
                    delay = max(0.0, random.uniform(min_delay, max_delay) - (now - _LAST_REQUEST_START))
                    if delay:
                        time.sleep(delay)
                _LAST_REQUEST_START = time.monotonic()
            try:
                response = session.request(method, url, timeout=timeout, allow_redirects=True, **kwargs)
                # Never retry 403: respect explicit denial. Retry only transient 429/5xx responses.
                if (response.status_code == 429 or response.status_code >= 500) and attempt < MAX_ATTEMPTS:
                    retry_after = response.headers.get("Retry-After", "")
                    try:
                        wait_seconds = min(20.0, max(0.0, float(retry_after)))
                    except ValueError:
                        try:
                            wait_seconds = min(20.0, max(0.0, (parsedate_to_datetime(retry_after) - datetime.now(UTC)).total_seconds()))
                        except Exception:
                            wait_seconds = 0.0
                    time.sleep(wait_seconds or (2 ** attempt))
                    continue
                return response
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= MAX_ATTEMPTS:
                    raise
                time.sleep(2 ** attempt)
        if last_error:
            raise last_error
        raise requests.RequestException(f"Request failed for {url}")

    @staticmethod
    def _paced_get(session: requests.Session, url: str, timeout: int, **kwargs):
        return BaseScraper._paced_request(session, "GET", url, timeout, **kwargs)

    @staticmethod
    def _paced_post(session: requests.Session, url: str, timeout: int, **kwargs):
        return BaseScraper._paced_request(session, "POST", url, timeout, **kwargs)

    def robots_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        cache_key = (origin, self.user_agent)
        now = time.monotonic()
        with _ROBOTS_LOCK:
            cached = _ROBOTS_CACHE.get(cache_key)
            if cached and now - cached[0] < 3600:
                return cached[1]

        robots_url = origin + "/robots.txt"
        try:
            response = self._paced_get(
                self.session,
                robots_url,
                min(15, self.timeout),
                min_delay_seconds=self.min_delay_seconds,
                max_delay_seconds=self.max_delay_seconds,
            )
        except requests.RequestException as exc:
            logger.warning("%s skipped: cannot verify robots.txt (%s)", self.source_id, exc)
            allowed = False
        else:
            if response.status_code in (404, 410):
                allowed = True
            elif response.status_code in (403, 429):
                # Do not request the listing if robots.txt itself is access-denied/rate-limited.
                # Propagate the response so orchestration records an explicit blocked status.
                raise requests.HTTPError(
                    f"{self.source_id} robots.txt returned HTTP {response.status_code}; "
                    "listing URL was not requested",
                    response=response,
                )
            elif response.status_code < 200 or response.status_code >= 300:
                # Fail closed when access rules cannot be verified.
                logger.warning(
                    "%s skipped: robots.txt returned HTTP %s; access rules cannot be verified",
                    self.source_id,
                    response.status_code,
                )
                allowed = False
            else:
                parser = RobotFileParser()
                parser.set_url(robots_url)
                parser.parse(response.text.splitlines())
                allowed = parser.can_fetch(self.user_agent, url)

        with _ROBOTS_LOCK:
            _ROBOTS_CACHE[cache_key] = (time.monotonic(), allowed)
        return allowed

    def fetch(self) -> str | None:
        if not self.enabled:
            logger.info("%s skipped: disabled in config.yaml", self.source_id)
            return None
        if not self.authorized:
            logger.info("%s skipped: explicit authorization is not enabled", self.source_id)
            return None
        url = self.build_url()
        if not self.robots_allowed(url):
            raise SourceNotAllowed(f"{self.source_id}: robots.txt blocks the configured search URL or could not be verified")
        response = self._paced_get(
            self.session,
            url,
            self.timeout,
            min_delay_seconds=self.min_delay_seconds,
            max_delay_seconds=self.max_delay_seconds,
        )
        if response.status_code in (403, 429):
            raise requests.HTTPError(
                f"{self.source_id} blocked the request with HTTP {response.status_code}; "
                "source will be logged and retried on a later scheduled run",
                response=response,
            )
        if response.status_code >= 400:
            raise requests.HTTPError(f"{self.source_id} returned HTTP {response.status_code}", response=response)
        final = urlparse(response.url)
        root = self.base_domain.lower().lstrip(".")
        host = (final.hostname or "").lower()
        if not (host == root or host.endswith("." + root)):
            raise SourceNotAllowed(f"{self.source_id}: redirect left the declared source domain")
        return response.text

    def parse(self, document: str | None) -> list[dict]:
        return self.parse_listing_page(document)

    def parse_listing_page(self, document: str | None) -> list[dict]:
        if not document:
            return []
        soup = BeautifulSoup(document, "html.parser")
        rows: list[dict] = []
        seen: set[str] = set()

        for posting in self._jsonld_postings(soup):
            normalized = self._normalize_job(
                title=posting.get("title"),
                company=posting.get("company"),
                location=posting.get("location"),
                url=posting.get("url"),
                posted_at=posting.get("posted_at"),
                salary=posting.get("salary"),
                job_type=posting.get("job_type"),
                description=posting.get("description"),
            )
            if normalized and normalized["url"] not in seen:
                rows.append(normalized)
                seen.add(normalized["url"])

        for selector in self.card_selectors:
            try:
                cards = soup.select(selector)
            except Exception:
                cards = []
            for card in cards:
                anchor = card if getattr(card, "name", "") == "a" and card.get("href") else card.find("a", href=True)
                if anchor is None:
                    continue
                title = self._first_text(card, self.title_selectors) or clean(anchor.get_text(" ", strip=True), 250)
                url = urljoin(self.settings.get("search_url", ""), str(anchor.get("href", "")))
                if not title or not self._same_domain(url) or url in seen:
                    continue
                date_node = self._first_node(card, self.date_selectors)
                posted = (date_node.get("datetime") or date_node.get_text(" ", strip=True)) if date_node else None
                row = self._normalize_job(
                    title=title,
                    company=self._first_text(card, self.company_selectors),
                    location=self._first_text(card, self.location_selectors),
                    url=url,
                    posted_at=posted,
                    salary=self._first_text(card, self.salary_selectors),
                    job_type=self._first_text(card, (".employment-type", "[class*='employment']", "[class*='job-type']")),
                    description=self._first_text(card, self.description_selectors),
                )
                if row:
                    rows.append(row)
                    seen.add(url)
        return rows

    def _jsonld_postings(self, soup: BeautifulSoup) -> list[dict]:
        found = []

        def walk(value):
            if isinstance(value, list):
                for entry in value:
                    walk(entry)
                return
            if not isinstance(value, dict):
                return
            types = value.get("@type", [])
            if isinstance(types, str):
                types = [types]
            if "JobPosting" in types:
                org = value.get("hiringOrganization") or {}
                loc_obj = value.get("jobLocation") or value.get("applicantLocationRequirements") or {}
                if isinstance(loc_obj, list):
                    loc_obj = loc_obj[0] if loc_obj else {}
                address = (loc_obj.get("address") or {}) if isinstance(loc_obj, dict) else {}
                if isinstance(address, list):
                    address = address[0] if address else {}
                if isinstance(address, dict):
                    location = ", ".join(filter(None, [
                        clean(address.get("addressLocality")),
                        clean(address.get("addressRegion")),
                        clean(address.get("addressCountry")),
                    ]))
                else:
                    location = clean(address)
                salary_obj = value.get("baseSalary") or {}
                salary = clean(salary_obj.get("value")) if isinstance(salary_obj, dict) else clean(salary_obj)
                if isinstance(org, dict):
                    company = org.get("name")
                else:
                    company = org
                found.append({
                    "title": value.get("title") or value.get("name"),
                    "company": company,
                    "location": location,
                    "url": value.get("url") or value.get("sameAs"),
                    "posted_at": value.get("datePosted"),
                    "salary": salary or None,
                    "job_type": value.get("employmentType"),
                    "description": value.get("description"),
                })
            for key in ("@graph", "mainEntity", "itemListElement"):
                if key in value:
                    walk(value[key])

        for script in soup.select('script[type="application/ld+json"]'):
            try:
                walk(json.loads(script.string or script.get_text()))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        return found

    def _same_domain(self, url: str) -> bool:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        root = self.base_domain.lower().lstrip(".")
        return parsed.scheme == "https" and bool(root) and (host == root or host.endswith("." + root))

    @staticmethod
    def _first_node(card, selectors):
        for selector in selectors:
            node = card.select_one(selector)
            if node:
                return node
        return None

    @classmethod
    def _first_text(cls, card, selectors) -> str:
        node = cls._first_node(card, selectors)
        if not node:
            return ""
        if node.name == "time" and node.get("datetime"):
            return clean(node.get("datetime"), 180)
        return clean(node.get_text(" ", strip=True), 500)

    def _normalize_job(self, title, company, location, url, posted_at=None,
                       salary=None, job_type=None, description=None) -> dict | None:
        title_text = clean(title, 250)
        url_text = str(url or "").strip()
        if not title_text or not url_text or not self._same_domain(url_text):
            return None
        company_text = clean(company, 160)
        location_text = clean(location, 220)
        posted = parse_iso(posted_at)
        salary_text = clean(salary, 100) or None
        kind = canonical_job_type(job_type)
        description_text = clean(description, 300)
        scraped_at = utc_now()
        identity = hashlib.sha256((url_text + title_text + company_text).encode("utf-8")).hexdigest()[:16]
        quality_score = 35 + 15 * bool(company_text) + 15 * bool(location_text) + 15 * bool(posted) + 10 * bool(salary_text) + 10 * bool(description_text)
        quality_label = "HOT" if quality_score >= 80 else "MEDIUM" if quality_score >= 50 else "LOW"
        return {
            "id": identity,
            "title": title_text,
            "company": company_text,
            "location": location_text,
            "source": self.source_id,
            "url": url_text,
            "posted_at": posted,
            "salary": salary_text,
            "job_type": kind,
            "description_snippet": description_text,
            "scraped_at": scraped_at,
            # Compatibility aliases consumed by the existing INFO LOKER website.
            "source_name": self.source_label,
            "source_type": "authorized_html",
            "listing_url": url_text,
            "application_url": url_text,
            "company_name": company_text or None,
            "location_label": location_text or None,
            "city": location_text or None,
            "province": None,
            "published_at": posted,
            "source_updated_at": posted,
            "salary_text": salary_text,
            "employment_type": job_type,
            "description_excerpt": description_text,
            "last_seen_at": scraped_at,
            "last_checked_at": scraped_at,
            "first_seen_at": scraped_at,
            "listing_state": "active_unverified",
            "work_mode": "Unknown",
            "is_remote": None,
            "quality_score": quality_score,
            "quality_label": quality_label,
            "quality_explanation": ["Metadata completeness only; employer and vacancy were not independently verified."],
            "risk_flags": [],
        }
