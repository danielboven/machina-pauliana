"""Subroutine (RAG): resolves knowledge criterium.

Contains specific prompt for resolving knowledge criterium based on legal
theory. Uses case-based reasoning through retrieval augmented generation over
previous judgments. This subroutine model can for reference also be found in
catala_json_schema/subroutine_wetenschap_schema.json
Note that this JSON schema is not directly linked (purely for reference).

Knowledge of the prejudice to creditors can be (1) established directly,
or (2) presumed via the evidentiary presumptions of art. 43 Fw (both sides)
or art. 45 Fw (debtor side only). A presumption can be rebutted.

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
RAG_LABEL = "wetenschap"


class WetenschapOutput(BaseModel):
    wetenschap_overwegingen: str = Field(
        description="Motivering: is de wetenschap rechtstreeks aangetoond, of wordt zij via een bewijsvermoeden (art. 43/45 Fw) vermoed, en is dat vermoeden ontzenuwd?"
    )
    wetenschap_schuldenaar_aangetoond: bool = Field(
        description="True als rechtstreeks (los van enig bewijsvermoeden) is aangetoond dat de schuldenaar wist of behoorde te weten dat benadeling het gevolg zou zijn."
    )
    wetenschap_wederpartij_aangetoond: bool | None = Field(
        default=None,
        description="True/false als rechtstreeks is beoordeeld of de wederpartij die wetenschap had (bij een rechtshandeling anders dan om niet). None als de feiten hier geen aanleiding toe geven.",
    )
    vermoeden_wetenschap_schuldenaar_tegenbewijs: bool | None = Field(
        default=None,
        description="True als een toepasselijk bewijsvermoeden aan de zijde van de schuldenaar met succes is ontzenuwd (aannemelijk dat faillissement en tekort niet voorzienbaar waren), false als het tegenbewijs niet slaagt. None indien geen vermoeden speelt.",
    )
    vermoeden_wetenschap_wederpartij_tegenbewijs: bool | None = Field(
        default=None,
        description="True als het bewijsvermoeden van art. 43 Fw aan de zijde van de wederpartij met succes is ontzenuwd, false als het tegenbewijs niet slaagt. None indien geen vermoeden speelt.",
    )
    tegen_onderwaarde: bool | None = Field(
        default=None,
        description="True als de waarde van de verbintenis van de schuldenaar die van de tegenprestatie aanmerkelijk overtreft (bewijsvermoeden art. 43 lid 1 sub 1°). None indien niet aan de orde.",
    )
    voldoening_of_zekerheid_niet_opeisbare_schuld: bool | None = Field(
        default=None,
        description="True bij voldoening van of zekerheidstelling voor een niet-opeisbare schuld (bewijsvermoeden art. 43 lid 1 sub 2°). None indien niet aan de orde.",
    )
    gelieerde_partij: bool | None = Field(
        default=None,
        description="True als de rechtshandeling is verricht met of jegens een gelieerde partij in de zin van het bewijsvermoeden van art. 43 lid 1 sub 3°-6° (familie- of rechtspersoonlijke band). None indien niet aan de orde.",
    )
    reeds_verplicht_voor_aanvang_termijn: bool | None = Field(
        default=None,
        description="True als de schuldenaar zich al vóór aanvang van de jaartermijn tot de rechtshandeling had verplicht (sluit het bewijsvermoeden van art. 43 Fw uit). None indien bewijsvermoeden van art. 43 Fw niet aan de orde komt.",
    )


SYSTEM_PROMPT = """Je bent een jurist gespecialiseerd in het Nederlandse insolventierecht. Beoordeel op basis van de onderstaande casus het wetenschapsvereiste van de faillissementspauliana (art. 42 Fw), inclusief de bewijsvermoedens van art. 43 en 45 Fw.

# Wetgeving

## Artikel 42 Faillissementswet

### Lid 1

De curator kan ten behoeve van de boedel elke rechtshandeling die de schuldenaar vóór de faillietverklaring onverplicht heeft verricht en waarvan deze bij dit verrichten wist of behoorde te weten dat daarvan benadeling van de schuldeisers het gevolg zou zijn, door een buitengerechtelijke verklaring vernietigen. Artikel 50, tweede lid, van Boek 3 van het Burgerlijk Wetboek is niet van toepassing.

### Lid 2

Een rechtshandeling anders dan om niet, die hetzij meerzijdig is, hetzij eenzijdig en tot een of meer bepaalde personen gericht, kan wegens benadeling slechts worden vernietigd, indien ook degenen met of jegens wie de schuldenaar de rechtshandeling verrichtte, wisten of behoorden te weten dat daarvan benadeling van de schuldeisers het gevolg zou zijn.

## Artikel 43 Faillissementswet

### Lid 1

Indien de rechtshandeling waardoor de schuldeisers zijn benadeeld, is verricht binnen een jaar voor de faillietverklaring en de schuldenaar zich niet reeds voor de aanvang van die termijn daartoe had verplicht, wordt de aan het slot van artikel 42, eerste lid, eerste zin, bedoelde wetenschap, behoudens tegenbewijs, vermoed aan beide zijden te bestaan:

#### Sub 1°

bij overeenkomsten, waarbij de waarde der verbintenis aan de zijde van de schuldenaar aanmerkelijk die der verbintenis aan de andere zijde overtreft;

#### Sub 2°

bij rechtshandelingen ter voldoening van of zekerheidstelling voor een niet opeisbare schuld;

#### Sub 3°

bij rechtshandelingen, door de schuldenaar die een natuurlijk persoon is, verricht met of jegens:
a) zijn echtgenoot, zijn pleegkind of een bloed- of aanverwant tot in de derde graad;
b) een rechtspersoon waarin hij, zijn echtgenoot, zijn pleegkind of een bloed- of aanverwant tot in de derde graad bestuurder of commissaris is, dan wel waarin deze personen, afzonderlijk of tezamen, als aandeelhouder rechtstreeks of middellijk voor ten minste de helft van het geplaatste kapitaal deelnemen;

#### Sub 4°

bij rechtshandelingen, door de schuldenaar die rechtspersoon is, verricht met of jegens een natuurlijk persoon,
a) die bestuurder of commissaris van de rechtspersoon is, dan wel met of jegens diens echtgenoot, pleegkind of bloed- of aanverwant tot in de derde graad:
b) die al dan niet tezamen met zijn echtgenoot, zijn pleegkinderen en zijn bloed- of aanverwanten tot in de derde graad, als aandeelhouder rechtstreeks of middellijk voor ten minste de helft van het geplaatste kapitaal deelneemt;
c) wiens echtgenoot, pleegkinderen of bloed- of aanverwanten tot in de derde graad, afzonderlijk of tezamen, als aandeelhouder rechtstreeks of middellijk voor tenminste de helft van het geplaatste kapitaal deelnemen;

#### Sub 5°

bij rechtshandelingen, door de schuldenaar die rechtspersoon is, verricht met of jegens een andere rechtspersoon, indien
a) een van deze rechtspersonen bestuurder is van de andere;
b) een bestuurder, natuurlijk persoon, van een van deze rechtspersonen, of diens echtgenoot, pleegkind of bloed- of aanverwant tot in de derde graad, bestuurder is van de andere;
c) een bestuurder, natuurlijk persoon, of een commissaris van een van deze rechtspersonen, of diens echtgenoot, pleegkind of bloed- of aanverwant tot in de derde graad, afzonderlijk of tezamen, als aandeelhouder rechtstreeks of middellijk voor ten minste de helft van het geplaatste kapitaal deelneemt in de andere;
d) in beide rechtspersonen voor ten minste de helft van het geplaatste kapitaal rechtstreeks of middellijk wordt deelgenomen door dezelfde rechtspersoon, dan wel dezelfde natuurlijke persoon, al dan niet tezamen met zijn echtgenoot, zijn pleegkinderen en zijn bloed- of aanverwanten tot in de derde graad;

#### Sub 6°

bij rechtshandelingen, door de schuldenaar die rechtspersoon is, verricht met of jegens een groepsmaatschappij.

### Lid 2

Met een echtgenoot wordt een geregistreerde partner of een andere levensgezel gelijkgesteld.

#### Lid 3

Onder pleegkind wordt verstaan hij die duurzaam als eigen kind is verzorgd en opgevoed.

#### Lid 4

Onder bestuurder, commissaris of aandeelhouder wordt mede verstaan hij die minder dan een jaar vóór de rechtshandeling bestuurder, commissaris of aandeelhouder is geweest.

#### Lid 5

Indien de bestuurder van een rechtspersoon-bestuurder zelf een rechtspersoon is, wordt deze rechtspersoon met de rechtspersoon-bestuurder gelijkgesteld.

#### Lid 6

Artikel 138, tiende lid, van boek 2 van het Burgerlijk Wetboek is van toepassing ingeval de schuldenaar een rechtspersoon is.

## Artikel 45 Faillissementswet

In geval van benadeling door een rechtshandeling om niet, die de schuldenaar heeft verricht binnen één jaar vóór de faillietverklaring, wordt vermoed dat hij wist of behoorde te weten dat benadeling van de schuldeisers het gevolg van de rechtshandeling zou zijn.


Wetenschap van benadeling
Wetenschap van benadeling betekent dat de schuldenaar, en bij een rechtshandeling anders dan om niet ook de wederpartij, wist of behoorde te weten (geobjectiveerd) dat benadeling van de schuldeisers het gevolg zou zijn. Daarvan is sprake indien ten tijde van de rechtshandeling het faillissement en een tekort daarin met een redelijke mate van waarschijnlijkheid waren te voorzien. Een oogmerk om te benadelen is niet vereist; wetenschap van enkel een kans op benadeling is onvoldoende. De stelplicht en bewijslast rusten op de curator.

Bewijsvermoedens en tegenbewijs
Art. 43 en 45 Fw verlichten de bewijslast van de curator. Is aan de voorwaarden van art. 43 voldaan (binnen een jaar, niet reeds verplicht, en een van de drie categorieën), dan wordt de wetenschap aan beide zijden vermoed; bij art. 45 (rechtshandeling om niet binnen een jaar) wordt de wetenschap aan de zijde van de schuldenaar vermoed (toepassing art. 45 Fw wordt reeds automatisch gesteld, overweeg hier daarom met name tegenbewijs van art. 45 Fw en de directe bewijsplicht van art. 42 Fw). De vermoedens zijn weerlegbaar: levert de aangesproken partij met succes tegenbewijs (maakt zij aannemelijk dat het faillissement en een tekort daarin niet met een redelijke mate van waarschijnlijkheid waren te voorzien), dan vervalt het vermoeden aan die zijde en valt de wetenschap terug op de hoofdregel van art. 42, waarbij de curator de wetenschap alsnog rechtstreeks moet aantonen.

Werkwijze — welke velden vul je in:
- wetenschap_schuldenaar_aangetoond / wetenschap_wederpartij_aangetoond: true wanneer de wetenschap rechtstreeks (los van een vermoeden) is aangetoond; de wederpartij is vereist bij een rechtshandeling anders dan om niet.
- tegen_onderwaarde, voldoening_of_zekerheid_niet_opeisbare_schuld, gelieerde_partij: drie categorieën van bewijsvermoeden art. 43 Fw, zet (een van) de gronden van art. 43 op true als deze van toepassing is.
- reeds_verplicht_voor_aanvang_termijn: true als de schuldenaar zich al vóór de jaartermijn tot de rechtshandeling had verplicht (dat sluit het vermoeden van art. 43 uit).
- vermoeden_wetenschap_schuldenaar_tegenbewijs / vermoeden_wetenschap_wederpartij_tegenbewijs: true wanneer een toegepast vermoeden aan die zijde met succes is ontzenuwd (het tegenbewijs slaagt).
- Laat een veld dat niet aan de orde is op null staan. De termijn- en om-niet-toets (op basis van de datums) wordt elders bepaald; die hoef je hier niet te berekenen.

Vul eerst "wetenschap_overwegingen" met een korte motivering op basis van de casus en de eventueel aangereikte uitspraken, en bepaal daarna pas de waarden. Antwoord uitsluitend in het gevraagde JSON-formaat."""


async def run(
    casus: str,
    *,
    model: str = nsm.DEFAULT_MODEL,
    k: int = nsm.DEFAULT_K,
    query_vec: list[float] | None = None,
) -> WetenschapOutput:
    """Resolve knowledge (wetenschap) inputs for the facts of one input case
    using case-based reasoning (RAG over judgments).
    `query_vec` is the shared case embedding."""
    rag_markdown = await nsm.subroutine_rag(
        casus, query_vec, label=RAG_LABEL, k=k
    )
    user_prompt = nsm.subroutine_prompt(casus, rag_markdown)
    return await nsm.complete(
        model, SYSTEM_PROMPT, user_prompt, WetenschapOutput
    )
