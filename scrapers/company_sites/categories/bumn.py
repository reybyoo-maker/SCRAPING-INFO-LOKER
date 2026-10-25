"""Selector fallback for the bumn employer category."""
from ..generic_parser import GenericCompanyParser


class BumnParser(GenericCompanyParser):
    extra_card_selectors = (
        "[data-job-id]",
        "[class*='lowongan']",
        "[class*='vacancy']",
        "[class*='recruitment']",
        "[class*='career']",
    )
