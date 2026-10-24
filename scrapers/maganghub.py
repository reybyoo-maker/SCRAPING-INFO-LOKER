from .base import BaseScraper


class MaganghubScraper(BaseScraper):
    source_id = "maganghub"
    source_label = "Maganghub"
    base_domain = "maganghub.kemnaker.go.id"
    card_selectors = ("[data-testid*='intern']", "[class*='magang']", "[class*='internship']", "article", "li")

    def fetch(self):
        return super().fetch()

    def parse(self, document):
        return self.parse_listing_page(document)
