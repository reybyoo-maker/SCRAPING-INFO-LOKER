"""Three-layer career discovery: curated URL, public path patterns, and sitemap/robots."""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from .base_company import CompanySiteClient, DomainBlocked, DomainRequestLimit, RobotsDisallowed

CAREER_KEYWORDS = re.compile(r"(?:job|karir|karier|career|lowongan|vacancy|hiring)", re.I)
SITEMAP_JOB_PATH = re.compile(r"(?:career|careers|karir|karier|job|jobs|lowongan|loker|vacan|hiring|opportunit)", re.I)
PATTERNS = (
    "/careers", "/career", "/karir", "/karier",
    "/jobs", "/lowongan", "/loker",
    "/join-us", "/joinus", "/work-with-us",
    "/about/careers", "/about-us/careers",
    "/tentang-kami/karir", "/en/careers", "/id/careers",
)


def _html_text(html):
    return BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)


def _sitemap_locations(xml_text):
    soup = BeautifulSoup(xml_text or "", "xml")
    return [node.get_text(" ", strip=True) for node in soup.find_all("loc") if node.get_text(" ", strip=True)]


def _career_content(response):
    if response is None or response.status_code != 200:
        return False
    text = _html_text(response.text)
    title = str(BeautifulSoup(response.text, "html.parser").title.string or "") if BeautifulSoup(response.text, "html.parser").title else ""
    return bool(CAREER_KEYWORDS.search(text[:250000]) or CAREER_KEYWORDS.search(title))


def discover_target(target: dict, client: CompanySiteClient | None = None) -> dict:
    client = client or CompanySiteClient(target)
    website = str(target.get("website") or ("https://" + target["domain"] + "/"))
    candidates = []
    seed = str(target.get("career_url") or "").strip()
    if seed.startswith("https://"):
        candidates.append(seed)
    candidates.extend(urljoin(website.rstrip("/") + "/", pattern.lstrip("/")) for pattern in PATTERNS)
    # De-dupe candidate URLs while preserving priority order.
    candidates = list(dict.fromkeys(candidates))
    pages = []
    reasons = []
    career_url = None
    for url in candidates:
        if len(pages) >= 1:
            break
        try:
            response = client.get(url)
        except DomainBlocked as exc:
            return {"status": "blocked", "reason": str(exc), "pages": [], "career_url": None}
        except DomainRequestLimit as exc:
            reasons.append(str(exc)); break
        except RobotsDisallowed as exc:
            reasons.append(str(exc)); continue
        except Exception as exc:
            reasons.append(str(exc)[:180]); continue
        if response.status_code == 404 or response.status_code == 410:
            continue
        if response.status_code != 200:
            continue
        if _career_content(response):
            career_url = response.url
            pages.append((response.url, response.text))

    # Layer C: robots.txt plus the conventional sitemap and any published Sitemap directives.
    host = urlparse(website).hostname or target["domain"]
    sitemap_urls = ["https://%s/sitemap.xml" % host]
    robots_text = getattr(client, "robots_text", "") or ""
    for line in robots_text.splitlines():
        match = re.match(r"\s*sitemap:\s*(https://\S+)", line, re.I)
        if match:
            sitemap_urls.append(match.group(1))
    sitemap_urls = list(dict.fromkeys(sitemap_urls))
    matching_urls = []
    for sitemap_url in sitemap_urls:
        try:
            response = client.get(sitemap_url)
        except (DomainBlocked, DomainRequestLimit) as exc:
            if isinstance(exc, DomainBlocked):
                return {"status": "blocked", "reason": str(exc), "pages": [], "career_url": career_url}
            reasons.append(str(exc)); break
        except (RobotsDisallowed, Exception) as exc:
            reasons.append(str(exc)[:180]); continue
        if response.status_code != 200 or not response.text:
            continue
        locations = _sitemap_locations(response.text)
        # Support one level of sitemap index while keeping request volume bounded.
        for location in locations:
            if not location.startswith("https://"):
                continue
            if re.search(r"sitemap[^/]*\.xml(?:$|\?)", location, re.I):
                continue
            if SITEMAP_JOB_PATH.search(urlparse(location).path):
                matching_urls.append(location)
            if len(matching_urls) >= 20:
                break
        if not matching_urls and "sitemapindex" in response.text[:5000].lower():
            for nested in locations[:10]:
                try:
                    nested_response = client.get(nested)
                except Exception:
                    continue
                if nested_response.status_code == 200:
                    matching_urls.extend(
                        loc for loc in _sitemap_locations(nested_response.text)
                        if loc.startswith("https://") and SITEMAP_JOB_PATH.search(urlparse(loc).path)
                    )
                if len(matching_urls) >= 20:
                    break
        if len(matching_urls) >= 20:
            break

    # Fetch bounded sitemap job URLs; retain only responses that look like vacancies.
    seen_pages = {url for url, _ in pages}
    for job_url in list(dict.fromkeys(matching_urls))[:20]:
        if job_url in seen_pages:
            continue
        try:
            response = client.get(job_url)
        except DomainBlocked as exc:
            return {"status": "blocked", "reason": str(exc), "pages": pages, "career_url": career_url}
        except Exception as exc:
            reasons.append(str(exc)[:180]); continue
        if response.status_code == 200 and _career_content(response):
            pages.append((response.url, response.text))
            seen_pages.add(response.url)

    if pages:
        return {"status": "ok", "career_url": career_url or pages[0][0], "pages": pages, "status_detail": {"candidate_count": len(candidates), "sitemap_matches": len(matching_urls)}}
    if client.blocked_registry.is_blocked(target["domain"]):
        return {"status": "blocked", "reason": "Domain is in data/blocked_domains.json and requires manual review.", "pages": [], "career_url": None}
    return {
        "status": "no-career-page",
        "reason": "No permitted URL-pattern or sitemap page returned HTTP 200 with career/job keywords.",
        "pages": [],
        "career_url": career_url,
        "status_detail": {"candidate_count": len(candidates), "sitemap_matches": len(matching_urls), "discovery_notes": reasons[:5]},
    }
