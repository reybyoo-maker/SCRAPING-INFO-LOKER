"""Generic job-listing parser for official company careers pages."""
from __future__ import annotations

import hashlib
import json
import logging
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..base import clean, parse_iso, canonical_job_type

logger = logging.getLogger("info-loker.company-sites.parser")
JOB_PATH_RE = re.compile(r"(?:career|careers|karir|karier|jobs?|lowongan|loker|vacan(?:cy|cies)?|hiring|opportunit|opening|position|requisition|job[-_/])", re.I)
JOB_TEXT_RE = re.compile(r"\b(?:job|karir|karier|career|lowongan|vacancy|vacancies|hiring|opportunity|opportunities|position|recruitment|rekrutmen)\b", re.I)


class GenericCompanyParser:
    extra_card_selectors = ()

    def __init__(self, target: dict):
        self.target = target
        self.company = str(target.get("name") or "")
        self.domain = str(target.get("domain") or "").lower()
        self.category = str(target.get("category") or "Corporate")

    @staticmethod
    def _text(node, selectors, limit=300):
        for selector in selectors:
            found = node.select_one(selector)
            if found:
                value = clean(found.get("datetime") or found.get_text(" ", strip=True), limit)
                if value:
                    return value
        return ""

    def _record(self, title, location, url, posted_at=None, salary=None, job_type=None, description=None):
        title = clean(title, 250)
        url = str(url or "").strip()
        parsed = urlparse(url)
        if not title or len(title) < 5 or parsed.scheme != "https" or not parsed.hostname:
            return None
        if not JOB_TEXT_RE.search(title) and title.lower() in {"careers", "career", "jobs", "job openings", "join us", "join our team"}:
            return None
        identity = hashlib.sha256((url + "|" + title + "|" + self.company).encode("utf-8")).hexdigest()[:16]
        posted = parse_iso(posted_at)
        salary_text = clean(salary, 120) or None
        description_text = clean(description, 300)
        kind = canonical_job_type(job_type)
        score = 30 + 20 * bool(self.company) + 15 * bool(location) + 15 * bool(posted) + 10 * bool(salary_text) + 10 * bool(description_text)
        label = "HOT" if score >= 80 else "MEDIUM" if score >= 50 else "LOW"
        domain_source = self.domain
        return {
            "id": identity,
            "title": title,
            "company": self.company,
            "company_name": self.company,
            "location": clean(location, 220),
            "location_label": clean(location, 220) or None,
            "city": None,
            "province": None,
            "source": "company:%s" % domain_source,
            "source_name": self.company,
            "source_group": "Company Sites",
            "source_type": "company_career_page",
            "category": self.category,
            "company_domain": domain_source,
            "url": url,
            "listing_url": url,
            "application_url": url,
            "posted_at": posted,
            "published_at": posted,
            "source_updated_at": posted,
            "salary": salary_text,
            "salary_text": salary_text,
            "job_type": kind,
            "employment_type": job_type or kind,
            "description_snippet": description_text,
            "description_excerpt": description_text,
            "scraped_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "last_seen_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "listing_state": "active_unverified",
            "work_mode": "Unknown",
            "is_remote": None,
            "quality_score": score,
            "quality_label": label,
            "quality_explanation": ["Official company career page or sitemap link; vacancy status and employer authenticity are not independently guaranteed by this parser."],
            "risk_flags": [],
        }

    def _jsonld(self, soup: BeautifulSoup, page_url: str):
        records = []
        def walk(value):
            if isinstance(value, list):
                for item in value: walk(item)
                return
            if not isinstance(value, dict):
                return
            kind = value.get("@type", [])
            if isinstance(kind, str): kind = [kind]
            if "JobPosting" in kind:
                org = value.get("hiringOrganization") or {}
                company = org.get("name") if isinstance(org, dict) else org
                location_obj = value.get("jobLocation") or {}
                if isinstance(location_obj, list): location_obj = location_obj[0] if location_obj else {}
                address = location_obj.get("address", {}) if isinstance(location_obj, dict) else {}
                if isinstance(address, list): address = address[0] if address else {}
                if isinstance(address, dict):
                    location = ", ".join(filter(None, [clean(address.get("addressLocality")), clean(address.get("addressRegion")), clean(address.get("addressCountry"))]))
                else:
                    location = clean(address)
                url = urljoin(page_url, str(value.get("url") or value.get("sameAs") or page_url))
                # The curated target name is authoritative for the company field.
                # The structured-data hiringOrganization may be a subsidiary or ATS vendor.
                record = self._record(
                    value.get("title") or value.get("name"), location, url,
                    value.get("datePosted"), value.get("baseSalary"), value.get("employmentType"), value.get("description")
                )
                if record: records.append(record)
            for key in ("@graph", "mainEntity", "itemListElement", "mainEntityOfPage"):
                if key in value: walk(value[key])
        for script in soup.select('script[type="application/ld+json"]'):
            try: walk(json.loads(script.string or script.get_text()))
            except (json.JSONDecodeError, TypeError, ValueError): continue
        return records

    def parse(self, html: str, page_url: str) -> list[dict]:
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        records = self._jsonld(soup, page_url)
        seen = {record["url"] for record in records}
        selectors = list(self.extra_card_selectors) + [
            "[data-job-id]", "[data-testid*='job']", "[data-automation*='job']",
            "div[class*='job']", "li[class*='job']", "article[class*='job']",
            "div[class*='career']", "li[class*='career']", "div[class*='vacan']",
            "div[class*='position']", "li[class*='opening']", "article",
            "ul li", "[data-position-id]", "[data-requisition-id]"
        ]
        checked_nodes = set()
        for selector in selectors:
            try: nodes = soup.select(selector)
            except Exception: continue
            for node in nodes:
                marker = id(node)
                if marker in checked_nodes: continue
                checked_nodes.add(marker)
                anchors = node.find_all("a", href=True) if getattr(node, "find_all", None) else []
                if getattr(node, "name", "") == "a" and node.get("href"): anchors = [node]
                text_all = clean(node.get_text(" ", strip=True), 1600)
                for anchor in anchors[:6]:
                    title_node = anchor.select_one("h1,h2,h3,h4,[class*='title'],[data-testid*='title'],[data-job-title]")
                    title = clean(title_node.get_text(" ", strip=True) if title_node else anchor.get_text(" ", strip=True), 250)
                    url = urljoin(page_url, str(anchor.get("href", "")).strip())
                    if url in seen or not title or len(title) < 5:
                        continue
                    path = urlparse(url).path
                    # A card is acceptable either from a job-like URL or from a job-like card.
                    if not JOB_PATH_RE.search(path) and not JOB_TEXT_RE.search(text_all):
                        continue
                    if title.lower() in {"career", "careers", "job", "jobs", "join us", "join our team", "view all", "learn more", "read more", "apply now"}:
                        continue
                    location = self._text(node, (
                        "[class*='location']", "[data-testid*='location']", "[data-automation*='location']",
                        "[itemprop='jobLocation']", "address", "time[datetime]"
                    ), 220)
                    posted = self._text(node, ("time[datetime]", "[class*='posted']", "[class*='date']"), 180)
                    salary = self._text(node, ("[class*='salary']", "[class*='compensation']", "[data-testid*='salary']"), 120)
                    job_type = self._text(node, ("[class*='employment']", "[class*='job-type']", "[data-testid*='type']"), 100)
                    record = self._record(title, location, url, posted, salary, job_type, text_all)
                    if record:
                        records.append(record); seen.add(url)
        # Fallback heuristic: anchors whose URL/path looks like a specific role, not broad navigation.
        if not records:
            for anchor in soup.select("a[href]"):
                title = clean(anchor.get_text(" ", strip=True), 250)
                url = urljoin(page_url, str(anchor.get("href", "")).strip())
                if url in seen or len(title) < 6 or not JOB_PATH_RE.search(urlparse(url).path):
                    continue
                if title.lower() in {"careers", "jobs", "job search", "join us", "learn more", "view all", "apply now"}:
                    continue
                record = self._record(title, "", url, description=clean(anchor.parent.get_text(" ", strip=True), 300) if anchor.parent else None)
                if record:
                    records.append(record); seen.add(url)
        # Keep only unique URLs per employer to avoid card-selector duplication.
        unique = {}
        for record in records: unique.setdefault(record["url"], record)
        return list(unique.values())
