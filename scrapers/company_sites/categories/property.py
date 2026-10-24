"""Selector fallback for the property employer category."""
from ..generic_parser import GenericCompanyParser


class PropertyParser(GenericCompanyParser):
    extra_card_selectors = (
        "[data-job-id]",
        "[class*='career']",
        "[class*='job-list']",
        "[class*='position']",
        "article",
    )
