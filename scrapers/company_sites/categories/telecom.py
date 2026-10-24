"""Selector fallback for the telecom employer category."""
from ..generic_parser import GenericCompanyParser


class TelecomParser(GenericCompanyParser):
    extra_card_selectors = (
        "[data-job-id]",
        "[class*='job-list']",
        "[class*='career-list']",
        "[class*='vacancy']",
        "article",
    )
