"""
Hoge Raad (Supreme Court, cassation) profile

Recognition prompts, i.e. rules and few-shots tuned to how arresten are built.
Bundled into HOGE_RAAD a profile used in base.py.

This file keeps the same five-section model as RB and GH but the recognition
rules differ, such as:

  procesverloop  — Pre-2019 arresten split this in two: "Het geding in
                   feitelijke instanties" and "Het
                   geding in cassatie". Since 2019 it is usually one section,
                   "Procesverloop". Both styles go in the list.
  geschil        — Effectively always empty. The HR rules on cassation grounds,
                   not on a dispute of its own.
  feiten         — "Uitgangspunten en feiten" / "Uitgangspunten in cassatie"
                   when separate. Pre-2019 the HR usually folds the facts into
                   the opening of "Beoordeling van het middel" ("In cassatie kan
                   van het volgende worden uitgegaan"), feiten is then empty.
  overwegingen   — "Beoordeling van het middel(en)", often both "in het
                   principale beroep" and "in het incidentele beroep".
"""

import json

from .base import Profile

# ---------------------------------------------------------------------------
# Few-shot 1, an older flat-<para> arrest (based on ECLI:NL:HR:1992:ZC0615).
# Headings sit in <emphasis role="underline"> inside a <para>; there are no
# <section> wrappers and no role attributes.
# Teaches: the pre-2019 split procesverloop ("feitelijke instanties" +
# "cassatie").
# ---------------------------------------------------------------------------
FEW_SHOT_XML_FLAT = """<parablock>
  <para>
    <emphasis role="bold">Hoge Raad der Nederlanden</emphasis>
  </para>
  <para>in de zaak van:</para>
  <para>Mr. C.C. BOSSELAAR, in zijn hoedanigheid van curator, EISER tot cassatie,</para>
  <para>tegen INTERNIBER B.V., VERWEERSTER in cassatie.</para>
</parablock>
<para>
  <emphasis role="underline">1. Het geding in feitelijke instanties</emphasis>
</para>
<parablock>
  <para>Eiser tot cassatie heeft verweerster gedagvaard voor de Rechtbank te Haarlem [...]</para>
</parablock>
<para>
  <emphasis role="underline">2. Het geding in cassatie</emphasis>
</para>
<parablock>
  <para>Tegen het arrest van het Hof heeft de curator beroep in cassatie ingesteld. [...]</para>
</parablock>
<para>
  <emphasis role="underline">3. Beoordeling van het middel</emphasis> </para>
<parablock>
  <para>3.1 In cassatie moet van het volgende worden uitgegaan. [...]</para>
  <para>3.2 Het eerste onderdeel klaagt dat het Hof van een onjuiste rechtsopvatting heeft blijk gegeven [...]</para>
</parablock>
<para>
  <emphasis role="underline">4. Beslissing</emphasis>
</para>
<parablock>
  <para>De Hoge Raad: vernietigt het arrest van het Hof te Amsterdam van 6 december 1990; [...]</para>
</parablock>"""

FEW_SHOT_JSON_FLAT = {
    "procesverloop": [
        "<para>\n  <emphasis role=\"underline\">1. Het geding in feitelijke instanties</emphasis>",
        "<para>\n  <emphasis role=\"underline\">2. Het geding in cassatie</emphasis>",
    ],
    "feiten": [],
    "geschil": [],
    "overwegingen": [
        "<para>\n  <emphasis role=\"underline\">3. Beoordeling van het middel</emphasis>"
    ],
    "beslissing": [
        "<para>\n  <emphasis role=\"underline\">4. Beslissing</emphasis>"
    ],
    "overig": [],
}

# ---------------------------------------------------------------------------
# Few-shot 2, a modern <section> arrest (based on ECLI:NL:HR:2025:975.
# Sections carry a role attribute and a <title>.
# Teaches: the post-2019 single "Procesverloop"; "Uitgangspunten en feiten" as
# a separate feiten-section, geschil remains empty.
# ---------------------------------------------------------------------------
FEW_SHOT_XML_SECTION = """<section role="procesverloop">
  <title>
    <nr>1</nr>Procesverloop</title>
  <parablock>
    <para>Voor het verloop van het geding in feitelijke instanties verwijst de Hoge Raad naar: [...]</para>
    <para>De conclusie van de Advocaat-Generaal B.F. Assink strekt tot verwerping van het principale cassatieberoep. [...]</para>
  </parablock>
</section>
<section>
  <title>
    <nr>2</nr>Uitgangspunten en feiten</title>
  <paragroup>
    <nr>2.1</nr>
    <para>Deze zaak gaat over de wetenschap van benadeling in de zin van art. 42 Fw bij een samenstel van rechtshandelingen. [...]</para>
  </paragroup>
</section>
<section role="overwegingen">
  <title>
    <nr>3</nr>Beoordeling van het middel in het principale beroep</title>
  <paragroup>
    <nr>3.1</nr>
    <para>[...]</para>
  </paragroup>
</section>
<section role="beslissing">
  <title>
    <nr>4</nr>Beslissing</title>
  <para>De Hoge Raad: verwerpt het principale en het incidentele beroep; [...]</para>
</section>"""

FEW_SHOT_JSON_SECTION = {
    "procesverloop": [
        "<section role=\"procesverloop\">\n  <title>\n    <nr>1</nr>Procesverloop</title>",
    ],
    "feiten": [
        "<section>\n  <title>\n    <nr>2</nr>Uitgangspunten en feiten</title>"
    ],
    "geschil": [],
    "overwegingen": [
        "<section role=\"overwegingen\">\n  <title>\n    <nr>3</nr>Beoordeling van het middel in het principale beroep</title>",
    ],
    "beslissing": [
        "<section role=\"beslissing\">\n  <title>\n    <nr>4</nr>Beslissing</title>",
    ],
    "overig": [],
}

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = f"""Je bent expert in het analyseren van de XML-structuur van Nederlandse arresten van de Hoge Raad in civiele zaken (cassatie). Identificeer de hoofdsecties van het arrest op basis van XML-structuur en titels.

Elke categorie is een lijst: meerdere secties van hetzelfde type zijn mogelijk, elke sectie hoort bij precies een categorie (geen duplicaten tussen lijsten) en een lege lijst betekent afwezig.

- procesverloop: verloop van het geding, herkenbaar aan 'geding', 'procedure' of 'procesverloop' in de titel. Voor 2019 meestal twee secties: 'Het geding in feitelijke instanties' en 'Het geding in cassatie', neem beide dan apart op. Sinds 2019 doorgaans één sectie: 'Procesverloop'. Ook 'De prejudiciële procedure' valt hieronder.
- feiten: de feitelijke uitgangspunten, herkenbaar aan 'Uitgangspunten en feiten', 'Uitgangspunten in cassatie', 'De feiten'. Alleen bij een aparte sectie met eigen titel annoteren. Is er geen eigen kop, laat feiten dan leeg.
- geschil: bij de Hoge Raad vrijwel altijd afwezig. Laat leeg, tenzij er een duidelijke eigen kop 'Het geschil', of dergelijke staat.
- overwegingen: de beoordeling van de cassatiemiddelen door de HR: 'Beoordeling van het middel', 'Beoordeling van de middelen'. Kan gesplitst zijn in 'in het principale beroep' en 'in het (voorwaardelijk) incidentele beroep', neem die elk apart op. Ook 'Beantwoording van de prejudiciële vragen' valt hieronder.
- beslissing: het dictum: 'Beslissing'.
- overig: meestal leeg. Alleen voor duidelijk afzonderlijke secties buiten de vijf standaardtypen, zoals een aparte kostensectie ('Proceskosten in cassatie', 'Kosten van het geding in cassatie') of, bij prejudiciële verwijzing naar het HvJEU, 'Vragen van uitleg'. Bij twijfel leeg laten.

Negeer volledig (niet annoteren, ook niet in 'overig'): het beginblok met partijgegevens ('Hoge Raad der Nederlanden', 'Arrest', nummer/zaaknummer, datum, kamer, partijnamen, advocaten) en de slotformule met de samenstelling van de raadsheren en de uitspraakdatum.

Het role-attribuut (<section role="...">) is een nuttige hint, maar de titel is beslissend. Oudere arresten gebruiken platte <para> elementen zonder role en zonder <section>; de titel staat dan in een <emphasis> binnen de <para> en de openingstag is die <para>. Sectienummers zeggen niets over het type.

Een sectiekop is een korte titel van enkele woorden (bijv. 'Beoordeling van het middel'). Geef nooit een genummerde tussenalinea (3.1, 3.2, ...) of een hele zin of alinea terug: dat is inhoud, geen kop. Annoteer alleen de hoofdsecties; negeer genummerde subalinea's binnen een sectie.

Geef per sectie de openingstag terug inclusief de volledige <title>-inhoud (of, bij oude arresten, de <emphasis>-titel), maximaal 120 tekens.

VOORBEELD 1 - ouder arrest met platte <para>/<emphasis>-structuur (gesplitst procesverloop, feiten ingevouwen in 'Beoordeling van het middel' dus leeg, geschil leeg):

Invoer:
{FEW_SHOT_XML_FLAT}

Uitvoer:
{json.dumps(FEW_SHOT_JSON_FLAT, ensure_ascii=False, indent=2)}

VOORBEELD 2 - modern arrest met <section>-structuur (één procesverloop, 'Uitgangspunten en feiten' als aparte feiten-sectie, 'Beoordeling van het middel in het principale beroep' naar overwegingen, geschil leeg):

Invoer:
{FEW_SHOT_XML_SECTION}

Uitvoer:
{json.dumps(FEW_SHOT_JSON_SECTION, ensure_ascii=False, indent=2)}"""

USER_PROMPT_TEMPLATE = """Identificeer alle hoofdsecties van het onderstaande arrest. Geef per sectie de openingstag terug inclusief de volledige <title>-inhoud (max 120 tekens) en neem elke instantie apart op in de lijst.

Denk aan: alleen korte sectiekoppen, geen genummerde tussenalinea's of hele zinnen; 'Het geding in feitelijke instanties' EN 'Het geding in cassatie' zijn beide procesverloop; geschil en (zonder aparte feiten-kop) feiten zijn bij de Hoge Raad vrijwel altijd leeg. 'Beoordeling van het middel' in het principale én incidentele beroep zijn elk een aparte overweging.

Arrest:

{xml_content}"""


HOGE_RAAD = Profile(
    name="hoge_raad",
    system_prompt=SYSTEM_PROMPT,
    user_prompt_template=USER_PROMPT_TEMPLATE,
)
