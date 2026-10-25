"""Selector override for Freeport Indonesia; generic JSON-LD and URL heuristics remain available."""
from ..generic_parser import GenericCompanyParser


class FreeportParser(GenericCompanyParser):
    extra_card_selectors = (
        "[data-job-id]",
        ".career-listing",
        ".job-listing",
        ".vacancy",
        "[class*='job-card']",
    )
