"""Unified input/output schema of the neuro-symbolic model.

One schema mirrors the structure of the Catala model, also see
catala_json_schema/catala_faillissementspauliana_art42.json
The only addition over the Catala input are the _overwegingen
motivation/consideration fields the routines produce.
Nothing is re-declared here: the schema is composed from the routine models.
"""

from .coroutine import Faillissement
from .coroutine import Handeling as _FeitelijkeHandeling
from .subroutine_benadeling_schuldeisers import BenadelingSchuldeisersOutput
from .subroutine_onverplicht import OnverplichtOutput
from .subroutine_wetenschap import WetenschapOutput

# Re-exported so callers can build/inspect
__all__ = [
    "Handeling",
    "Faillissement",
    "FaillissementspaulianaInput",
    "NeuroSymbolicResult",
]


class Handeling(_FeitelijkeHandeling, OnverplichtOutput):
    """Merges the coroutine Handeling fields with the onverplicht subroutine."""


class FaillissementspaulianaInput(
    BenadelingSchuldeisersOutput, WetenschapOutput
):
    """Every resolved art. 42 Fw variable, shaped like the Catala input."""

    handeling: Handeling
    faillissement: Faillissement

    @classmethod
    def from_routines(
        cls,
        coroutine,
        onverplicht: OnverplichtOutput,
        benadeling: BenadelingSchuldeisersOutput,
        wetenschap: WetenschapOutput,
    ) -> "FaillissementspaulianaInput":
        """Assemble one from the four routine outputs."""
        return cls(
            handeling=Handeling(
                **coroutine.handeling.model_dump(), **onverplicht.model_dump()
            ),
            faillissement=coroutine.faillissement,
            **benadeling.model_dump(),
            **wetenschap.model_dump(),
        )


class NeuroSymbolicResult(FaillissementspaulianaInput):
    """The symbolic model's output: the input variables plus the verdict."""

    vernietigbaar: bool
