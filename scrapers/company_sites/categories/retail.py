"""Selector fallback for the retail employer category."""
from ..generic_parser import GenericCompanyParser


class RetailParser(GenericCompanyParser):
    extra_card_selectors = (
        "[data-job-id]",
        "[class*='job-card']",
        "[class*='career']",
        "[class*='opening']",
        "[class*='position']",
    )
