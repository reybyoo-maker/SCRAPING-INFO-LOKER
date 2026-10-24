"""Selector override for Mayora; generic JSON-LD and URL heuristics remain available."""
from ..generic_parser import GenericCompanyParser


class MayoraParser(GenericCompanyParser):
    extra_card_selectors = (
        "[data-job-id]",
        ".career-listing",
        ".job-listing",
        ".vacancy",
        "[class*='position']",
    )
