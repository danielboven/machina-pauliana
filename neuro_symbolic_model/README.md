# neuro_symbolic_model

Decides whether a contested legal act is voidable under Art. 42 Fw for one case.
Four LLM routines resolve the inputs from the case facts,
and the [`catala_model`](../catala_model/) formal model then decides if the legal act
is avoidable from those inputs. See [`catala_model/README.md`](../catala_model/README.md)
for what is modelled and how.

```python
from neuro_symbolic_model import resolve

async def beoordeel(casus: str) -> bool:
    result = await resolve(casus)  # casus: the case facts as free text
    return result.vernietigbaar    # is the act voidable?
```

From a synchronous script, call `asyncio.run(resolve(casus))` instead.

`resolve()` is the only entry point most callers need: it runs the four routines,
assembles their output into a `FaillissementspaulianaInput`, and feeds that into
Catala. `resolve_symbolic(invoer)` runs just the Catala part on an already-resolved
(or manually edited) `FaillissementspaulianaInput`, so certain inputs can be edited
and re-evaluated without re-querying all neural routines. Both are re-exported
from the package `__init__.py`.

`resolve(casus, model=DEFAULT_MODEL, k=DEFAULT_K, exclude=())` takes the LLM, the
RAG top-k (`k = 0` disables retrieval) and an optional collection of ECLIs to
ablate from retrieval, e.g. the other proceedings of the case being resolved.

## The four routines

One factual-extraction routine (coroutine) and three RAG CBR subroutines that use case-based reasoning.
Schemas are all defined as a Pydantic schema based on [`catala_json_schema/*.json`](./catala_json_schema/)
and the LLM prompts are also defined in the Python files:

- `coroutine.py`: resolves the (factual) inputs that do not require case-based reasoning,
  such as whether the act is a legal act, performed by the debtor, for consideration, and
  the dates of the act and bankruptcy. No RAG.
- `subroutine_onverplicht.py`, `subroutine_benadeling_schuldeisers.py`,
  `subroutine_wetenschap.py`: resolve the three material criteria that use
  case-based reasoning. These retrieve top-k similar judgments from
  [`rag`](../rag/) — filtered on their own label — and pass them to the LLM as
  context alongside the case facts.

Every output field with reasoning is preceded by an `_overwegingen` (motivation)
field, so the model reasons in text before committing to the boolean, as the prompts
instruction it to fill that field first. `wetenschap` is the largest of the three: it
also resolves the Artt. 43/45 Fw presumption grounds and any rebuttal.

`model.py` is the shared infrastructure the four routines use: it picks the
provider (OpenAI compatible library) from the model-name prefix (`gemini*`, `mistral*`,
`gpt*`), runs the structured-output prompt (with retry on 429), and embeds the
case once so the three RAG subroutines can share one query vector instead of
re-embedding per label.

## Schemas

Every schema is a Pydantic model, composed rather than redeclared: `schema.py`
builds `FaillissementspaulianaInput` (and its result subtype
`NeuroSymbolicResult`) directly from the four routines' output models, mirroring
the shape that can be generated using `clerk json-schema`.
The corresponding JSON Schemas live under [`catala_json_schema/`](./catala_json_schema/)
for reference only. They are not imported anywhere.

## Catala bridge

`catala.py` exposes the function `vernietigbaar(input)`, that maps a
`FaillissementspaulianaInput` onto the Catala scope's input type and runs it.
Catala treats an absent optional the same as `false` by default.

`catala_generated/` is the compiled Catala package and **should not be edited by
hand**: it is produced by [`catala_model/generate_catala_python.sh`](../catala_model/generate_catala_python.sh),
which compiles the `.catala_en` source with `clerk` and flattens the runtime,
stdlib and compiled scope into this one importable package. Re-run that script
after changing the Catala source:

```sh
sh catala_model/generate_catala_python.sh
```

## Requirements

- Python 3.11 or higher
- Python packages: see the `pyproject.toml` file
- One API key per LLM provider used (`GEMINI_API_KEY`, `SCALEWAY_API_KEY`,
  `OPENAI_API_KEY`), read from a `.env` file in the main directory
  (`machina-pauliana/.env`); only the key matching the chosen model is required
- A running [`rag`](../rag/) database (the three RAG subroutines query it directly)
