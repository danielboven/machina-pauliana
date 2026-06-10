# rechtspraak_corpus_construction

A set of tools/programs that build the corpus from the [rechtspraak.nl](https://www.rechtspraak.nl)
open data. They run as a data pipeline: import the case metadata into Postgres, fetch
the judgment XML for the cases you want, filter that down to the relevant
articles, and finally cross-check the result against an external reference list.

1. `db_import_woozm.py`: stream the [WooZM](https://woozm.nl) metadata dump into Postgres.
2. `rechtspraak_fetcher.py`: fetch the judgment XML for the selected `dc_source` rows.
3. `filter_copy.py`: copy out only the cases that cite art. 42/43/45 Fw.
4. `compare_inview.py`: check the filtered corpus against a Wolters Kluwer Inview export.

## Requirements

- Python 3.11 or higher
- PostgreSQL on your system (or a sandbox, e.g. Docker with Postgres and Python 3)
- Python packages: see `pyproject.toml` file

## Postgres setup

Set up the database in Postgres so you can import all the Rechtspraak metadata from
the [WooZM](https://woozm.nl) database. The data dump comes from the ICAI OpenGov Lab.

```sql
CREATE DATABASE machina_pauliana;
```

Now on the `machina_pauliana` database connection:

```sql
CREATE TABLE dossiers (
    dc_identifier       TEXT        PRIMARY KEY,
    dc_title            TEXT,
    dc_type             TEXT,
    dc_description      TEXT,
    dc_source           TEXT,
    dc_publisher        TEXT,
    dc_creator          TEXT,
    tooiwl_topic        TEXT,
    foi_decisionDate    DATE,
    foi_nrDocuments     INTEGER,
    foi_retrievedDate   DATE,
    foi_publishedDate   DATE,
    foi_active          BOOLEAN,
    dc_date_year        SMALLINT,
    foi_approved        BOOLEAN,
    foi_updateDate      DATE
);
```

## DB Import WooZM

`db_import_woozm.py` streams the gzipped JSON export from WooZM straight into the
`dossiers` table. Run it from this folder, for instance:

```
python db_import_woozm.py --dsn postgresql://localhost/machina_pauliana --input woo_dev_dossiers_3b-u.json.gz
```

You can verify on the database that it worked accordingly:

```
machina_pauliana=# SELECT COUNT(*) FROM dossiers;
 count
--------
 880987
(1 row)
```

## Rechtspraak Fetcher

`rechtspraak_fetcher.py` takes any SQL query that returns `dc_source` rows,
extracts the ECLI from each URL, and downloads the corresponding case from the
Rechtspraak content API. Files are written as `<court>/<year>/<ECLI>.xml` (e.g.
`HR/1981/ECLI_NL_HR_1981_AG4158.xml`), so the layout matches what the segmentation
and filter tools expect. Downloads run concurrently behind a shared rate limiter
(default 10 req/s, per [IVO Rechtspraak 2019](https://www.rechtspraak.nl/binaries/_rts_1768910542320/content/assets/ivo/wi/ivo-wi-technische-documentatie-open-data-van-de-rechtspraak.pdf)). Files already on disk are skipped, so
the fetch is resumable, just run it again to fill in the gaps.

The command below fetches all civil law cases and stores them inside a
`data/xml_output` directory:

```
python rechtspraak_fetcher.py \
  --dsn postgresql://localhost/machina_pauliana \
  --query "SELECT dc_source FROM dossiers WHERE tooiwl_topic ILIKE 'civiel%'" \
  --output-dir ../data/xml_output
```

You can tune the `--rate`, `--concurrency` and `--timeout` if you need to, but keep in mind the spec from Rechtspraak.

## Filter Copy

`filter_copy.py` walks the fetched XML and copies only the cases that reference
**art. 42, 43 or 45 Fw** (the Faillissementspauliana) into a new folder, preserving
the `COURT/YEAR/ECLI.xml` structure. Matching is a case-insensitive regex for an
article reference (`art` / `art.` / `artt.` / `artikel`) near `Fw` /
`Faillissementswet`. Only Rechtbank (`RB*`), Gerechtshof (`GH*`) and Hoge Raad
(`HR`) are kept. Other codes such as `PHR` are skipped.

```
python filter_copy.py ../data/xml_output ../data/xml_output_matches
```

It prints how many files matched out of the total scanned.

## Compare Inview

Wolters Kluwer Inview (formerly Navigator) lists the judicial decisions for a
specific article, e.g. Art. 42 Fw. You can scrape that list (including ECLI numbers)
with the [Instant Data Scraper Chrome extension](https://chromewebstore.google.com/detail/instant-data-scraper/ofaokhiedipichpaobibbnahnkdoiiah)
once you are logged in on Chrome, go to the "Uitspraken" tab for the article and
export the visible table as CSV. (Note that you will have to define in the extension
the table and the next page button.) This text and data mining is allowed here within
the context of scientific research under Art. 15n of the Dutch Copyright Act
(Auteurswet).

`compare_inview.py` then takes that CSV plus the filtered corpus and prints which
Inview ECLIs are **not** part of your local corpus:

```
python compare_inview.py inview_art42.csv ../data/xml_output_matches
```

You can choose to (manually) add those cases, or to use them as validation cases for
a final model that runs on open Rechtspraak data. Cases that are missing are usually
either a misclassification by Wolters Kluwer, or more often simply not part of
the open data from rechtspraak.nl but instead handed to Wolters Kluwer by a lawyer or
requested by them.

Optionally pass the full (civil law) corpus as a third argument. Each missing ECLI is
then also looked up there, so you can tell whether a case is merely absent from your
*filtered* corpus but was in fact fetched as part of the full civil corpus:

```
python compare_inview.py inview_art42.csv ../data/xml_output_matches ../data/xml_output
```
