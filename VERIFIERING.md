# Verifiering av Streamlit-utgåvan

Datum: 26 oktober 2026. Modell: **10.4**. Apputgåva: **10.4-streamlit.1**.

## Genomfört och godkänt

Tio automatiska regressionstester har körts med Python 3.12.14 och Node.js
24.22.1. De verifierar följande:

1. Oförändrade originalfiler genom SHA-256-kontrollsummor.
2. Identisk JavaScript-kod i Pythonfilen och HTML-modellens tre motormoduler.
3. Samtliga 84 indatanycklar och identiska standardvärden.
4. Exakt överensstämmelse för alla resultatfält och årsserier i 16 scenarier,
   där HTML-motorn körts separat och jämförts med Streamlit-adapterns resultat.
5. Standardscenariots netto: 1 158,4161511633881 tCO₂/ha efter 200 år och
   beräknad bonitet 6,9 m³sk/ha,år.
6. Sambandet mellan brutto, referens och netto samt arealskalning och
   omräkning mellan ton kol och ton CO₂.
7. Export och återinläsning av scenario-JSON, inklusive svenska tecken.
8. Avvisning av trasig JSON, ogiltiga kategorier, fel datatyper, negativa
   arealer och icke ändliga numeriska värden.
9. Samtliga 40 referensutfalls modellvärden, känslighetsspann och status
   överensstämmer med den tidigare levererade 10.4-baslinjen.
10. Sex skötselmetoder i jämförelsefunktionen ger samma årsserier som när
    metoderna beräknas en och en.

De 16 scenarierna omfattar alla sex trädslagsval, nybeskogning, befintligt
bestånd, skogslandskap, alla sex skötselval, tre systemgränser, organisk jord,
hårdgjord mark, direkta GIS-förändringar, separat stomvirke, avstängt markkol,
varierad areal och analysperioder på 50–300 år.

Att referensbaslinjen överensstämmer betyder att samma tidigare
modellresultat har bevarats. Vissa referensutfall visar redan i originalet
avvikelse mot studierna. Sådana avvikelser finns kvar i denna utgåva.

Pythonflödet för samtliga fem appvyer och sex villkorade indatalayouter har
också körts med en förenklad ersättning för Streamlits gränssnitt. En
indataåterkoppling har kontrollerats så att G24 blir bonitet 6,9 när
indatametoden byts. Detta är en kontroll av Pythonflödet och ersätter inte
körning i Streamlit eller visuell kontroll i en webbläsare.

## Återstående kontroll

Den aktuella arbetsmiljön har inte Streamlit installerat och tillåter inte
hämtning av paketet från Python Package Index. Fyra medföljande
integrationstester för Streamlit kunde därför inte köras här. Ingen
molnpublicering på användarens konton har genomförts.

Integrationstesterna finns i `tests/test_model.py`. De provar initiala
resultat och arealändring, ändring av projekttyp och skötsel, körning av
referenskontroller samt öppning av originalmodellen och hjälpsidan.

Om hela paketet inklusive `.github/workflows/kontroll.yml` laddas upp,
installerar GitHub Actions beroendena och kör även dessa tester. Se fliken
**Actions** i GitHub. Gör därefter den praktiska kontrollen i avsnitt 6 i
publiceringsguiden.

## Köra kontrollerna

Från projektets rot:

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Med alla beroenden installerade ska inga tester vara markerade som
`skipped`. En godkänd programkontroll innebär att de definierade
regressionerna och gränssnittsflödena fungerar. Den innebär inte en ny
vetenskaplig validering eller certifiering av modellens antaganden.
