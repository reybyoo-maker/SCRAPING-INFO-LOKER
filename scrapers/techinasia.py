from .base import BaseScraper


class TechinasiaScraper(BaseScraper):
    source_id = "techinasia"
    source_label = "Tech in Asia Jobs"
    base_domain = "techinasia.com"
    card_selectors = ("[data-testid*='job']", "[class*='job-card']", "article", "li")

    def fetch(self):
        return super().fetch()

    def parse(self, document):
        return self.parse_listing_page(document)
