"""Subroutine (RAG): resolves prejudice to creditors.

Contains specific prompt for resolving prejudice to creditors based on legal
theory. Uses case-based reasoning through retrieval augmented generation over
previous judgments. This subroutine model can for reference also be found in
catala_json_schema/subroutine_benadeling_schuldeisers_schema.json
Note that this JSON schema is not directly linked (purely for reference).

Sources used for writing the prompt:
    Pannevis, N.B. (2026). "Schuldeisersbenadeling". In: 16th ed. Deventer:
        Wolters Kluwer. Chap. 7. ISBN 9789013178944.
    Vriesendorp, R.D. (2024). Insolventierecht. Derde druk. Studiereeks
        burgerlijk recht 8. Deventer: Wolters Kluwer. ISBN 978-90-13-17603-2.
    Wessels, B. (2019). Gevolgen van faillietverklaring. 5th ed. Vol. III.
        Insolventierecht. Deventer: Wolters Kluwer. ISBN 978-90-13-15314-9.
"""

from collections.abc import Collection

from pydantic import BaseModel, Field

from . import model as nsm

# The database RAG label (column) this subroutine filters retrieval on
RAG_LABEL = "benadeling_schuldeisers"


class BenadelingSchuldeisersOutput(BaseModel):
    benadeling_schuldeisers_overwegingen: str = Field(
        description="Motivering van de invulling van de benadeling van schuldeisers."
    )
    benadeling_schuldeisers: bool = Field(
        description="True als de schuldeisers zijn benadeeld (minder verhaal of een verstoorde rangorde), anders false."
    )


SYSTEM_PROMPT = """Je bent een jurist gespecialiseerd in het Nederlandse insolventierecht. Beoordeel op basis van de onderstaande casus of de schuldeisers door de aangevochten rechtshandeling zijn benadeeld in de zin van artikel 42 Faillissementswet (Fw).

# Wetgeving

## Artikel 42 Faillissementswet

### Lid 1

De curator kan ten behoeve van de boedel elke rechtshandeling die de schuldenaar vóór de faillietverklaring onverplicht heeft verricht en waarvan deze bij dit verrichten wist of behoorde te weten dat daarvan benadeling van de schuldeisers het gevolg zou zijn, door een buitengerechtelijke verklaring vernietigen. Artikel 50, tweede lid, van Boek 3 van het Burgerlijk Wetboek is niet van toepassing.

### Lid 2

Een rechtshandeling anders dan om niet, die hetzij meerzijdig is, hetzij eenzijdig en tot een of meer bepaalde personen gericht, kan wegens benadeling slechts worden vernietigd, indien ook degenen met of jegens wie de schuldenaar de rechtshandeling verrichtte, wisten of behoorden te weten dat daarvan benadeling van de schuldeisers het gevolg zou zijn.


Benadeling van de schuldeisers
Of er benadeling is, wordt bepaald door een vermogensvergelijking: de hypothetische situatie waarin de schuldeisers zouden hebben verkeerd zonder de gewraakte rechtshandeling wordt vergeleken met de situatie waarin zij feitelijk verkeren als die handeling in stand blijft. De benadeling moet aanwezig zijn op het moment waarop de curator zijn rechten doet gelden (leer van de middellijke benadeling).

Bij die vergelijking:
- Weeg zowel de nadelige als de gunstige gevolgen van de rechtshandeling mee en beoordeel de transactie in haar geheel.
- Betrek in het hypothetische scenario ook wat daarna daadwerkelijk zou zijn gebeurd (een reële, navolgbare inschatting), niet wat enkel had gekund.

Benadeling kan de vorm aannemen van (i) vermindering van het actief, (ii) vermeerdering van de passiva, of (iii) verstoring van de rangorde tussen de schuldeisers, ook als per saldo geen vermogensvermindering optreedt, bijvoorbeeld wanneer voor een reële prijs is gepresteerd maar de opbrengst aan één schuldeiser ten goede komt. Voldoende is dat de schuldeisers in het algemeen zijn benadeeld; benadeling van één schuldeiser kan volstaan.

Geen benadeling is er bijvoorbeeld wanneer ook zonder de handeling alle schulden voldaan hadden kunnen worden, wanneer de schuldeisers zich toch niet op de betrokken goederen hadden kunnen verhalen (er rustten zekerheidsrechten op en de gerechtigde zou hebben uitgewonnen), of wanneer de schuldeisers slechts een voordeel is ontgaan zonder daadwerkelijk nadeel.

Werkwijze: vul eerst het veld "benadeling_schuldeisers_overwegingen" met een motivering op basis van de casus en de eventueel aangereikte uitspraken, en bepaal daarna pas de waarde. Antwoord uitsluitend in het gevraagde JSON-formaat."""


async def run(
    casus: str,
    *,
    model: str = nsm.DEFAULT_MODEL,
    k: int = nsm.DEFAULT_K,
    query_vec: list[float] | None = None,
    exclude: Collection[str] = (),
) -> BenadelingSchuldeisersOutput:
    """Resolve prejudice to creditors (benadeling schuldeisers) for the facts
    of one input case using case-based reasoning (RAG over judgments).
    `query_vec` is the shared case embedding; `exclude` ablates judgments from
    retrieval."""
    rag_markdown = await nsm.subroutine_rag(
        casus, query_vec, label=RAG_LABEL, k=k, exclude=exclude
    )
    user_prompt = nsm.subroutine_prompt(casus, rag_markdown)
    return await nsm.complete(
        model, SYSTEM_PROMPT, user_prompt, BenadelingSchuldeisersOutput
    )
