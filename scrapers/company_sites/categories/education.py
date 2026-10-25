"""Selector fallback for the education employer category."""
from ..generic_parser import GenericCompanyParser


class EducationParser(GenericCompanyParser):
    extra_card_selectors = (
        "[data-job-id]",
        "[class*='career']",
        "[class*='position']",
        "[class*='job-list']",
        "article",
    )
