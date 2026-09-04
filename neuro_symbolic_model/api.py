"""Public API of the neuro-symbolic model.

Two entry points:

- :func:`resolve` calls 4 LLM routines (coroutine and the onverplicht,
  benadeling_schuldeisers and wetenschap RAG subroutines) concurrently
  It assembles their output into `FaillissementspaulianaInput`, and then calls
  :func:`resolve_symbolic`.
- :func:`resolve_symbolic` feeds a `FaillissementspaulianaInput` into the Catala
  scope FaillissementspaulianaArt42 and returns a `NeuroSymbolicResult` (input
  variables plus the verdict `vernietigbaar`). It does no LLM work, so it
  stays synchronous.
"""

import asyncio
from collections.abc import Collection

from . import catala, coroutine
from . import subroutine_benadeling_schuldeisers as benadeling_mod
from . import subroutine_onverplicht as onverplicht_mod
from . import subroutine_wetenschap as wetenschap_mod
from .model import DEFAULT_K, DEFAULT_MODEL, embed_casus_async
from .schema import FaillissementspaulianaInput, NeuroSymbolicResult


async def resolve(
    casus: str,
    *,
    model: str = DEFAULT_MODEL,
    k: int = DEFAULT_K,
    exclude: Collection[str] = (),
) -> NeuroSymbolicResult:
    """Resolve art. 42 Fw for the facts of one case (LLM routines + Catala).

    The four routines are independent, so they run concurrently; the call takes
    about as long as the slowest one.
    The case is embedded once and that vector is shared by the three RAG
    subroutines.

    `exclude` ablates judgments from retrieval by ECLI, for a case whose own
    proceedings are part of the corpus. They are dropped before ranking, so
    each subroutine still receives k example judgments.
    """

    async def run_subroutines():
        query_vec = await embed_casus_async(casus) if k >= 1 else None
        common = {"model": model, "k": k, "query_vec": query_vec}
        return await asyncio.gather(
            onverplicht_mod.run(casus, **common, exclude=exclude),
            benadeling_mod.run(casus, **common, exclude=exclude),
            wetenschap_mod.run(casus, **common, exclude=exclude),
        )

    (
        coroutine_uitvoer,
        (onverplicht, benadeling, wetenschap),
    ) = await asyncio.gather(
        coroutine.run(casus, model=model),
        run_subroutines(),
    )
    invoer = FaillissementspaulianaInput.from_routines(
        coroutine_uitvoer, onverplicht, benadeling, wetenschap
    )
    return resolve_symbolic(invoer)


def resolve_symbolic(
    invoer: FaillissementspaulianaInput,
) -> NeuroSymbolicResult:
    """Run the Catala model on resolved input variables
    (FaillissementspaulianaInput). Itreturns the variables and the verdict
    `vernietigbaar`.
    """
    return NeuroSymbolicResult(
        **invoer.model_dump(),
        vernietigbaar=catala.vernietigbaar(invoer),
    )
