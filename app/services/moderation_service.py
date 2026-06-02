from spanlp.palabrota import Palabrota
from spanlp.domain.countries import Country

_palabrota = Palabrota(
    censor_char="*",
    countries=[
        Country.COSTA_RICA,
        Country.MEXICO,
        Country.ARGENTINA,
        Country.COLOMBIA,
        Country.VENEZUELA,
        Country.CHILE,
        Country.PERU,
        Country.ECUADOR,
        Country.URUGUAY,
        Country.PANAMA,
    ],
)


def censor(text: str) -> str:
    return _palabrota.censor(text)
