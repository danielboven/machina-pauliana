"""Subroutine (RAG): resolve voluntary performance (onverplicht/verplicht).

Contains specific prompt for resolving whether performance was voluntary based
on legal theory. Uses case-based reasoning through retrieval augmented
generation over previous judgments. This subroutine model can for reference
also be found in catala_json_schema/subroutine_onverplicht_schema.json
Note that this JSON schema is not directly linked (purely for reference).

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

# The database RAG label (column) this subroutine filters retrieval on
RAG_LABEL = "onverplicht"


class OnverplichtOutput(BaseModel):
    onverplicht_overwegingen: str = Field(
        description="Motivering of voor de rechtshandeling een in rechte afdwingbare rechtsplicht (uit wet of overeenkomst) bestond."
    )
    onverplicht: bool = Field(
        description="True als de rechtshandeling onverplicht is verricht, false als zij verplicht was."
    )


SYSTEM_PROMPT = """Je bent een jurist gespecialiseerd in het Nederlandse insolventierecht. Beoordeel op basis van de onderstaande casus of de aangevochten rechtshandeling onverplicht is verricht in de zin van artikel 42 Faillissementswet (Fw).

# Wetgeving

## Artikel 42 Faillissementswet

### Lid 1

De curator kan ten behoeve van de boedel elke rechtshandeling die de schuldenaar vóór de faillietverklaring onverplicht heeft verricht en waarvan deze bij dit verrichten wist of behoorde te weten dat daarvan benadeling van de schuldeisers het gevolg zou zijn, door een buitengerechtelijke verklaring vernietigen. Artikel 50, tweede lid, van Boek 3 van het Burgerlijk Wetboek is niet van toepassing.

### Lid 2

Een rechtshandeling anders dan om niet, die hetzij meerzijdig is, hetzij eenzijdig en tot een of meer bepaalde personen gericht, kan wegens benadeling slechts worden vernietigd, indien ook degenen met of jegens wie de schuldenaar de rechtshandeling verrichtte, wisten of behoorden te weten dat daarvan benadeling van de schuldeisers het gevolg zou zijn.


Onverplicht
Een rechtshandeling is onverplicht verricht wanneer daartoe geen op de wet of een overeenkomst berustende rechtsplicht bestond. Beslissend is of de prestatie in rechte kon worden afgedwongen; zo niet, dan is de handeling onverplicht, ook als de schuldenaar feitelijk praktisch niet anders kon. Morele, feitelijke of economische druk schept geen rechtsplicht. De stelplicht en bewijslast van het onverplichte karakter rusten op de curator.

Aandachtspunten:
- Het betalen of zekerstellen van een niet-opeisbare schuld is onverplicht; betaling binnen de geldende betalingstermijn is in beginsel verplicht.
- Zekerheid stellen voor een bestaande schuld is verplicht wanneer daartoe al een verplichting bestond (bijvoorbeeld op grond van de algemene bankvoorwaarden), en anders onverplicht; zekerheid voor nieuw krediet is onverplicht als het aangaan van dat krediet onverplicht was.
- Verkoop gevolgd door verrekening is een onverplichte rechtshandeling van de schuldenaar; de verrekening zelf is een handeling van de schuldeiser en valt buiten art. 42 Fw.
- Een bestaande verplichting kan op een niet-voorgeschreven wijze worden uitgevoerd zonder dat de uitvoering daardoor onverplicht wordt.

Werkwijze: vul eerst het veld "onverplicht_overwegingen" met een motivering op basis van de casus en de eventueel aangereikte uitspraken, en bepaal daarna pas de waarde. Antwoord uitsluitend in het gevraagde JSON-formaat."""


async def run(
    casus: str,
    *,
    model: str = nsm.DEFAULT_MODEL,
    k: int = nsm.DEFAULT_K,
    query_vec: list[float] | None = None,
) -> OnverplichtOutput:
    """Resolve voluntary performance (onverplicht) for the facts of one input
    case using case-based reasoning (RAG over judgments).
    `query_vec` is the shared case embedding."""
    rag_markdown = await nsm.subroutine_rag(
        casus, query_vec, label=RAG_LABEL, k=k
    )
    user_prompt = nsm.subroutine_prompt(casus, rag_markdown)
    return await nsm.complete(
        model, SYSTEM_PROMPT, user_prompt, OnverplichtOutput
    )
