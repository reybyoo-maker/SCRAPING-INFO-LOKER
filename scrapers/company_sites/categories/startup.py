"""Selector fallback for the startup employer category."""
from ..generic_parser import GenericCompanyParser


class StartupParser(GenericCompanyParser):
    extra_card_selectors = (
        "[data-testid*='job']",
        "[data-qa*='job']",
        "[class*='opening']",
        "[class*='posting']",
        "[class*='role-card']",
    )
