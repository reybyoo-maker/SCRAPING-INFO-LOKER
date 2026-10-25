"""Selector override for Bank Mandiri; generic JSON-LD and URL heuristics remain available."""
from ..generic_parser import GenericCompanyParser


class MandiriParser(GenericCompanyParser):
    extra_card_selectors = (
        "[data-job-id]",
        ".job-listing",
        ".vacancy",
        ".career-card",
        "[class*='job-item']",
    )
