from .base import BaseScraper


class KalibrrScraper(BaseScraper):
    source_id = "kalibrr"
    source_label = "Kalibrr"
    base_domain = "kalibrr.com"
    card_selectors = ("[data-testid*='job']", "[class*='job-card']", "article", "li")

    def fetch(self):
        return super().fetch()

    def parse(self, document):
        return self.parse_listing_page(document)
