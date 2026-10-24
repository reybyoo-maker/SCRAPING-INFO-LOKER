from .base import BaseScraper


class GlintsScraper(BaseScraper):
    source_id = "glints"
    source_label = "Glints"
    base_domain = "glints.com"
    card_selectors = ("[data-testid*='job-card']", "[data-qa*='job-card']", "article", ".job-card")

    def fetch(self):
        # Uses ordinary HTML requests only; dynamic pages may return no records.
        return super().fetch()

    def parse(self, document):
        return self.parse_listing_page(document)
