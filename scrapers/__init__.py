"""Authorized, robots-aware site adapters for INFO LOKER Indonesia."""
from .base import BaseScraper, SourceNotAllowed
from .jobstreet import JobstreetScraper
from .indeed import IndeedScraper
from .glints import GlintsScraper
from .kalibrr import KalibrrScraper
from .karir import KarirScraper
from .dealls import DeallsScraper
from .linkedin import LinkedinScraper
from .lokerid import LokeridScraper
from .disnakerja import DisnakerjaScraper
from .techinasia import TechinasiaScraper
from .maganghub import MaganghubScraper

SCRAPER_CLASSES = (
    JobstreetScraper,
    IndeedScraper,
    GlintsScraper,
    KalibrrScraper,
    KarirScraper,
    DeallsScraper,
    LinkedinScraper,
    LokeridScraper,
    DisnakerjaScraper,
    TechinasiaScraper,
    MaganghubScraper,
)

__all__ = ["BaseScraper", "SourceNotAllowed", "SCRAPER_CLASSES"]
