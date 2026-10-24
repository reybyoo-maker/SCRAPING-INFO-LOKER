from .base import BaseScraper


class DeallsScraper(BaseScraper):
    source_id = "dealls"
    source_label = "Dealls"
    base_domain = "dealls.com"
    card_selectors = ("[data-testid*='job']", "[class*='JobCard']", "[class*='job-card']", "article")

    def fetch(self):
        # Does not probe private/internal JSON endpoints.
        return super().fetch()

    def parse(self, document):
        return self.parse_listing_page(document)
