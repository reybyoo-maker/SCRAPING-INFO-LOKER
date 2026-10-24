from .base import BaseScraper


class DisnakerjaScraper(BaseScraper):
    source_id = "disnakerja"
    source_label = "Disnakerja"
    base_domain = "disnakerja.com"
    card_selectors = (".job-listing", ".job-item", ".job-card", "article", "li")

    def fetch(self):
        return super().fetch()

    def parse(self, document):
        return self.parse_listing_page(document)
