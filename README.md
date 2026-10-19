# Machina Pauliana: Modelling actio pauliana in Dutch insolvency law

Daan Boven

This repository accompanies the paper *Machina Pauliana: A neuro-symbolic approach to the actio pauliana in Dutch insolvency law*
by Daan Boven, Gregor Behnke and David Graus, accepted at JURIX 2026.

Machina Pauliana is a research project from the University of Amsterdam
on the neuro-symbolic modelling of transaction avoidance (actio pauliana of Article 42 Fw) in Dutch insolvency law.
It combines a formal, rule-based model of the statutory provision with a data-driven pipeline that retrieves,
segments, and embeds Dutch case law from [rechtspraak.nl](https://rechtspraak.nl), used as a neural CBR subroutine
to interpret the open-textured elements. The aim is to assess how well this hybrid approach produces judicial
reasoning in (possible) actio pauliana cases.

## Repository layout

The corpus construction, survey and segmentation stages prepare the case law
for RAG. The Catala model supplies the formal legal rules, and the
neuro-symbolic model combines both sides. Each folder has its own README with
the details. All LLM prompts are listed in [`PROMPTS.md`](PROMPTS.md).

| directory | purpose |
|---|---|
| [`rechtspraak_corpus_construction/`](rechtspraak_corpus_construction/) | Imports Rechtspraak metadata, fetches judgment XML, filters the art. 42/43/45 Fw corpus and compares it with an external reference list. |
| [`rechtspraak_corpus_survey/`](rechtspraak_corpus_survey/) | Uses an LLM to survey the section structure of the corpus, as input for drafting and checking the segmentation lexicons. |
| [`rechtspraak_segmentation/`](rechtspraak_segmentation/) | Deterministically splits judgments into labelled, non-overlapping sections using court-specific lexicons. |
| [`catala_model/`](catala_model/) | Formally models the requirements and evidentiary presumptions of the faillissementspauliana in Catala. |
| [`rag/`](rag/) | Stores, annotates and embeds the segmented judgments, then retrieves similar cases and their procedural relations. |
| [`neuro_symbolic_model/`](neuro_symbolic_model/) | Resolves the open-textured inputs with LLM routines and lets the Catala model decide whether the act is voidable. |
| [`evaluation/`](evaluation/) | Builds the validation datasets and evaluates segmentation, pre-retrieval annotation and the final model. |
| [`data/`](data/) | Contains the corpus data, database snapshot, gold standards, model outputs and generated figures used in the research paper. |

## Requirements

- Python 3.11 or higher
- Python packages: see [`pyproject.toml`](pyproject.toml)
- PostgreSQL and pgvector for the database-backed corpus and RAG stages
- Provider-specific API keys for the LLM and embedding steps
- Catala and Clerk only when rebuilding the generated formal model

See the respective READMEs for the setup and commands of each stage.

## Disclosure

This repository is released under the [BSD 3-Clause License](LICENSE.md); any use
or redistribution must comply with its terms. The project is provided as is for
research purposes, does not constitute legal advice, and the author accepts no
responsibility for its use or outcomes.

Generative AI tools were used to refine the code, documentation and structure of
this repository. Their output was reviewed and adjusted by the author.
