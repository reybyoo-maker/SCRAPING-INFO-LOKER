"""Permission-gated adapter for the unverified Karir.com API candidate.

The current adapter is intentionally disabled in config.yaml. Karir.com's terms prohibit
automated collection without permission, and the endpoint contract has not been published
in official developer documentation. It must not be enabled until the site owner authorizes
this use. No live endpoint probe is performed by tests.
"""
from __future__ import annotations

import json
import logging
from urllib.parse import urljoin, urlparse

import requests

from .base import BaseScraper, SourceNotAllowed, clean, parse_iso

logger = logging.getLogger("info-loker.scrapers.karir")


class KarirScraper(BaseScraper):
    source_id = "karir"
    source_label = "Karir.com API"
    base_domain = "karir.com"

    def fetch(self):
        if not self.enabled:
            logger.info("%s skipped: disabled in config.yaml", self.source_id)
            return None
        if not self.authorized:
            raise SourceNotAllowed(
                "Karir.com API is inactive until written permission or official API authorization is obtained"
            )

        url = self.build_url()
        if not self.robots_allowed(url):
            raise SourceNotAllowed(
                "Karir.com API skipped because robots.txt blocks the endpoint or could not be verified"
            )

        try:
            page_size = min(100, max(1, int(self.settings.get("page_size", 50))))
        except (TypeError, ValueError):
            page_size = 50
        response = self._paced_post(
            self.session,
            url,
            self.timeout,
            json={"keyword": self.keyword, "limit": page_size, "offset": 0},
            min_delay_seconds=self.min_delay_seconds,
            max_delay_seconds=self.max_delay_seconds,
        )
        if response.status_code in (403, 429):
            raise requests.HTTPError(
                f"{self.source_id} API blocked the request with HTTP {response.status_code}; "
                "source will be logged as blocked and no access-control workaround will be attempted",
                response=response,
            )
        if response.status_code >= 400:
            raise requests.HTTPError(f"{self.source_id} API returned HTTP {response.status_code}", response=response)
        final = urlparse(response.url)
        root = self.base_domain.lower().lstrip(".")
        host = (final.hostname or "").lower()
        if not (host == root or host.endswith("." + root)):
            raise SourceNotAllowed("Karir.com API redirect left the declared source domain")
        return response.text

    @staticmethod
    def _extract_items(payload):
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []
        for key in ("opportunities", "items", "results", "jobs", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested = KarirScraper._extract_items(value)
                if nested:
                    return nested
        return []

    @staticmethod
    def _text_value(value):
        if isinstance(value, dict):
            return clean(
                value.get("name") or value.get("title") or value.get("label")
                or value.get("city") or value.get("province") or value.get("value"),
                240,
            )
        if isinstance(value, list):
            return ", ".join(filter(None, (KarirScraper._text_value(item) for item in value)))
        return clean(value, 500)

    def parse(self, document):
        if not document:
            return []
        try:
            payload = json.loads(document)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Karir.com API response was not valid JSON")
            return []

        rows = []
        seen = set()
        for item in self._extract_items(payload):
            title = item.get("title") or item.get("name") or item.get("job_title") or item.get("position")
            company = self._text_value(
                item.get("company") or item.get("company_name") or item.get("employer")
            )
            location = self._text_value(
                item.get("location") or item.get("location_name") or item.get("city")
            )
            url_value = (
                item.get("url") or item.get("job_url") or item.get("detail_url")
                or item.get("public_url") or item.get("link") or item.get("apply_url")
            )
            if not url_value:
                # Do not invent a detail-route format from an undocumented endpoint schema.
                continue
            url = urljoin("https://www.karir.com/", str(url_value).strip())
            posted_at = item.get("posted_at") or item.get("published_at") or item.get("created_at") or item.get("publishedAt")
            salary = self._text_value(item.get("salary") or item.get("salary_range") or item.get("salary_text"))
            job_type = item.get("job_type") or item.get("employment_type") or item.get("employmentType")
            description = item.get("description") or item.get("summary") or item.get("excerpt")
            record = self._normalize_job(
                title=title,
                company=company,
                location=location,
                url=url,
                posted_at=parse_iso(posted_at),
                salary=salary or None,
                job_type=job_type,
                description=description,
            )
            if record and record["url"] not in seen:
                record["source_type"] = "permission_gated_json_api"
                rows.append(record)
                seen.add(record["url"])
        return rows
