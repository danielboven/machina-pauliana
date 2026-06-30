"""Neuro-symbolic model for the faillissementspauliana (art. 42 Fw).

LLM routines resolve the open-textured inputs of the Catala model,
which then decides whether a legal act is avoidable.
:func:`resolve` is an async coroutine that runs the routines and the Catala
model end to end. You can ``await`` it from an async stack
or use ``asyncio.run(resolve(...))``; :func:`resolve_symbolic` runs only the
Catala model on a `FaillissementspaulianaInput` (synchronous), so a manually
edited input can be re-evaluated.
"""

from .api import resolve, resolve_symbolic
from .schema import NeuroSymbolicResult, FaillissementspaulianaInput

__all__ = [
    "resolve",
    "resolve_symbolic",
    "FaillissementspaulianaInput",
    "NeuroSymbolicResult",
]
