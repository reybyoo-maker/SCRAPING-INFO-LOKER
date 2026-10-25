"""Selector fallback for the fintech employer category."""
from ..generic_parser import GenericCompanyParser


class FintechParser(GenericCompanyParser):
    extra_card_selectors = (
        "[data-testid*='job']",
        "[data-job-id]",
        "[class*='opening']",
        "[class*='position']",
        ".career-card",
    )
