"""Selector fallback for the healthcare employer category."""
from ..generic_parser import GenericCompanyParser


class HealthcareParser(GenericCompanyParser):
    extra_card_selectors = (
        "[data-job-id]",
        "[class*='career']",
        "[class*='job-list']",
        "[class*='vacancy']",
        "[class*='position']",
    )
