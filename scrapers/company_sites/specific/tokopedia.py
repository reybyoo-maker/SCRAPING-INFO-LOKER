"""Selector override for Tokopedia; generic JSON-LD and URL heuristics remain available."""
from ..generic_parser import GenericCompanyParser


class TokopediaParser(GenericCompanyParser):
    extra_card_selectors = (
        "[data-testid*='job']",
        ".opening",
        ".posting",
        ".job-post",
        "[class*='opportunity']",
    )
