"""Coroutine: resolve the factual art. 42 Fw inputs without case law.

Given the facts of a case, this routine resolves the inputs of the Catala scope
`FaillissementspaulianaArt42 that do not require case-based reasoning (RAG).

Sources used for writing the prompt:
    Pannevis, N.B. (2026). "Schuldeisersbenadeling". In: 16th ed. Deventer:
        Wolters Kluwer. Chap. 7. ISBN 9789013178944.
    Vriesendorp, R.D. (2024). Insolventierecht. Derde druk. Studiereeks
        burgerlijk recht 8. Deventer: Wolters Kluwer. ISBN 978-90-13-17603-2.
    Wessels, B. (2019). Gevolgen van faillietverklaring. 5th ed. Vol. III.
        Insolventierecht. Deventer: Wolters Kluwer. ISBN 978-90-13-15314-9.
"""

from pydantic import BaseModel, Field

from . import model as nsm


# ---------------------------------------------------------------------------
# Structured output schema (mirrors coroutine_schema.json)
# ---------------------------------------------------------------------------


class Handeling(BaseModel):
    is_rechtshandeling_overwegingen: str = Field(
        description="Korte motivering of de gewraakte handeling een rechtshandeling is."
    )
    is_rechtshandeling: bool = Field(
        description="True als het om een rechtshandeling gaat, false als het geen rechtshandeling betreft, zoals bij een feitelijke handeling of schijnhandeling."
    )
    datum_rechtshandeling: str = Field(
        description="Datum waarop de rechtshandeling is verricht, in het formaat yyyy-mm-dd. Bij meerdere rechtshandelingen die gezamenlijk worden genomen, gebruik dan de eerste datum."
    )
    verricht_door_de_schuldenaar_overwegingen: str = Field(
        description="Korte motivering of de rechtshandeling door de schuldenaar zelf is verricht."
    )
    verricht_door_de_schuldenaar: bool = Field(
        description="True als de schuldenaar (niet een derde) de rechtshandeling verrichtte."
    )
    om_niet_overwegingen: str = Field(
        description="Korte motivering of de rechtshandeling om niet dan wel om baat is."
    )
    om_niet: bool = Field(
        description="True als de rechtshandeling om niet is (zonder wederprestatie), false bij een rechtshandeling anders dan om niet (om baat)."
    )


class Faillissement(BaseModel):
    datum_faillietverklaring: str = Field(
        description="Datum van de faillietverklaring (waarop faillissement is uitgesproken), in het formaat yyyy-mm-dd."
    )


class CoroutineOutput(BaseModel):
    handeling: Handeling
    faillissement: Faillissement


# ---------------------------------------------------------------------------
# Prompts (Dutch)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """Je bent een jurist gespecialiseerd in het Nederlandse insolventierecht. Uit de onderstaande casus haal je de feitelijke gegevens die nodig zijn om de faillissementspauliana van artikel 42 Faillissementswet (Fw) te beoordelen. Beoordeel hier de feitelijke vereisten. De inhoudelijke vereisten (onverplicht, benadeling van de schuldeisers, wetenschap) blijven hier buiten beschouwing.

# Wetgeving

## Artikel 42 Faillissementswet

### Lid 1

De curator kan ten behoeve van de boedel elke rechtshandeling die de schuldenaar vóór de faillietverklaring onverplicht heeft verricht en waarvan deze bij dit verrichten wist of behoorde te weten dat daarvan benadeling van de schuldeisers het gevolg zou zijn, door een buitengerechtelijke verklaring vernietigen. Artikel 50, tweede lid, van Boek 3 van het Burgerlijk Wetboek is niet van toepassing.

### Lid 2

Een rechtshandeling anders dan om niet, die hetzij meerzijdig is, hetzij eenzijdig en tot een of meer bepaalde personen gericht, kan wegens benadeling slechts worden vernietigd, indien ook degenen met of jegens wie de schuldenaar de rechtshandeling verrichtte, wisten of behoorden te weten dat daarvan benadeling van de schuldeisers het gevolg zou zijn.


Beoordeel de volgende gegevens:

- Rechtshandeling (is_rechtshandeling): een rechtshandeling vereist een op een rechtsgevolg gerichte wil die zich door een verklaring heeft geopenbaard (art. 3:33 BW). Het begrip is ruim en omvat zowel obligatoire als goederenrechtelijke handelingen. Feitelijke handelingen en schijnhandelingen vallen erbuiten en kunnen niet met de pauliana worden vernietigd (vgl. HR 21 juni 2013, Eringa q.q./ABN AMRO).

- Verricht door de schuldenaar (verricht_door_de_schuldenaar): de pauliana richt zich uitsluitend tegen een rechtshandeling van de schuldenaar zelf, niet tegen die een derde bijvoorbeeld. Doorgaans volgt dit zonder meer uit de feiten.

- Om niet of om baat (om_niet): een rechtshandeling is "om niet" wanneer de schuldenaar geen wederprestatie bedingt. Staat tegenover de prestatie een reële tegenprestatie, dan is zij "anders dan om niet" (om baat). Een dividenduitkering is om niet; de betaling van andermans schuld (art. 6:30 BW) is niet zonder meer om niet, dat hangt af van een reële, daarmee verband houdende tegenprestatie.

- Datums (datum_rechtshandeling, datum_faillietverklaring): noteer beide in het formaat yyyy-mm-dd. Op grond van het fixatiebeginsel (art. 23 Fw) is alleen een handeling van vóór de faillietverklaring vatbaar voor vernietiging.

Werkwijze: vul voor elk vereiste eerst het bijbehorende "_overwegingen"-veld met een korte motivering op basis van de feiten, en bepaal daarna pas de bijbehorende waarde. Baseer je uitsluitend op de aangeleverde feiten. Antwoord uitsluitend in het gevraagde JSON-formaat."""

# The case facts are appended under a Markdown header, leaving room for the input.
USER_PROMPT_TEMPLATE = """Hieronder volgen de feiten van een casus. Haal hieruit de vereiste (feitelijke) gegevens voor artikel 42 Fw.

# Casus

{casus}"""


async def run(casus: str, *, model: str = nsm.DEFAULT_MODEL) -> CoroutineOutput:
    """Resolve the factual art. 42 Fw inputs for the facts of one case."""
    return await nsm.complete(
        model,
        SYSTEM_PROMPT,
        USER_PROMPT_TEMPLATE.format(casus=casus),
        CoroutineOutput,
    )
