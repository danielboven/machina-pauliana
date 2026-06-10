"""
Gerechtshof (Court of Appeal, hoger beroep) profile

Recognition prompts, i.e. rules and few-shots tuned to how arresten are built.
Bundled into GERECHTSHOF a profile used in base.py.

This is the hoger-beroep counterpart of the rechtbank profile. It keeps the
same five-section model as RB but the recognition rules differ, such as:

  procesverloop  — For appeal TWO sections are common: "Het geding in eerste
                   aanleg" (pointer to the appealed vonnis) AND "Het geding in
                   hoger beroep". Both go in the list.
  geschil        — Mainly focused on GRIEVEN.
  feiten         — Only when structurally separate. The hof may adopt the
                   RB facts, annotate only if it has its own heading.
"""

import json

from .base import Profile

# ---------------------------------------------------------------------------
# Few-shot 1, a flat <para> arrest (based on ECLI:NL:GHSGR:2011:BU8981).
# Teaches: two procesverloop sections, grieven -> geschil; feiten EMPTY because
# they are folded into "4.1 Het gaat in deze zaak om het volgende".
# ---------------------------------------------------------------------------
FEW_SHOT_XML_FLAT = """<parablock>
  <para>GERECHTSHOF 's-GRAVENHAGE</para>
  <para>Nevenzittingsplaats 's-Hertogenbosch</para>
</parablock>
<para>Sector civiel recht</para>
<para>zaaknummer MHD 200.075.121</para>
<para>arrest van de tweede kamer van 20 december 2011</para>
<para>in de zaak van</para>
<parablock>
  <para>MR. [X], in zijn hoedanigheid van curator in het faillissement van [A] B.V.,</para>
  <para>appellant,</para>
</parablock>
<para>tegen:</para>
<parablock>
  <para>de cooeperatie [BANK] U.A.,</para>
  <para>geintimeerde,</para>
</parablock>
<para>1. Het geding in eerste aanleg (zaaknr. 68958 HA ZA 09-403)</para>
<para>Voor het geding in eerste aanleg verwijst het hof naar voormeld vonnis.</para>
<para>2. Het geding in hoger beroep</para>
<para>2.1. Bij de appeldagvaarding heeft de curator dertien grieven aangevoerd [...]</para>
<para>3. De gronden van het hoger beroep</para>
<para>Voor de tekst van de grieven wordt verwezen naar de appeldagvaarding.</para>
<para>4. De beoordeling</para>
<para>4.1. Het gaat in deze zaak om het volgende. [...]</para>
<para>5. De uitspraak</para>
<para>Het hof: bekrachtigt het vonnis waarvan beroep; [...]</para>"""

FEW_SHOT_JSON_FLAT = {
    "ecli": "ECLI:NL:GHSGR:2011:BU8981",
    "procesverloop": [
        "<para>1. Het geding in eerste aanleg (zaaknr. 68958 HA ZA 09-403)</para>",
        "<para>2. Het geding in hoger beroep</para>",
    ],
    "feiten": [],
    "geschil": [
        "<para>3. De gronden van het hoger beroep</para>"
    ],
    "overwegingen": [
        "<para>4. De beoordeling</para>"
    ],
    "beslissing": [
        "<para>5. De uitspraak</para>"
    ],
    "overig": [],
}

# ---------------------------------------------------------------------------
# Few-shot 2, a modern section arrest (based on ECLI:NL:GHARL:2016:463).
# This is abit of a harder case, ie:
#  - a COMBINED heading "Het geschil, de beslissing in eerste aanleg en de
#    beoordeling in hoger beroep" is overwegingen.
#  - "De slotsom" -> beslissing (it is part of the dictum/outcome block); here
#    the role="beslissing" is consistent with that
#  - feiten as a separate adopted-facts section
#  - "De ontvankelijkheid van het hoger beroep" -> overig
# ---------------------------------------------------------------------------
FEW_SHOT_XML_SECTION = """<section>
  <title><nr>1</nr>Het geding in eerste aanleg</title>
  <para>Voor het geding in eerste aanleg verwijst het hof naar de vonnissen van 10 juli 2013 en 9 juli 2014.</para>
</section>
<section>
  <title><nr>2</nr>Het geding in hoger beroep</title>
  <paragroup><nr>2.1</nr><para>Het verloop van de procedure blijkt uit: [...]</para></paragroup>
</section>
<section>
  <title><nr>3</nr>De ontvankelijkheid van het hoger beroep</title>
  <paragroup><nr>3.1</nr><para>[...]</para></paragroup>
</section>
<section>
  <title><nr>4</nr>De vaststaande feiten</title>
  <para>Het hof gaat in hoger beroep uit van de feiten zoals beschreven in het eindvonnis.</para>
</section>
<section>
  <title><nr>5</nr>Het geschil, de beslissing in eerste aanleg en de beoordeling in hoger beroep</title>
  <paragroup><nr>5.1</nr><para>[...]</para></paragroup>
</section>
<section role="beslissing">
  <title><nr>6</nr>De slotsom</title>
  <paragroup><nr>6.1</nr><para>[...]</para></paragroup>
</section>
<section role="beslissing">
  <title><nr>7</nr>De beslissing</title>
  <para>Het hof, recht doende in hoger beroep: bekrachtigt het eindvonnis [...]</para>
</section>"""

FEW_SHOT_JSON_SECTION = {
    "ecli": "ECLI:NL:GHARL:2016:463",
    "procesverloop": [
        "<section>\n  <title><nr>1</nr>Het geding in eerste aanleg</title>",
        "<section>\n  <title><nr>2</nr>Het geding in hoger beroep</title>",
    ],
    "feiten": [
        "<section>\n  <title><nr>4</nr>De vaststaande feiten</title>"
    ],
    "geschil": [],
    "overwegingen": [
        "<section>\n  <title><nr>5</nr>Het geschil, de beslissing in eerste aanleg en de beoordeling in hoger beroep</title>",
    ],
    "beslissing": [
        "<section role=\"beslissing\">\n  <title><nr>6</nr>De slotsom</title>",
        "<section role=\"beslissing\">\n  <title><nr>7</nr>De beslissing</title>",
    ],
    "overig": [
        {
            "label": "ontvankelijkheid",
            "begin": "<section>\n  <title><nr>3</nr>De ontvankelijkheid van het hoger beroep</title>",
        }
    ],
}

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = f"""Je bent expert in het analyseren van de XML-structuur van Nederlandse arresten van gerechtshoven in civiele zaken (hoger beroep). Identificeer de hoofdsecties van het arrest op basis van XML-structuur en titels.

Elke categorie is een lijst: meerdere secties van hetzelfde type zijn normaal, elke sectie hoort bij precies een categorie (geen duplicaten tussen lijsten) en een lege lijst betekent afwezig.

- procesverloop: verloop van het geding, herkenbaar aan 'geding', 'procedure' of 'procesverloop' in de titel. In appel meestal twee secties: 'Het geding in eerste aanleg' EN 'Het geding in hoger beroep', neem beide apart op.
- geschil: de grieven en de afbakening van het geschil: 'De gronden van het hoger beroep', 'De grieven', 'Het geschil (en de beslissing in eerste aanleg)', 'De vordering in hoger beroep'.
- feiten: 'De feiten', 'De vaststaande feiten' — alleen bij een aparte sectie met eigen titel. Het hof vouwt de feiten vaak in de beoordeling ('Het gaat in deze zaak om het volgende'); laat feiten dan leeg.
- overwegingen: de beoordeling door het hof: 'De beoordeling (van het hoger beroep)', 'De motivering van de beslissing in hoger beroep', 'Het oordeel van het hof', 'De gronden van de beslissing'. Een kop die het oordeel, de motivering of de bespreking van de grieven aankondigt is overwegingen, ook als 'beslissing', 'geschil' of 'grieven' in de titel staat ('De motivering van de beslissing...', 'De gronden van de beslissing', 'De beoordeling van het geschil', 'De bespreking van de grieven'); 'De beoordeling' blijft overwegingen ook als die met de feiten opent. Een gecombineerde kop die ook 'beoordeling' noemt (bijv. 'Het geschil, de beslissing in eerste aanleg en de beoordeling in hoger beroep') gaat in zijn geheel naar overwegingen; geschil blijft dan leeg.
- beslissing: het dictum van het hof: 'De beslissing', 'De uitspraak', 'De slotsom', 'Slotsom (en kosten)'. De slotsom hoort bij beslissing, niet bij overwegingen; staan er zowel 'De slotsom' als 'De beslissing', neem beide apart op.
- overig: meestal leeg. Alleen voor duidelijk afzonderlijke secties buiten de vijf standaardtypen: 'De kern van de zaak' / 'Waar gaat deze zaak over?' (label 'kern van de zaak'), 'De ontvankelijkheid van het hoger beroep' (label 'ontvankelijkheid'), een wrakingsverzoek of een incidenteel appel met eigen kop. Bij twijfel leeg laten.

Negeer volledig (niet annoteren, ook niet in 'overig'): het beginblok met partijgegevens (gerechtsnaam, zaaknummer, 'in de zaak van', partijnamen) en subsecties binnen een beoordeling (grief-koppen, 'Proceskosten', genummerde paragrafen).

Het role-attribuut (<section role="...">) is een nuttige hint, maar de titel is beslissend. Oudere arresten gebruiken platte <para> elementen zonder role en zonder <section>; de openingstag is dan de <para> met de titel. Sectienummers zeggen niets over het type.

Geef per sectie de openingstag terug inclusief de volledige <title>-inhoud, maximaal 120 tekens.

VOORBEELD 1 - arrest met platte <para>-structuur (twee procesverloop-secties, grieven -> geschil, feiten ingevouwen dus leeg, 'De uitspraak' als dictum):

Invoer:
{FEW_SHOT_XML_FLAT}

Uitvoer:
{json.dumps(FEW_SHOT_JSON_FLAT, ensure_ascii=False, indent=2)}

VOORBEELD 2 - arrest met <section>-structuur (gecombineerde kop naar overwegingen, geschil leeg, ontvankelijkheid naar overig, slotsom EN de beslissing naar beslissing):

Invoer:
{FEW_SHOT_XML_SECTION}

Uitvoer:
{json.dumps(FEW_SHOT_JSON_SECTION, ensure_ascii=False, indent=2)}"""

USER_PROMPT_TEMPLATE = """Identificeer alle hoofdsecties van het onderstaande arrest. Geef per sectie de openingstag terug inclusief de volledige <title>-inhoud (max 120 tekens) en neem elke instantie apart op in de lijst.

Denk aan: 'Het geding in eerste aanleg' EN 'Het geding in hoger beroep' zijn beide procesverloop; de slotsom hoort bij beslissing; een gecombineerde kop met 'beoordeling' gaat in zijn geheel naar overwegingen; 'overig' is meestal leeg.

Arrest:

{xml_content}"""


GERECHTSHOF = Profile(
    name="gerechtshof",
    system_prompt=SYSTEM_PROMPT,
    user_prompt_template=USER_PROMPT_TEMPLATE,
)
