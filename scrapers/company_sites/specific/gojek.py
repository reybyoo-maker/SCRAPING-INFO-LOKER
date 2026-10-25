"""Selector override for Gojek; generic JSON-LD and URL heuristics remain available."""
from ..generic_parser import GenericCompanyParser


class GojekParser(GenericCompanyParser):
    extra_card_selectors = (
        "[data-testid*='job']",
        ".opening",
        ".posting",
        ".job-post",
        "[class*='job-card']",
    )
