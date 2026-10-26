# Skogskolmodellen 10.4 – GitHub och Streamlit

Svensk app för att jämföra skogsskötsel, referensscenarier, kollager,
träprodukter och antagen substitution. Utgåvan bygger på den levererade
Skogskolmodellen 10.4 från oktober 2026.

**Börja med [PUBLICERING.md](PUBLICERING.md).** Den beskriver alla moment i
webbläsaren. Samma guide finns som `PUBLICERING.html`, som kan öppnas genom
att dubbelklicka på filen efter uppackning.

## Publiceringsinställningar

| Inställning i Streamlit Community Cloud | Värde |
|---|---|
| Repository | `DITT_GITHUBNAMN/skogskolmodellen` |
| Branch | `main` |
| Main file path | `streamlit_app.py` |
| Python version, under Advanced settings | `3.12` |
| App URL, om namnet är ledigt | `skogsnytta` |
| Secrets | Lämnas tomt |

`skogsnytta` är ett förslag; ingen adress har registrerats genom detta paket.

## Funktioner

- Nybeskogning, befintligt bestånd och skogslandskap.
- Samtliga 84 modellindata finns i Streamlit-gränssnittet; relevanta fält visas efter dina val.
- Tall, gran, barrblandning, gran/bok, bok och ek; H100 eller bonitet.
- Sex skötselalternativ inklusive landskapsmix.
- SOC 0–50 cm, DOM, träprodukter, substitution och särredovisat stomvirke.
- Kumulativa och årliga resultat i ton CO₂ eller ton kol samt jämförelser mellan metoder.
- Import av befintliga JSON-scenarier samt export av scenario, årsdata och fullständigt resultat.
- Källornas roll i valt scenario, känslighetsanalys och 40 fasta referensutfall.
- Den kompletta ursprungliga webbmodellen i en separat vy.

## Vad som har ändrats

Streamlit-gränssnitt, indatahantering, exportknappar och publiceringsfiler är
nya. Modellversionen är fortfarande **10.4** och apputgåvan betecknas
**10.4-streamlit.1**.

`Skogskolmodellen_v10_4.py` och `webbmodell.html` är oförändrade kopior av
de tidigare levererade källfilerna. Pythonfilen anropar samma inbäddade
JavaScript-motor som webbmodellen. Detta är en Streamlit-anpassning av
modellen. Ingen självständig omskrivning av formlerna till Python ingår.

`nodejs-wheel` installerar Node.js tillsammans med Pythonberoendena. Därför
behövs ingen separat Node-installation för publicering på Community Cloud
och ingen `packages.txt`. Paketet innehåller inga API-nycklar och kräver
ingen anslutning till en extern databas.

## Filer

| Fil | Funktion |
|---|---|
| `streamlit_app.py` | Appens startfil och gränssnitt |
| `model_adapter.py` | Indata, export och anrop till originalmodellen |
| `Skogskolmodellen_v10_4.py` | Oförändrad originalmotor med Pythonanrop |
| `input_schema.json` | Fältnamn, enheter, gränser och val för alla modellindata |
| `standardscenario.json` | Originalets förvalda scenario |
| `webbmodell.html` | Komplett oförändrad webbmodell 10.4 |
| `requirements.txt` | Versioner av Streamlit, pandas och Node-paketet |
| `original_hashes.json` | Kontrollsummor för originalfilerna |
| `tests/` | Regressionstester och tidigare levererade referensutfall |
| `.github/workflows/kontroll.yml` | Automatisk kontroll vid ändringar i GitHub |
| `VERIFIERING.md` | Genomförda kontroller och återstående gränssnittskontroll |

## Lokal start, frivilligt

För publicering med webbläsaren behövs inga lokala installationer. För den
som vill köra appen på sin dator med Python 3.12:

```bash
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

Verifiera paketet med:

```bash
python -m unittest discover -s tests -v
```

## Tolkning och jämförbarhet

Positivt netto betyder större beräknad klimatnytta än referensen inom vald
systemgräns. Netto bygger på skillnaden mellan förändringarna i projektet
och referensen. Substitution behandlas enligt originalets valda systemgräns.

De 40 referenskontrollerna är 40 utfall, ofta flera från samma studie.
Känslighetsspannen bygger på fem valda körningar och är inte statistiska
konfidensintervall. Källförteckningen beskriver antagandenas roller; modellen
beräknar inga statistiska studievikter för användarens scenario.

Denna leverans omfattar anpassning till GitHub/Streamlit och verifiering mot
originalet. Någon ny vetenskaplig granskning eller uppdatering av referenserna
i modell 10.4 har inte genomförts.
