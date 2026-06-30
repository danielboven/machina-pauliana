"""Bridge to the Catala symbolic model (scope FaillissementspaulianaArt42).

Exposes one function 'vernietigbaar' that feeds the variables resolved
by the LLM routines into the Catala model and returns the final verdict.

The model is the self-contained package built using the script
catala_model/generate_catala_python.sh, please re-run that script after
changing the Catala source.
"""

from .catala_generated import Faillissementspauliana as F
from .catala_generated import catala_runtime as rt


def _date(ymd: str):
    """Get a Catala Date from a 'yyyy-mm-dd' string."""
    return rt.Date(*(int(part) for part in ymd.split("-")))


def vernietigbaar(invoer) -> bool:
    """Whether the rechtshandeling is avoidable under art. 42 Fw.

    `invoer` is a `schema.FaillissementspaulianaInput`
    Each conditional field (criterium) is wrapped as a Catala condition
    (a value with a source position) or left absent when None. Catala default
    case is then False."""
    pos = rt.SourcePosition("neuro_symbolic_model", 0, 0, 0, 0, [])

    def cond(value):
        return (
            rt.Option(rt.CatalaTuple(rt.Bool(value), pos))
            if value is not None
            else rt.Option(None)
        )

    h = invoer.handeling
    inp = F.FaillissementspaulianaArt42In(
        handeling_in=F.Handeling(
            is_rechtshandeling=rt.Bool(h.is_rechtshandeling),
            datum_rechtshandeling=_date(h.datum_rechtshandeling),
            verricht_door_de_schuldenaar=rt.Bool(
                h.verricht_door_de_schuldenaar
            ),
            onverplicht=rt.Bool(h.onverplicht),
            om_niet=rt.Bool(h.om_niet),
        ),
        faillissement_in=F.Faillissement(
            datum_faillietverklaring=_date(
                invoer.faillissement.datum_faillietverklaring
            ),
        ),
        benadeling_schuldeisers_in=rt.Bool(invoer.benadeling_schuldeisers),
        wetenschap_schuldenaar_aangetoond_in=rt.Bool(
            invoer.wetenschap_schuldenaar_aangetoond
        ),
        wetenschap_wederpartij_aangetoond_in=cond(
            invoer.wetenschap_wederpartij_aangetoond
        ),
        vermoeden_wetenschap_schuldenaar_tegenbewijs_in=cond(
            invoer.vermoeden_wetenschap_schuldenaar_tegenbewijs
        ),
        vermoeden_wetenschap_wederpartij_tegenbewijs_in=cond(
            invoer.vermoeden_wetenschap_wederpartij_tegenbewijs
        ),
        tegen_onderwaarde_in=cond(invoer.tegen_onderwaarde),
        voldoening_of_zekerheid_niet_opeisbare_schuld_in=cond(
            invoer.voldoening_of_zekerheid_niet_opeisbare_schuld
        ),
        gelieerde_partij_in=cond(invoer.gelieerde_partij),
        reeds_verplicht_voor_aanvang_termijn_in=cond(
            invoer.reeds_verplicht_voor_aanvang_termijn
        ),
    )
    return bool(F.faillissementspauliana_art42(inp).vernietigbaar)
