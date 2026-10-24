"""Selector override for Astra; generic JSON-LD and URL heuristics remain available."""
from ..generic_parser import GenericCompanyParser


class AstraParser(GenericCompanyParser):
    extra_card_selectors = (
        "[data-qa='job-listing']",
        "[data-testid*='job-card']",
        ".job-listing",
        ".career-opportunity",
        ".opening",
        "[class*='vacancy']",
    )
