"""
Rechtbank (District Court, eerste aanleg) profile.

Recognition prompts, ie rules and few-shots tuned to the structure of vonnis
eerste aanleg. Bundled into RECHTBANK, profile used by the shared base.
in base.py.
"""

import json

from .base import Profile

# ---------------------------------------------------------------------------
# First few-shot based on ECLI:NL:RBSHE:2010:BM8082. This is a flat-<para>
# document (no <section>-wrappers, no role-attributes).
# ---------------------------------------------------------------------------
FEW_SHOT_XML = """<parablock>
  <para>vonnis</para>
  <para>RECHTBANK 'S-HERTOGENBOSCH</para>
</parablock>
<para>Sector civiel recht</para>
<para>zaaknummer / rolnummer: 212581 / KG ZA 10-337</para>
<para>Vonnis in kort geding van 16 juni 2010</para>
<para>in de zaak van</para>
<parablock>
  <para>1. de burgerrechtelijke maatschap MAATSCHAP ABEN &amp; SLAG ADVOCATEN, ...</para>
  <para>2. MR. ...</para>
  <para>eisers,</para>
</parablock>
<para>tegen</para>
<parablock>
  <para>1. [gedaagde sub 1], ...</para>
  <para>2. [gedaagde sub 2], ...</para>
  <para>gedaagden.</para>
</parablock>
<para>1. De procedure</para>
<para>1.1. Eisers hebben bij exploot van 28 mei [gedaagden] in kort geding gedagvaard.</para>
<para>1.4. [gedaagde sub 2] heeft tijdens de behandeling gezegd dat hij een beroep op wraking deed. [...]</para>
<para>2. Het wrakingsverzoek</para>
<para>2.1. Voor spoedeisende zaken [...]</para>
<para>3. De relevante vaststaande feiten</para>
<para>3.1. Bij vonnis van 18 april 2007 [...]</para>
<para>4. Het geschil</para>
<para>4.1. Eisers vorderen thans in dit geding [...]</para>
<para>5. De beoordeling</para>
<para>5.1. De vorderingen [...]</para>
<para>6. De beslissing</para>
<para>De voorzieningenrechter</para>
<para>6.1. wijst de vorderingen af;</para>"""

FEW_SHOT_JSON = {
    "procesverloop": [
        "<para>1. De procedure</para>"
    ],
    "feiten": [
        "<para>3. De relevante vaststaande feiten</para>"
    ],
    "geschil": [
        "<para>4. Het geschil</para>"
    ],
    "overwegingen": [
        "<para>5. De beoordeling</para>"
    ],
    "beslissing": [
        "<para>6. De beslissing</para>"
    ],
    "overig": [
        {
            "label": "wrakingsverzoek",
            "begin": "<para>2. Het wrakingsverzoek</para>",
        }
    ],
}

# ---------------------------------------------------------------------------
# Second few-shot, party-blocks present (can be ignored),
# "De procedure" used as procesverloop, no role-attributes, overig is empty.
# This is what most vonnissen look like.
# ---------------------------------------------------------------------------
FEW_SHOT_XML_COMMON = """<section>
  <title><nr>1</nr> [gedaagde 1] ,</title>
  <paragroup><para>wonende te [woonplaats]</para></paragroup>
</section>
<section>
  <title><nr>1</nr>De procedure</title>
  <paragroup><nr>1.1</nr><para>Het verloop van de procedure blijkt uit: [...]</para></paragroup>
</section>
<section>
  <title><nr>2</nr>De feiten</title>
  <paragroup><nr>2.1</nr><para>[vaststaande feiten...]</para></paragroup>
</section>
<section>
  <title><nr>3</nr>Het geschil</title>
  <paragroup><nr>3.1</nr><para>[vordering en verweer...]</para></paragroup>
</section>
<section>
  <title><nr>4</nr>De beoordeling</title>
  <paragroup><nr>4.1</nr><para>[juridische beoordeling...]</para></paragroup>
  <paragroup><para>Proceskosten</para><para>[kostenoverwegingen...]</para></paragroup>
</section>
<section>
  <title><nr>5</nr>De beslissing</title>
  <paragroup><nr>5.1</nr><para>[dictum...]</para></paragroup>
</section>"""

FEW_SHOT_JSON_COMMON = {
    "procesverloop": [
        "<section>\n  <title><nr>1</nr>De procedure</title>"
    ],
    "feiten": [
        "<section>\n  <title><nr>2</nr>De feiten</title>"
    ],
    "geschil": [
        "<section>\n  <title><nr>3</nr>Het geschil</title>"
    ],
    "overwegingen": [
        "<section>\n  <title><nr>4</nr>De beoordeling</title>"
    ],
    "beslissing": [
        "<section>\n  <title><nr>5</nr>De beslissing</title>"
    ],
    "overig": [],
}

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = f"""Je bent expert in het analyseren van de XML-structuur van Nederlandse vonnissen van rechtbanken in civiele zaken (eerste aanleg). Identificeer de hoofdsecties van het vonnis op basis van XML-structuur en titels.

Elke categorie is een lijst: meerdere secties van hetzelfde type zijn mogelijk, elke sectie hoort bij precies een categorie (geen duplicaten tussen lijsten) en een lege lijst betekent afwezig.

- procesverloop: 'De procedure', 'Het procesverloop', 'Het verloop van de procedure', 'Het verloop van het geding'. '(1.) De procedure' is altijd procesverloop, ook zonder role-attribuut.
- feiten: 'De feiten', 'De vaststaande feiten', alleen bij een aparte sectie met eigen titel, anders leeg laten.
- geschil: 'Het geschil', 'De vordering', 'Het verweer', 'De vordering en het verweer', 'Standpunten van partijen', telkens ook met 'in conventie'/'in reconventie'. Neem elke vordering-, verweer- en standpunt-sectie apart op. Een aparte 'Het verweer'-sectie hoort bij geschil, nooit bij overwegingen.
- overwegingen: de beoordeling door de rechter: 'De (verdere) beoordeling (van het geschil)', 'De beoordeling in conventie/in reconventie/in het incident', 'Gronden van de beslissing', 'Rechtsoverwegingen'. Neem elke beoordeling-sectie apart op.
- beslissing: het dictum: 'De beslissing', 'Beslissing', soms zonder kop en in dat geval beginnend met 'De rechtbank, rechtdoende:'.
- overig: meestal leeg. Alleen voor duidelijk afzonderlijke secties buiten de vijf standaardtypen: 'De kern van de zaak' / 'De zaak in het kort' / 'Waar gaat deze zaak over?' (label 'kern van de zaak') of een wrakingsverzoek (label 'wrakingsverzoek'). Bij twijfel leeg laten.

Negeer volledig (niet annoteren, ook niet in 'overig'): het beginblok met partijgegevens (rechtbanknaam, zaaknummer, 'in de zaak van', partijnamen, genummerde <section>-elementen met alleen een partijnaam zoals '<nr>1</nr> [gedaagde 1]') en subsecties binnen een beoordeling ('Proceskosten', 'De cessie', genummerde paragrafen).

Het role-attribuut (<section role="...">) is een nuttige hint, maar de titel is beslissend. Veel vonnissen gebruiken platte <para> elementen zonder role en zonder <section>; de openingstag is dan de <para> met de titel. Sectienummers zeggen niets over het type.

Geef per sectie de openingstag terug inclusief de volledige <title>-inhoud, maximaal 120 tekens.

VOORBEELD 1 — vonnis met platte <para>-structuur en een wrakingsverzoek (uitzonderlijk geval met 'overig'):

Invoer:
{FEW_SHOT_XML}

Uitvoer:
{json.dumps(FEW_SHOT_JSON, ensure_ascii=False, indent=2)}

VOORBEELD 2 — typisch vonnis (de meest voorkomende structuur, 'overig' is leeg):

Invoer:
{FEW_SHOT_XML_COMMON}

Uitvoer:
{json.dumps(FEW_SHOT_JSON_COMMON, ensure_ascii=False, indent=2)}"""

USER_PROMPT_TEMPLATE = """Identificeer alle hoofdsecties van het onderstaande vonnis. Geef per sectie de openingstag terug inclusief de volledige <title>-inhoud (max 120 tekens) en neem elke instantie apart op in de lijst.

Denk aan: neem elke vordering- en verweer-sectie apart op in geschil; 'overig' is meestal leeg; negeer partijgegevens aan het begin van het vonnis.

Vonnis:

{xml_content}"""


RECHTBANK = Profile(
    name="rechtbank",
    system_prompt=SYSTEM_PROMPT,
    user_prompt_template=USER_PROMPT_TEMPLATE,
)
