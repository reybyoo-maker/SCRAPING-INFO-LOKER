"""Optional company-specific selector overrides used before generic heuristics."""
from .astra import AstraParser
from .unilever import UnileverParser
from .telkom import TelkomParser
from .gojek import GojekParser
from .tokopedia import TokopediaParser
from .mandiri import MandiriParser
from .bca import BcaParser
from .bri import BriParser
from .bni import BniParser
from .pertamina import PertaminaParser
from .pln import PlnParser
from .telkomsel import TelkomselParser
from .traveloka import TravelokaParser
from .bukalapak import BukalapakParser
from .kalbe import KalbeParser
from .indofood import IndofoodParser
from .shopee import ShopeeParser
from .blibli import BlibliParser
from .freeport import FreeportParser
from .mayora import MayoraParser

SPECIFIC_PARSERS = {
    "astra": AstraParser,
    "unilever": UnileverParser,
    "telkom": TelkomParser,
    "gojek": GojekParser,
    "tokopedia": TokopediaParser,
    "mandiri": MandiriParser,
    "bca": BcaParser,
    "bri": BriParser,
    "bni": BniParser,
    "pertamina": PertaminaParser,
    "pln": PlnParser,
    "telkomsel": TelkomselParser,
    "traveloka": TravelokaParser,
    "bukalapak": BukalapakParser,
    "kalbe": KalbeParser,
    "indofood": IndofoodParser,
    "shopee": ShopeeParser,
    "blibli": BlibliParser,
    "freeport": FreeportParser,
    "mayora": MayoraParser,
}
