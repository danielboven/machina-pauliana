# rechtspraak_segmentation

Segments a Dutch civil court judgment (a *vonnis* / *arrest*, supplied as Rechtspraak
XML) into a sequence of labelled, non-overlapping sections. Each section is one of
six labels: **procesverloop** (procedural history), **feiten** (the facts),
**geschil** (the dispute / claims), **overwegingen** (the court's reasoning),
**beslissing** (the dictum), or **overig** (catch-all). The court-specific rules
live in a swappable *lexicon*, selected automatically from the ECLI.

## Requirements

- Python 3.11 or higher
- [`lxml`](https://pypi.org/project/lxml/) for XML parsing
- [`rich`](https://pypi.org/project/rich/) for the coloured `--print` output
- [`textual`](https://pypi.org/project/textual/) for the interactive reviewer

All three are cross-platform, so every mode runs anywhere.

## Usage

As a library, `segment()` takes raw XML bytes or a path and returns a result:

```python
from rechtspraak_segmentation import segment
from rechtspraak_segmentation.core.serialize import to_markdown

result = segment("ECLI_NL_RBAMS_2012_xyz.xml")   # or segment(xml_bytes)
print(result.court, result.strategy)
for s in result.sections:
    print(s.number, s.label, s.raw_title)
    print(to_markdown(s.blocks))   # the section body as Markdown, heading included
```

The court's lexicon is chosen from the ECLI; override it with `segment(src,
court="rechtbank")` or `segment(src, lexicon=my_lexicon)`. For the whole document as
one labelled-Markdown string, use `interface.render.document_markdown(xml_bytes)`,
which returns `(markdown, meta)` with a `## §LABEL` heading per section.

As a program, run the package on a file or a folder:

```bash
python -m rechtspraak_segmentation FOLDER            # interactive reviewer (Textual)
python -m rechtspraak_segmentation FOLDER --print    # print each document, coloured
python -m rechtspraak_segmentation FOLDER --court RB # only process one court family
```

In the reviewer: `←` opens the previous document, `→` / `Enter` opens the next,
and `f` flags the document (type a note, then `Enter` to save and advance, or
`Esc` to cancel). `↑` `↓`
`PgUp` `PgDn` `Home` `End` scroll, `q` quits. Flagged files are appended to
`review_flagged.log` (a TSV: timestamp, path, ecli, strategy, number of sections, note).

## Output / labels

`segment()` returns a `SegmentationResult`:

| field | meaning |
|---|---|
| `sections` | list of `Section` in document order |
| `strategy` | which detector fired: `section` / `bridgehead` / `numbered-para` / `keyword` |
| `ecli` | the document's ECLI |
| `court` | the lexicon used (`rechtbank`, `gerechtshof`, …) |

Each `Section` has: `label` (one of the six above), `raw_title` (the heading that
opened it), `number` (the heading number, if any), `strategy`, `blocks` (the body as
a list of typed blocks, ready for `to_markdown`), `body_text` (the same span as plain
text, heading included), and `element` / `end_element` (the start/end boundaries).

## Algorithm

The XML is first parsed once into a flat, document-ordered stream of **typed blocks**
(`Para`, `Heading`, `List`, `Table`, ...), an intermediate representation that the rest
of the package works on, so detection does not use lxml again. A separate
**serializer** turns those blocks into Markdown, which decouples the output format from
the source XML. Segmentation is a short cascade of finite-state recognizers over that
block stream:

1. **Recognise.** Four detection strategies are tried in priority order, each one
   reading the block sequence and emitting labelled section markers:
   `structured` (top-level `<section>`s) → `bridgehead` → `numbered-para`
   (`"3. Het geschil"`) → `keyword` (bare heading lines). A strategy only "wins"
   if it produces at least one canonical section, otherwise the next is tried.
2. **Refine.** Recover headings the front-end missed (a leading procesverloop, the
   closing beslissing, oblique facts headings) and drop spurious ones (the party
   caption, quoted/enumerated lines mistaken for headings).
3. **Close.** Span each section from its start to just before the next, slicing the
   block stream into each section's `blocks` (heading included) and `body_text`.

Labelling is done by the **lexicon**: `label_rules` is an ordered list of
`(regex → label)` (first match wins), and a *controlled heading language*
(`heading_vocab`) gates which short lines may become headings at all, this is
what keeps running sentences from being promoted.

Module layout:

```
api.py            public segment() + the detect_boundaries pipeline
core/             court-agnostic primitives: xmlutil (XML helpers),
                  parse (XML -> typed blocks), blocks (the block model),
                  serialize (blocks -> Markdown), model (Section + labels)
lexicon/          base (the Lexicon type), text, registry + court detection,
                  and one module per court: rechtbank, gerechtshof, hoge_raad
strategies/       headings (the 4 recognisers), refine (recover / drop / close)
interface/        render (shared view-model + Markdown), cli, tui (Textual)
```

## Running on your corpus, and adapting it

The tools expect the Rechtspraak layout `COURT/YEAR/ECLI.xml`
(e.g. `xml_output/RBAMS/2012/ECLI_NL_RBAMS_2012_xyz.xml`); folders are searched
recursively. The court is read from each ECLI: `RB*` → `rechtbank`, `GH*` →
`gerechtshof`, `HR` → `hoge_raad`. Any other code (e.g. `PHR`) raises
`UnknownCourtError`.

To check a rule change against your corpus, use the interactive reviewer (it logs the
files you flag): snapshot `segment()`'s output over the corpus, make the change, then
diff to confirm only the intended documents moved.

**Adapting it to a court or a topic.** The engine is court-agnostic; only the
lexicon changes. To add or tune a court, build a `Lexicon(name=, label_rules=,
heading_vocab=, oblique_feiten=)` in `lexicon/<court>.py` and register it in
`lexicon/__init__.py`. Rules are ordered (first match wins), so ordering encodes
priority.

**Important caveat:** the lexicons here were derived and tested **only on
Faillissementspauliana cases (art. 42 / 43 / 45 Fw)**. The heading vocabulary and
label rules reflect that subject matter and may well not generalise to other areas
of Dutch civil law. Expect to extend `label_rules` / `heading_vocab` and refinements
before using it on a different corpus.
