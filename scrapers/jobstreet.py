from .base import BaseScraper


class JobstreetScraper(BaseScraper):
    source_id = "jobstreet"
    source_label = "JobStreet"
    base_domain = "jobstreet.com"
    card_selectors = ("[data-automation='normalJob']", "[data-automation*='jobListing']", "article", "li[data-job-id]", ".job-card")

    def fetch(self):
        return super().fetch()

    def parse(self, document):
        return self.parse_listing_page(document)
