# catala_model

A formal model of the *faillissementspauliana* (the avoidance action of art. 42 of
the Dutch Bankruptcy Act, *Faillissementswet*, Fw) written in [Catala](https://catala-lang.org/)
with the English Catala syntax. The model follows the decision scheme of Polak/Pannevis and,
in keeping with Catala's literate-programming approach, stays close to the statute:
each condition sits next to the paragraph (*lid*) it comes from, with the Dutch statutory text
quoted inline above its formalisation.

Catala compiles the model to OCaml and Python, also see `clerk.toml`. The Python target
is what the rest of the neuro-symbolic pipeline calls: given the inputs of a
contested transaction it decides whether that transaction is voidable
(*vernietigbaar*).

## What is modelled

- **Art. 42 lid 1 and lid 2**: the core requirements: a legal act, performed by
  the debtor before bankruptcy, voluntarily, causing prejudice to creditors, with
  the requisite knowledge; and the additional counterparty-knowledge requirement
  for acts other than *om niet*. *Anders dan om niet* is modelled as `not om_niet`.
- **The art. 43 presumption** as the subscope `BewijsvermoedenArt43`. Its grounds
  are modelled as sub 1° *onderwaarde* and sub 2° *niet-opeisbare schuld* as
  separate conditions, the affiliated-party grounds collapsed into one boolean
  `gelieerde_partij` (see below), and the one-year requirement that the debtor was
  not already obliged to perform the act before the term began.
- **The art. 45 presumption** as the subscope `BewijsvermoedenArt45`: knowledge
  presumed for an act *om niet* within one year of bankruptcy.

Some smaller choices: the one-year window rounds dates down, for which there is not
a clear source on the Dutch Bankruptcy Act (Fw), so it was modelled after HR 1 September 2017,
ECLI:NL:HR:2017:2225 (leap-year situation is unsettled for Fw).
Unlike art. 45 the art. 43 presumption can also be invoked for an act
*om niet* (HR 23 September 2016, ECLI:NL:HR:2016:2172, *Hage q.q./Kelderman*).

## What is deliberately left out

- **Art. 42 lid 3**, the protection of a good-faith, un-enriched beneficiary of an
  act *om niet*. It limits the *effect* of an avoidance, not whether the act is
  voidable, so it was decided that this falls outside the question the model should
  help to answer. Note that the legislator originally put this in Art. 46 Fw but it
  was later moved. This also indicates that the contents are somewhat seperated
  from the rest of the faillissementspauliana.
- **Art. 47**, avoidance for due performances, is governed by a
  different, stricter regime and is left out.
- **The affiliated-party grounds of art. 43 sub 3°–6°** and the definitions of
  lid 2–6. These point to a long, casuistic catalogue of related parties.
  Rather than expand them into many narrow booleans, they are collapsed into
  the single condition `gelieerde_partij`, whose qualification is determined
  neurally. Fully modelling them would inflate the
  symbolic interface and push the same combinatorial detail into the neural
  component as context; Gao et al. (2024) note that overloading a model with context
  degrades its output, so the affiliated-party question is kept as one boolean. The
  trade-off is that the statutory definition is delegated to the neural layer rather
  than checked by the model.

## Neural bridge

The Catala model is the primary symbolic reasoner. It orders the statutory
conditions, applies the evidentiary presumptions of arts. 43 and 45 and decides
whether the contested transaction is voidable. Neural routines supply the inputs
that require either structuring natural-language facts or interpreting
open-textured terms developed in case law.

The neural coroutine and case-based subroutines supply these structured inputs
from the natural language facts and retrieved decisions. The division of tasks and schemas are
documented in the [final neuro-symbolic model](../neuro_symbolic_model/README.md).

The coupling is deliberately loose. Pydantic schemas constrain the neural output,
while the typed Catala scope defines the symbolic inputs and output; the Python
pipeline maps between the two. `clerk json-schema` can print that Catala scope
schema independently.

## Building and running

Install Catala and `clerk` first; see the [Catala book](https://book.catala-lang.org/en/1-1-0-installing.html). Then, inside this directory:

```bash
clerk start      # prepare the local build environment (runtime + stdlib)
clerk typecheck  # type-check the sources
clerk test       # run the Catala tests in tests/
clerk build      # compile the OCaml and Python targets into _targets/
```

For the full command reference, see
<https://book.catala-lang.org/en/6-2-commands-workflow.html>.

## Key references

- Huttner, Liane and Denis Merigoux (Aug. 2022). "Catala: Moving towards the future
  of legal expert systems". In: *Artificial Intelligence and Law*. ISSN: 1572-8382.
  DOI: 10.1007/s10506-022-09328-5. <https://doi.org/10.1007/s10506-022-09328-5>.
- Gao, Yunfan et al. (2024). *Retrieval-Augmented Generation for Large Language
  Models: A Survey*. arXiv: 2312.10997 [cs.CL]. <https://arxiv.org/abs/2312.10997>.
- Merigoux, Denis, Nicolas Chataing, and Jonathan Protzenko (2021). "Catala: A
  Programming Language for the Law". In: *CoRR* abs/2103.03198. arXiv: 2103.03198.
  <https://arxiv.org/abs/2103.03198>.
- Pannevis, N.B. (2026). *Schuldeisersbenadeling*. 16th ed. Deventer: Wolters
  Kluwer. Chap. 7. ISBN 9789013178944.
- Wessels, B. (2019). *Gevolgen van faillietverklaring*. 5th ed. Vol. III.
  Insolventierecht. Deventer: Wolters Kluwer. ISBN 978-90-13-15314-9.
