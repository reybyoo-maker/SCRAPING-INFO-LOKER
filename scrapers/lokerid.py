from .base import BaseScraper


class LokeridScraper(BaseScraper):
    source_id = "lokerid"
    source_label = "Loker.id"
    base_domain = "loker.id"
    card_selectors = (".job-listing", ".job-item", ".job-card", "article", "li")

    def fetch(self):
        return super().fetch()

    def parse(self, document):
        return self.parse_listing_page(document)
