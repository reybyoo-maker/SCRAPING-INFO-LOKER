"""Category-specific selector fallback for company career sites."""
from .bank_fintech import BankFintechParser
from .fintech import FintechParser
from .telecom import TelecomParser
from .startup import StartupParser
from .corporate import CorporateParser
from .healthcare import HealthcareParser
from .property import PropertyParser
from .manufacturing import ManufacturingParser
from .bumn import BumnParser
from .retail import RetailParser
from .transport_logistics import TransportLogisticsParser
from .education import EducationParser
from .media import MediaParser

CATEGORY_PARSERS = {
    "Bank & Fintech": BankFintechParser,
    "Fintech": FintechParser,
    "Telecom": TelecomParser,
    "Startup": StartupParser,
    "Corporate": CorporateParser,
    "Healthcare": HealthcareParser,
    "Properti": PropertyParser,
    "Manufaktur": ManufacturingParser,
    "BUMN": BumnParser,
    "Retail": RetailParser,
    "Transport & Logistics": TransportLogisticsParser,
    "Education": EducationParser,
    "Media": MediaParser,
}
