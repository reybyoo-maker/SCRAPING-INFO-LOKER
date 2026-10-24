"""Public Dealls listing adapter.

The collector reads listing metadata and keeps links to the original vacancy page.
It does not log in, probe private APIs, or bypass access controls.
"""
from __future__ import annotations

import re
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup

from .base import BaseScraper, clean


class DeallsScraper(BaseScraper):
    source_id = "dealls"
    source_label = "Dealls"
    base_domain = "dealls.com"
    card_selectors = (
        "[data-testid*='job']",
        "[class*='JobCard']",
        "[class*='job-card']",
        "article",
    )

    def fetch(self):
        return super().fetch()

    @staticmethod
    def _title_from_slug(value: str) -> str:
        text = unquote(value).replace("-", " ").replace("_", " ")
        text = re.sub(r"\s+", " ", text).strip()
        return " ".join(
            word.upper() if word.lower() in {"hr", "it", "ui", "ux", "seo", "ai", "qa"}
            else word.capitalize()
            for word in text.split()
        )

    @staticmethod
    def _company_from_slug(value: str) -> str:
        text = unquote(value).replace("-", " ").replace("_", " ")
        text = re.sub(r"\s+", " ", text).strip()
        abbreviations = {"pt": "PT", "cv": "CV", "tbk": "Tbk", "ud": "UD", "bumd": "BUMD", "bumn": "BUMN"}
        return " ".join(
            abbreviations.get(word.lower(), word.capitalize())
            for word in text.split()
        )

    @staticmethod
    def _card_for(anchor):
        candidates = []
        for parent in anchor.parents:
            if getattr(parent, "name", "") in ("body", "html"):
                break
            text = clean(parent.get_text(" ", strip=True))
            if len(text) > 35:
                candidates.append((parent, text))
                if len(text) >= 80 and len(text) <= 1200:
                    # A job card often includes employment type or location/salary metadata.
                    if re.search(r"(?:Rp\s*[\d.,]+|on-site|onsite|hybrid|remote|penuh waktu|kontrak|magang|part time)", text, re.I):
                        return parent, text
        if candidates:
            # The final candidate is the largest nearby container; cap the extraction length.
            return candidates[0]
        return anchor, clean(anchor.get_text(" ", strip=True))

    def parse(self, document):
        if not document:
            return []
        soup = BeautifulSoup(document, "html.parser")
        rows = []
        seen = set()

        for anchor in soup.select("a[href]"):
            href = str(anchor.get("href", "")).strip()
            parsed = urlparse(urljoin("https://dealls.com/", href))
            path = unquote(parsed.path)
            # Dealls job detail routes use /loker/{title-slug}~{company-slug}.
            match = re.fullmatch(r"/loker/([^/?#~]+)~([^/?#]+)", path.rstrip("/"))
            if not match:
                continue
            url = parsed._replace(query="", fragment="").geturl()
            if url in seen or not self._same_domain(url):
                continue

            title_slug, company_slug = match.groups()
            card, card_text = self._card_for(anchor)
            title_node = card.select_one("h1, h2, h3, [class*='job-title'], [data-testid*='title']")
            anchor_title = clean(anchor.get_text(" ", strip=True), 180)
            if title_node:
                title = clean(title_node.get_text(" ", strip=True), 250)
            elif anchor_title and len(anchor_title) <= 150 and not re.search(
                r"(?:Rp\s*[\d.,]+|on-site|onsite|hybrid|remote|pelamar|rekruter aktif)",
                anchor_title,
                re.I,
            ):
                title = anchor_title
            else:
                title = self._title_from_slug(title_slug)

            company = ""
            company_node = card.select_one("[class*='company'], [data-testid*='company'], [class*='employer']")
            if company_node:
                company = clean(company_node.get_text(" ", strip=True), 160)
            if not company or company.lower() in {"company", "perusahaan"}:
                company = self._company_from_slug(company_slug)

            location = ""
            location_node = card.select_one("[class*='location'], [data-testid*='location'], [aria-label*='location']")
            if location_node:
                location = clean(location_node.get_text(" ", strip=True), 220)
            if not location:
                match_location = re.search(
                    r"(?:On-site|Onsite|Hybrid|Remote|WFH|WFO)\s*[•·-]\s*([^|]{2,100}?)(?=\s+(?:Min\.|Fresh Grad|Rp\s*[\d.,]+|Rekruter aktif|Penuh waktu|Kontrak|Magang|Full[- ]?time)|$)",
                    card_text,
                    re.I,
                )
                if match_location:
                    location = clean(match_location.group(1), 220)

            salary_match = re.search(
                r"Rp\s*[\d.]+(?:,[\d]{1,2})?(?:\s*[–—-]\s*(?:Rp\s*)?[\d.]+(?:,[\d]{1,2})?)?",
                card_text,
                re.I,
            )
            salary = clean(salary_match.group(0), 100) if salary_match else None
            date_node = card.select_one("time[datetime]")
            posted_at = date_node.get("datetime") if date_node else None

            record = self._normalize_job(
                title=title,
                company=company,
                location=location,
                url=url,
                posted_at=posted_at,
                salary=salary,
                job_type=card_text,
                description=card_text,
            )
            if record:
                rows.append(record)
                seen.add(url)

        # Keep the generic JSON-LD/HTML parser as a fallback for future markup variants.
        if not rows:
            rows = self.parse_listing_page(document)
        return rows
