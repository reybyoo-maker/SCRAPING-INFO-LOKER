"""Selector override for Bukalapak; generic JSON-LD and URL heuristics remain available."""
from ..generic_parser import GenericCompanyParser


class BukalapakParser(GenericCompanyParser):
    extra_card_selectors = (
        "[data-testid*='job']",
        ".opening",
        ".posting",
        ".job-post",
        "[class*='career']",
    )
