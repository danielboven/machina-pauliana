# evaluation

Builds the two hand-annotated validation datasets and builds the final results:
Rechtspraak segmentation, RAG pre-retrieval annotation, and the final neuro-symbolic model.
All commands below run from the repository root.

## Scripts

| script | purpose |
|---|---|
| `build_validation_dataset.py` | Randomly samples (SRS) judgments from the RAG database and writes Markdown templates for manual pipeline validation. |
| `evaluate_rechtspraak_segmentation.py` | Compares the manual section spans with the segmentation spans stored in the database. |
| `evaluate_rechtspraak_annotation.py` | Compares an LLM's three pre-retrieval labels with the hand-annotated labels. |
| `build_neuro_symbolic_dataset.py` | Runs the end-to-end neuro-symbolic model over a directory of case inputs for one model and one RAG `k`. |
| `evaluate_neuro_symbolic.py` | Scores resolved boolean variables and the final `vernietigbaar` verdict against the neuro-symbolic gold standard (manual). |

## Requirements

- Python 3.11 or higher
- Python packages: see [`pyproject.toml`](../pyproject.toml)
- `DATABASE_URL` in the root `.env`, or `--dsn`, for scripts that read the RAG
  Postgres database
- The provider API key required by the selected model when generating results;
  see [`neuro_symbolic_model/README.md`](../neuro_symbolic_model/README.md)

The committed datasets and model predictions are under [`data/`](../data/) dir, so
the annotation and neuro-symbolic scoring scripts can be rerun without making
LLM requests. Segmentation evaluation still reads the predicted sections from
the database.

## Pipeline validation

Create a random sample from the RAG store:

```bash
python -m evaluation.build_validation_dataset \
  -n 100 \
  -o data/gold_standard/validation_dataset_pipeline
```

Each output file has blank YAML fields for `onverplicht`, `wetenschap` and
`benadeling_schuldeisers`. Fill these with booleans after review. Sections are
opened by markers such as `<!-- @feiten -->` and these can be adjusted.
A section runs until the next marker or end of file.

Score the corrected segmentation against the sections in the RAG store:

```bash
python -m evaluation.evaluate_rechtspraak_segmentation \
  data/gold_standard/validation_dataset_pipeline
```

A span counts as correct only when both its label and Markdown content match
exactly (apart from surrounding whitespace). A predicted span that is not in
the manual annotation is a false positive; a manually annotated span that is
missing from the prediction is a false negative. Changing a boundary or label
therefore usually creates both: the original predicted span is a false positive
and the corrected span is a false negative.

The script prints precision, recall and F1 per section label, plus pooled averages.

Score an LLM annotation file against the three YAML labels:

```bash
python -m evaluation.evaluate_rechtspraak_annotation \
  data/gold_standard/validation_dataset_pipeline \
  data/rag/pauliana_validation_gpt54.jsonl \
  -o data/figures/annotation_grounds_decision_gpt_confusion_matrix.pdf
```

The three labels are treated as separate binary classifiers/labels, with `True`
as the positive class. The script prints a multilabel classification report and
writes one confusion matrix pooling all judgment/requirement pairs. Gold ECLIs
absent from the prediction file are reported and skipped.

## Neuro-symbolic evaluation

Run all Markdown inputs for one model and retrieval setting:

```bash
python -m evaluation.build_neuro_symbolic_dataset \
  data/neuro_symbolic_model/inputs \
  --model gpt-5.5 \
  -k 5 \
  -o data/neuro_symbolic_model/results/faillissementspauliana_result_gpt-5.5_k_5.json
```

Cases are processed in filename order. The output records `model`, `k`,
and one resolved result per input filename. Use `k = 0` for a run without
retrieved examples.

After generating one or more `(model, k)` files, evaluate the entire results
directory:

```bash
python -m evaluation.evaluate_neuro_symbolic \
  data/neuro_symbolic_model/results \
  -o data/figures/vernietigbaar_accuracy_graph.pdf
```

By default, gold annotations come from
`data/gold_standard/neuro_symbolic_model/full_judgments`. You can override
this with `--gold`. The script prints two precision/recall/F1 tables:

1. a micro-average over every boolean Catala input and the final verdict;
2. the same variables grouped by the `onverplicht`,
   `benadeling_schuldeisers` and `wetenschap` subroutines.

Missing and `null` booleans are interpreted as `False`, matching how Catala
treats these. The generated PDF separately shows the number of correct final
`vernietigbaar` verdicts per model and `k`.
