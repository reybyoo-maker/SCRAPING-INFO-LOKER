from .base import BaseScraper


class IndeedScraper(BaseScraper):
    source_id = "indeed"
    source_label = "Indeed Indonesia"
    base_domain = "indeed.com"
    card_selectors = ("[data-jk]", ".job_seen_beacon", ".jobsearch-ResultsList li", "td.resultContent", "article")

    def fetch(self):
        return super().fetch()

    def parse(self, document):
        return self.parse_listing_page(document)
