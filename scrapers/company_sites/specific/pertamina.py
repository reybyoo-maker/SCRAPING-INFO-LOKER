"""Selector override for Pertamina; generic JSON-LD and URL heuristics remain available."""
from ..generic_parser import GenericCompanyParser


class PertaminaParser(GenericCompanyParser):
    extra_card_selectors = (
        "[data-job-id]",
        ".job-listing",
        ".vacancy",
        ".career-card",
        "[class*='job-item']",
    )
