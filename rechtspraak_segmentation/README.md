# rechtspraak_segmentation

Segments a Dutch court judgment (a *vonnis* / *arrest*, supplied as Rechtspraak
XML) into a sequence of labelled, non-overlapping sections. Each section is one of
six labels: **procesverloop** (procedural history), **feiten** (the facts),
**geschil** (the dispute / claims), **overwegingen** (the court's reasoning),
**beslissing** (the dictum), or **overig** (catch-all). The court-specific rules
live in a swappable *lexicon*, selected automatically from the ECLI.

## Requirements

- Python 3.10 or higher
- [`lxml`](https://pypi.org/project/lxml/) is the only third-party dependency used here
- The interactive review tool uses the standard-library `curses`, so that mode is
  Unix/macOS only (note that there is a port called [UniCursus](https://docs.python.org/3/howto/curses.html)). The library and the `--print` mode are cross-platform.

## Usage

As a library, `segment()` takes raw XML bytes or a path and returns a result:

```python
from rechtspraak_segmentation import segment

result = segment("ECLI_NL_RBAMS_2012_xyz.xml")   # or segment(xml_bytes)
print(result.court, result.strategy)
for s in result.sections:
    print(s.number, s.label, len(s.body_text), s.raw_title)
```

The court's lexicon is chosen from the ECLI; override it with `segment(src,
court="rechtbank")` or `segment(src, lexicon=my_lexicon)`.

As a program, run the package on a file or a folder:

```bash
python -m rechtspraak_segmentation FOLDER            # TUI interactive
python -m rechtspraak_segmentation FOLDER --print    # print each document, coloured
python -m rechtspraak_segmentation FOLDER --court RB # only process one court family
```

In the TUI: `->` / `Enter` = OK, `<-` / `f` = flag (then type a note), arrows/PgUp/PgDn
scroll, `q` quits. Flagged files are appended to `review_flagged.log` (a TSV:
timestamp, path, ecli, strategy, number of sections, note).

## Output / labels

`segment()` returns a `SegmentationResult`:

| field | meaning |
|---|---|
| `sections` | list of `Section` in document order |
| `strategy` | which detector fired: `section` / `bridgehead` / `numbered-para` / `keyword` |
| `ecli` | the document's ECLI |
| `court` | the lexicon used (`rechtbank`, `gerechtshof`, …) |

Each `Section` has: `label` (one of the six above), `raw_title` (the heading that
opened it), `number` (the heading number, if any), `strategy`, `body_text` (the
text of the span), and `element` / `end_element` (the start/end XML nodes).

## Algorithm

A short cascade of finite-state recognizers over the document's block elements
(`<para>`, `<title>`, `<bridgehead>`):

1. **Recognise.** Four detection strategies are tried in priority order, each one
   reading the element sequence and emitting labelled section markers:
   `structured` (top-level `<section>`s) → `bridgehead` → `numbered-para`
   (`"3. Het geschil"`) → `keyword` (bare heading lines). A strategy only "wins"
   if it produces at least one canonical section, otherwise the next is tried.
2. **Refine.** Recover headings the front-end missed (a leading procesverloop, the
   closing beslissing, oblique facts headings) and drop spurious ones (the party
   caption, quoted/enumerated lines mistaken for headings).
3. **Close.** Pair each start with the next to form spans and collect `body_text`.

Labelling is done by the **lexicon**: `label_rules` is an ordered list of
`(regex → label)` (first match wins), and a *controlled heading language*
(`heading_vocab`) gates which short lines may become headings at all — this is
what keeps running sentences from being promoted. See `THEORY.md` for the
finite-state-transducer framing, and `viz.py` to generate diagrams of these
machines from the code.

Module layout:

```
api.py            public segment() + the detect_boundaries pipeline
core/             court-agnostic primitives: xmlutil (XML helpers), model (Section)
lexicon/          base (the Lexicon type), text, registry + court detection,
                  and one module per court: rechtbank, gerechtshof, hoge_raad
strategies/       detect (the 4 recognisers), refine (recover / drop / close)
interface/        render (shared view-model), cli, tui
viz.py            emit Graphviz .dot of the label/heading/pipeline machines
```

## Running on your corpus, and adapting it

The tools expect the Rechtspraak layout `COURT/YEAR/ECLI.xml`
(e.g. `xml_output/RBAMS/2012/ECLI_NL_RBAMS_2012_xyz.xml`); folders are searched
recursively. The court is read from each ECLI: `RB*` → `rechtbank`, `GH*` →
`gerechtshof`, `HR` → `hoge_raad`. Any other code (e.g. `PHR`) raises
`UnknownCourtError`.

To check a rule change against your corpus, use the review TUI (it logs the files
you flag) together with the baseline snapshot/diff tool
`cache_segmentation.py` (a sibling under `rechtspraak_corpus_construction`): snapshot
the current behaviour, make the change, then diff to confirm only the intended
documents moved.

**Adapting it to a court or a topic.** The engine is court-agnostic; only the
lexicon changes. To add or tune a court, build a `Lexicon(name=, label_rules=,
heading_vocab=, oblique_feiten=)` in `lexicon/<court>.py` and register it in
`lexicon/__init__.py`. Rules are ordered (first match wins), so ordering encodes
priority. **Important caveat:** the lexicons here were derived and tested **only on
Faillissementspauliana cases (art. 42 / 43 / 45 Fw)**. The heading vocabulary and
label rules reflect that subject matter and may well not generalise to other areas
of law — expect to extend `label_rules` / `heading_vocab` before trusting it on a
different corpus.
