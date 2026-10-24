"""Selector fallback for the transport logistics employer category."""
from ..generic_parser import GenericCompanyParser


class TransportLogisticsParser(GenericCompanyParser):
    extra_card_selectors = (
        "[data-job-id]",
        "[class*='job-list']",
        "[class*='opening']",
        "[class*='career']",
        "[class*='position']",
    )
