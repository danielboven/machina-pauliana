# Machina Pauliana: Modelling actio pauliana in Dutch insolvency law

Daan Boven

Machina Pauliana is a BSc thesis project (Computer Science, University of Amsterdam)
on the neuro-symbolic modelling of transaction avoidance (actio pauliana of Article 42 Fw) in Dutch insolvency law.
It combines a formal, rule-based model of the statutory provision with a data-driven pipeline that retrieves,
segments, and embeds Dutch case law from [rechtspraak.nl](https://rechtspraak.nl), used as a neural subroutine
to interpret the open-textured elements. The aim is to assess how well this hybrid approach produces judicial
reasoning in (possible) actio pauliana cases.

## Repository layout

The case-law side of the project is a pipeline that runs roughly in this following order.
Each folder has its own README with the details.

1. [`rechtspraak_corpus_construction/`](rechtspraak_corpus_construction/)
   Builds the corpus from the [rechtspraak.nl](https://www.rechtspraak.nl) open
   data: import the case metadata into Postgres, fetch the judgment XML, filter
   it down to the art. 42/43/45 Fw cases, and cross-check the result against an
   external reference list.
2. [`rechtspraak_corpus_survey/`](rechtspraak_corpus_survey/) An LLM survey
   that labels the main sections of each uitspraak, used to draft and check the
   segmentation lexicons. Prompt-driven, one JSON line per document.
3. [`rechtspraak_segmentation/`](rechtspraak_segmentation/) The deterministic
   segmenter that splits each judgment into labelled, non-overlapping sections
   (procesverloop, feiten, geschil, overwegingen, beslissing, overig) using
   court-specific lexicons. This is the structural backbone for the downstream
   modelling.

## Requirements

- Python 3.11 or higher
- Python packages: see [`pyproject.toml`](pyproject.toml)
- Some steps need extra setup: PostgreSQL for corpus construction, and an
  `OPENAI_API_KEY` in a `.env` file for the survey. See the respective READMEs.