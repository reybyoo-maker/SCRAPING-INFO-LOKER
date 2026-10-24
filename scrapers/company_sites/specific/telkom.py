"""Selector override for Telkom; generic JSON-LD and URL heuristics remain available."""
from ..generic_parser import GenericCompanyParser


class TelkomParser(GenericCompanyParser):
    extra_card_selectors = (
        "[data-job-id]",
        ".job-list",
        ".job-listing",
        ".vacancy-item",
        "[class*='career-item']",
    )
