"""Selector override for Telkomsel; generic JSON-LD and URL heuristics remain available."""
from ..generic_parser import GenericCompanyParser


class TelkomselParser(GenericCompanyParser):
    extra_card_selectors = (
        "[data-job-id]",
        ".job-listing",
        ".career-item",
        ".vacancy",
        "[class*='career-card']",
    )
