"""Selector override for Kalbe Farma; generic JSON-LD and URL heuristics remain available."""
from ..generic_parser import GenericCompanyParser


class KalbeParser(GenericCompanyParser):
    extra_card_selectors = (
        "[data-job-id]",
        ".career-listing",
        ".job-listing",
        ".vacancy",
        "[class*='position']",
    )
