# rag

The retrieval store and advanced RAG behind the three case-based subroutines of
the [`neuro_symbolic_model`](../neuro_symbolic_model/). It holds the segmented
judgments (as Markdown sections), their section embeddings and the relations of
their procedural chain (i.e. "eerdere aanleg") in one Postgres/pgvector
database, and retrieves the top-k most similar judgments for a query,
filtered by pre-retrieval labels and expanded with the related judgments.
Sections come from the deterministic [`rechtspraak_segmentation`](../rechtspraak_segmentation/) pipeline.

Retrieval is *advanced* RAG in the sense of Gao et al. (2024): a pre-retrieval
and a post-retrieval stage wrap the similarity search, instead of just a
cosine similarity lookup.

## The store

Three tables (see [`db/schema.sql`](db/schema.sql)):

- `judgment` — one row per decision (ECLI as key) with `court`,
  segmentation `strategy`, `judgment_date`, and the three pre-retrieval label
  columns (below).
- `section` — the ordered RAG sections (chunks): one row per section in document order,
  the `label` (the six segmentation types), the `markdown` content, and an `embedding`
  (only calculated for feiten/overwegingen).
- `relation` — directional relation edges `(source_ecli → target_ecli)`
  between two judgments in the store, i.e. the procedural chain.

The three label columns encode, per judgment, whether the court rules on each
art. 42 Fw parts (used in pre-retrieval):

| column | requirement |
|---|---|
| `onverplicht` | onverplichte rechtshandeling (voluntary act) |
| `benadeling_schuldeisers` | benadeling van schuldeisers (prejudice to creditors) |
| `wetenschap` | wetenschap van benadeling (knowledge of prejudice) |

## Requirements

- Python 3.11 or higher
- Python packages: see the `pyproject.toml` file
- PostgreSQL with the [`pgvector`](https://github.com/pgvector/pgvector) extension
- A `.env` in the main directory (`machina-pauliana/.env`) with at least:
  - `DATABASE_URL` — Postgres DSN for the store (or use argument `--dsn`)
  - `SCALEWAY_API_KEY` — used for embeddings, and `mistral*` annotation LLM
  - `OPENAI_API_KEY` — only when annotating with a `gpt*` LLM

## Building the store

Run the passes in order from the main directory (`machina-pauliana/`):
`python -m rag <command>` is a thin dispatcher, each pass is also runnable on its own
(`python -m rag.ingest` ...):

```bash
python -m rag init                                 # create the schema (pgvector required on machine)
python -m rag ingest ./data/xml_output_matches     # segment XML -> judgments, sections, relations
python -m rag embed                                # embed feiten/overwegingen sections
python -m rag annotate --output labels.jsonl --write-db   # pre-retrieval labels
```

`init` allows the argument `--drop` to rebuild from scratch.
`ingest` expects an empty store and is not resumable; use `init --drop` before
re-ingesting a corpus. `embed` is resumable: it only processes sections without
a vector yet (for instance when internet was intermittently lost).

**Ingest** segments each judgment with the existing pipeline, merges adjacent
same-label sections, and writes the `judgment` and ordered `section` rows.
It then runs a second pass that extracts the procedural-chain
**relations** ([`ingest/relations.py`](ingest/relations.py)), with three
deterministic extractors, in priority order, that only emit an edge when both
judgments are in the store:

1. **formal** — an ECLI in a `<dcterms:relation>` RDF element (e.g. *eerste
   aanleg*), this type is structured and unambiguous.
2. **zaaknummer** — one judgment citing another's case number. A district number
   of the format `C/cc/NNNNNN` (or a rollcode number) is specific enough to match directly.
   A bare sequential number (i.e. `NNNNNN`) is matched only when the citing court
   names the other court instance beside it (like how a court of appeal cites
   a district court).
3. **inhoud** — an `"Appel/Hoger beroep van ECLI:..."` line in the
   `<inhoudsindicatie>` (rather strict matching in this format).

Free-form scanning of the body for ECLIs is deliberately avoided (as it leads
to many false positives).

**Embed** computes vectors only for `feiten` and `overwegingen` sections of at
least 70 characters (the two types retrieval scores on), using
**[Qwen3-Embedding-8B](https://huggingface.co/Qwen/Qwen3-Embedding-8B)**
through Scaleway, Matryoshka-truncated to 2000 dimensions
(within pgvector's HNSW limit), stored under a cosine HNSW index. A query is
embedded once with the model's asymmetric instruct prefix and reused across all
three subroutines. Documents get no instruction prefix, as Qwen3 is asymmetric.
Both live in [`api.py`](api.py) so the ingest-time and query-time vectors share one space.

## Retrieval

`rag.api` is the one public API. The neuro-symbolic subroutines use it as a
library:

```python
from rag.api import embed_query, retrieve, to_markdown
from rag.db.connection import connect

def retrieve_onverplicht(casus: str) -> str:
    """Retrieve examples for case facts and the relevant dispute."""
    with connect() as conn:
        vec = embed_query(casus)
        hits = retrieve(conn, vec, label="onverplicht", k=5)
        return to_markdown(hits)  # related judgments as one Markdown string
```

`retrieve(conn, query_vec, label=None, k=5)` runs the three stages:

- **Pre-retrieval (label filter).** When a `label` is given, only judgments for
  which that label is true are candidates. The rest are dropped for that
  subroutine. The label is propagated across the relation graph, so a judgment
  also qualifies when any judgment in its procedural chain has the label true.
  Recall matters most on the label (see below), because a false negative loses a
  judgment here.
- **Retrieval (weighted maxP).** Each candidate is scored by a weighted
  combination of its `feiten` and `overwegingen` similarity
  ([`retrieval/similarity.py`](retrieval/similarity.py)): `0.75 · feiten + 0.25 ·
  overwegingen`, renormalized to the types the judgment actually has (so a
  judgment with only one type falls back to it fully). Within a type, the score
  is the **maxP** aggregation described by Dai & Callan (2019): the cosine of the query
  against every section of that type, keeping "the best".
- **Post-retrieval (chain expansion).** Each of the top-k hits is expanded with
  its whole connected relation documents (including itself), rendered as full
  Markdown and ordered earliest → latest by `judgment_date`. `to_markdown`
  flattens the hits into a single context string, de-duplicating judgments that
  appear under more than one hit.

## Annotation

[`annotate.py`](annotate.py) produces the pre-retrieval labels. It prompts an
LLM, once per judgment, on whether the court itself rules on each of the three
art. 42 Fw parts: `onverplicht`, `benadeling_schuldeisers`,
`wetenschap`. To focus the model on the court's grounds of the decision,
only the grounds of the decision (`overwegingen`) are passed as context.

For each requirement the model returns, via structured output, a boolean plus a
verbatim citation (`citaat`) of the sentence the verdict rests on. Every result
is written as one JSON line. With `--write-db` the three booleans are also
written onto the `judgment` row. The citations are kept in the JSONL only, as an
audit trail — they are not stored in the database.

```bash
python -m rag.annotate --output labels.jsonl [--eclis ECLI ...] \
    [--model MODEL] [--write-db]
```

By default the entire corpus is annotated.
`--eclis` restricts it to a set. The provider is chosen from the model-name
prefix: `mistral*` → Scaleway (requires `SCALEWAY_API_KEY`),
`gpt*` → OpenAI (requires `OPENAI_API_KEY`), so switching models is
just `--model gpt-5.4` or `--model mistral/...`. **Recall** is one of the important
metrics to watch: a false negative silently drops a judgment from that subroutine's
candidate set, so false negatives should be minimised.

## Module layout

```
api.py            public surface: embedding (embed_text / embed_query) + retrieve / to_markdown
main.py           dispatcher over the subcommands (init / ingest / embed / annotate)
annotate.py       LLM pre-retrieval labelling of the three art. 42 Fw parts (done once)
db/               connection, schema.sql, init_db (create, --drop rebuild)
ingest/           main (XML -> judgments + sections), relations (citation edges), embed (section vectors)
retrieval/        search (the read path), similarity (weighted maxP), graph (relation-graph CTEs)
```

## Key references

- Zhang, Yanzhao et al. (2025). *Qwen3 Embedding: Advancing Text Embedding and
  Reranking Through Foundation Models*. arXiv:2506.05176 [cs.CL].
  <https://arxiv.org/abs/2506.05176>
- Gao, Yunfan et al. (2024). *Retrieval-Augmented Generation for Large Language
  Models: A Survey*. arXiv:2312.10997 [cs.CL]. <https://arxiv.org/abs/2312.10997>
- Dai, Zhuyun and Jamie Callan (2019). "Deeper Text Understanding for IR with
  Contextual Neural Language Modeling". In: *Proceedings of the 42nd
  International ACM SIGIR Conference on Research and Development in Information
  Retrieval*. ACM, pp. 985–988. <https://doi.org/10.1145/3331184.3331303>
- Pannevis, N.B. (2026). "Schuldeisersbenadeling". 16th ed. Deventer: Wolters
  Kluwer. Chap. 7. ISBN 9789013178944.
- Vriesendorp, R.D. (2024). *Insolventierecht*. Derde druk. Studiereeks
  burgerlijk recht 8. Deventer: Wolters Kluwer. ISBN 978-90-13-17603-2.
- Wessels, B. (2019). *Gevolgen van faillietverklaring*. 5th ed. Vol. III.
  Insolventierecht. Deventer: Wolters Kluwer. ISBN 978-90-13-15314-9.
