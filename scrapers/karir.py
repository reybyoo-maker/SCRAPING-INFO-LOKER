from .base import BaseScraper


class KarirScraper(BaseScraper):
    source_id = "karir"
    source_label = "Karir.com"
    base_domain = "karir.com"
    card_selectors = ("[data-testid*='job']", ".job-item", ".job-card", "article", "li")

    def fetch(self):
        return super().fetch()

    def parse(self, document):
        return self.parse_listing_page(document)
