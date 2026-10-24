from urllib.parse import urljoin
import re

from bs4 import BeautifulSoup

from .base import BaseScraper, clean


class KalibrrScraper(BaseScraper):
    source_id = "kalibrr"
    source_label = "Kalibrr"
    # Kalibrr's Indonesian public job board moved to kalibrr.id in 2026.
    base_domain = "kalibrr.id"
    card_selectors = (
        "a[href*='/c/'][href*='/jobs/']",
        "[data-testid*='job']",
        "[class*='job-card']",
        "[class*='JobCard']",
        "article",
    )
    title_selectors = ("h2", "h3", "[class*='title']", "[data-testid*='title']")
    company_selectors = ("[class*='company']", "[data-testid*='company']")
    location_selectors = ("[class*='location']", "[data-testid*='location']")
    salary_selectors = ("[class*='salary']", "[data-testid*='salary']")
    date_selectors = ("time[datetime]", "time", "[class*='posted']")

    def fetch(self):
        return super().fetch()

    def parse(self, document):
        if not document:
            return []
        soup = BeautifulSoup(document, "html.parser")
        rows = []
        seen = set()
        for title_link in soup.select("a[href*='/c/'][href*='/jobs/']"):
            url = urljoin("https://www.kalibrr.id/", str(title_link.get("href", "")))
            if url in seen or not self._same_domain(url):
                continue
            title_node = title_link.select_one("h1, h2, h3, [class*='title']")
            title = clean(title_node.get_text(" ", strip=True) if title_node else title_link.get_text(" ", strip=True), 250)
            if not title:
                continue

            card = title_link
            for _ in range(5):
                parent = card.parent
                if parent is None:
                    break
                card = parent
                card_text = clean(card.get_text(" ", strip=True), 1200)
                if len(card_text) > len(title) + 30:
                    break

            company = ""
            for company_link in card.select("a[href*='/c/']"):
                company_href = str(company_link.get("href", ""))
                if "/jobs/" not in company_href and clean(company_link.get_text(" ", strip=True)):
                    company = clean(company_link.get_text(" ", strip=True), 160)
                    break
            location = self._first_text(card, self.location_selectors)
            if not location:
                match = re.search(r"([A-Z][^|]{0,90}?,\s*(?:Indonesia|Philippines|United States|Singapore|Malaysia))", card.get_text(" ", strip=True))
                location = match.group(1) if match else ""
            salary = self._first_text(card, self.salary_selectors)
            if not salary:
                match = re.search(r"(?:IDR|PHP|USD|SGD|MYR)\s*[\d,.]+(?:\s*[-–]\s*(?:IDR|PHP|USD|SGD|MYR)?\s*[\d,.]+)?(?:\s*/\s*month)?", card.get_text(" ", strip=True))
                salary = match.group(0) if match else None
            posted = self._first_text(card, self.date_selectors)
            snippet = clean(card.get_text(" ", strip=True), 300)
            record = self._normalize_job(
                title=title,
                company=company,
                location=location,
                url=url,
                posted_at=posted,
                salary=salary,
                job_type=clean(card.get_text(" ", strip=True), 240),
                description=snippet,
            )
            if record:
                rows.append(record)
                seen.add(url)
        # JSON-LD is retained as a fallback when Kalibrr changes its card markup.
        if not rows:
            rows = self.parse_listing_page(document)
        return rows
