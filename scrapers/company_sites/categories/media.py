"""Selector fallback for the media employer category."""
from ..generic_parser import GenericCompanyParser


class MediaParser(GenericCompanyParser):
    extra_card_selectors = (
        "[data-job-id]",
        "[class*='career']",
        "[class*='job-list']",
        "[class*='opening']",
        "article",
    )
