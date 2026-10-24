"""Selector fallback for the corporate employer category."""
from ..generic_parser import GenericCompanyParser


class CorporateParser(GenericCompanyParser):
    extra_card_selectors = (
        "[data-job-id]",
        "[data-requisition-id]",
        "[class*='job-card']",
        "[class*='career']",
        "[class*='vacancy']",
    )
