"""Selector override for Shopee; generic JSON-LD and URL heuristics remain available."""
from ..generic_parser import GenericCompanyParser


class ShopeeParser(GenericCompanyParser):
    extra_card_selectors = (
        "[data-qa='job-card']",
        "[data-testid*='job']",
        ".job-card",
        ".job-listing",
        "article",
    )
