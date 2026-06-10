# rechtspraak_corpus_survey

A small LLM pipeline that gives an overview of the *structure* of the civil rechtspraak
corpus quickly and cheaply. It reads the judgment XML produced by
[`rechtspraak_corpus_construction`](../rechtspraak_corpus_construction/) and asks
an instruction-tuned model through an OpenAI-compatible generative API to
label the main sections of each uitspraak. The output is one JSON line per
document, which then feeds the lexicon work in
[`rechtspraak_segmentation`](../rechtspraak_segmentation/).

The main point of interest is the **prompting**, split out per judicial instance.
Everything that is identical across courts (the API/model settings,
the structured-output schema, the XML extraction, the LLM call and the batch
runner) lives in `base.py`; the court-specific system prompt, user prompt and
few-shot examples live in a `Profile` and are selected on the command line:

- `base.py`: the shared pipeline, schema and batch runner.
- `rechtbank.py`: the `RECHTBANK` profile (vonnis, eerste aanleg).
- `gerechtshof.py`: the `GERECHTSHOF` profile (arrest, hoger beroep).
- `cli.py` / `__init__.py`: argument parsing and the court, profile registry.

## The section model

Each document is annotated against the standard structure of a civil judgment
(art. 230 Rv). Every section type is a *list*, so multiple occurrences within one
document are captured (e.g. "De beoordeling in conventie" and "in
reconventie"). An empty list means the section is absent.

## Requirements

- Python 3.11 or higher
- Python packages: see the `pyproject.toml` file
- An `OPENAI_API_KEY` (see below)

The API key is **required** and read from a `.env` file in the main directory
(`machina-pauliana/.env`):

```
OPENAI_API_KEY=your-key-here
```

The key is any OpenAI-compatible key; here it is a Scaleway Generative APIs
secret key. The model and endpoint are set in `base.py`:

| Setting   | Value                                                       |
|-----------|-------------------------------------------------------------|
| Model     | `mistral-small-3.2-24b-instruct-2506`                       |
| Provider  | Scaleway Generative APIs (OpenAI-compatible)                |
| Endpoint  | `https://api.scaleway.ai/v1`                                |
| Decoding  | `temperature=0.1`, `top_p=0.2`, `seed=42`, `max_tokens=1200` |

A non-zero temperature is used on purpose: Scaleway's docs warn that `0` risks
loops with structured output.

## Usage

Run it as a module from the main directory (`machina-pauliana/`), choosing a
court with `--court` (`RB` = rechtbank, `GH` = gerechtshof):

```
python -m rechtspraak_corpus_survey \
  --court GH \
  --input_dir ./data/xml_output_matches \
  --output ./data/report_gerechtshof.jsonl
```

`--input_dir` expects the `COURT/YEAR/ECLI.xml` layout written by the fetcher.
`--court` doubles as a **filter**: with `--court GH` only files under court
folders starting with `GH` (e.g. `GHAMS/`, `GHARL/`) are processed, so you can
point at the full corpus and still survey one instantie at a time. Pointing
`--input_dir` directly at a single court folder also works.

Requests are executed with an interval (and retried with backoff on HTTP 429) to stay within
the API rate limits, so a large run takes a while; progress is printed per file
and the output is flushed after every document.
You might be able to tweak the interval based on your API rate limits.

## Output

A JSONL file, one object per document. Each object carries the `ecli`, the six
section lists (each entry is the section's opening tag including its title) and
the `source_file`.

## Key references

- Törnberg, Petter (2024). *Best Practices for Text Annotation with Large
  Language Models*. arXiv:2402.05129 [cs.CL].
  <https://arxiv.org/abs/2402.05129>
- Ahsmann, M.J.A.M. (2020). *De weg naar het civiele vonnis*. 2nd ed. Den Haag:
  Boom Juridisch. ISBN 9789462901681.
- Bartelds, Joost et al. (2020). *Professionele standaard Schrijven: Best
  practices en aanbevelingen van de civiele afdelingen van de hoven*.
  <https://www.rechtspraak.nl/binaries/_rts_1768396290578/content/assets/lov/ps/lov-ps-professionele-standaard-schrijven.pdf>
- De Groot, J.F. and A.E.H. van der Voort Maarschalk (2026). "Opbouw van de
  uitspraak". In: *Cassatie*. Ed. by B.T.M. van der Wiel. 2nd ed. Monografieën
  Burgerlijk Proces & Praktijk 20. Deventer: Wolters Kluwer. ISBN 9789013184914.
