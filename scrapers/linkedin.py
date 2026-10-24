from .base import BaseScraper


class LinkedinScraper(BaseScraper):
    source_id = "linkedin"
    source_label = "LinkedIn Jobs"
    base_domain = "linkedin.com"
    card_selectors = (".job-card-container", ".jobs-search-results__list-item", "li[data-occludable-job-id]")

    def fetch(self):
        # LinkedIn requires authorized access; this adapter does not bypass its controls.
        return super().fetch()

    def parse(self, document):
        return self.parse_listing_page(document)
