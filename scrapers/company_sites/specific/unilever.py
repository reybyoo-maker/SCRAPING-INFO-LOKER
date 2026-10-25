"""Selector override for Unilever; generic JSON-LD and URL heuristics remain available."""
from ..generic_parser import GenericCompanyParser


class UnileverParser(GenericCompanyParser):
    extra_card_selectors = (
        "[data-ph-at-id='job-results']",
        "[data-automation-id*='job']",
        ".job-tile",
        ".job-card",
        "[class*='job-listing']",
    )
