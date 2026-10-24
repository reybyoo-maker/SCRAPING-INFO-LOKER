"""Selector override for Traveloka; generic JSON-LD and URL heuristics remain available."""
from ..generic_parser import GenericCompanyParser


class TravelokaParser(GenericCompanyParser):
    extra_card_selectors = (
        "[data-testid*='job']",
        "[class*='job-card']",
        ".opening",
        ".job-listing",
        "article",
    )
