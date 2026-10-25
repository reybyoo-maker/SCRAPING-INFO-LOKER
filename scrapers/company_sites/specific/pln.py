"""Selector override for PLN; generic JSON-LD and URL heuristics remain available."""
from ..generic_parser import GenericCompanyParser


class PlnParser(GenericCompanyParser):
    extra_card_selectors = (
        "[data-job-id]",
        ".vacancy-item",
        ".career-list",
        ".job-listing",
        "[class*='lowongan']",
    )
