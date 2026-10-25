"""Selector fallback for the manufacturing employer category."""
from ..generic_parser import GenericCompanyParser


class ManufacturingParser(GenericCompanyParser):
    extra_card_selectors = (
        "[data-job-id]",
        "[class*='vacancy']",
        "[class*='career']",
        "[class*='job-list']",
        "[class*='recruitment']",
    )
