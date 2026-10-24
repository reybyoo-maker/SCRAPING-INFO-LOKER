"""Selector fallback for the bank fintech employer category."""
from ..generic_parser import GenericCompanyParser


class BankFintechParser(GenericCompanyParser):
    extra_card_selectors = (
        "[class*='job']",
        "[class*='career']",
        "[data-job-id]",
        "li[class*='position']",
        ".vacancy-card",
    )
