# Publicera Skogskolmodellen med GitHub och Streamlit

Guide för Skogskolmodellen **10.4-streamlit.1**, framtagen 26 oktober 2026.

Du laddar upp modellfilerna till GitHub och låter Streamlit Community Cloud
köra appen. När publiceringen är klar får modellen en webbadress som du kan
dela med andra. Hela grundförfarandet kan göras i en vanlig webbläsare.

## 1. Packa upp paketet på datorn

1. Ladda ned `Skogskolmodellen_v10_4_GitHub_Streamlit.zip`.
2. I Windows: högerklicka på ZIP-filen och välj **Extrahera alla**.
3. Öppna den uppackade mappen. Fortsätt till den nivå där du ser filen
   **streamlit_app.py**.
4. Kontrollera att samma mapp också innehåller `requirements.txt`,
   `model_adapter.py`, `Skogskolmodellen_v10_4.py`, `input_schema.json`,
   `standardscenario.json` och `webbmodell.html`.

Det är **innehållet i den uppackade mappen** som ska laddas upp till GitHub.
Laddar du enbart upp ZIP-filen kan Streamlit inte hitta appens startfil.
Paketet är litet och behöver inte delas i mindre ZIP-filer.

## 2. Skapa ett nytt repository på GitHub

Ett repository är GitHubs projektmapp för kod och dess versionshistorik.

1. Gå till [github.com](https://github.com/) och logga in.
2. Klicka på **+** uppe till höger och välj **New repository**. Du kan också
   öppna [github.com/new](https://github.com/new).
3. Välj ditt konto under **Owner**.
4. Skriv **skogskolmodellen** som **Repository name**. Om det namnet redan
   används på ditt konto kan du exempelvis skriva `skogskolmodellen-streamlit`.
5. En lämplig beskrivning är: `Skogskolmodellen 10.4 – scenarier för skog och klimat`.
6. Välj **Public** för den enklaste publiceringsvägen. Då blir också
   modellens källkod offentligt läsbar. Om du vill begränsa insynen i koden
   väljer du **Private** och följer även avsnitt 8.
7. Låt GitHub lämna README, gitignore och licens tomma här. Paketet har redan
   en README och en gitignore.
8. Klicka på **Create repository**.

Detta följer GitHubs dokumentation om att skapa nya projekt [1].

## 3. Ladda upp filerna

1. I det nya, tomma projektet: klicka på länken **uploading an existing file**.
   Om det redan finns filer väljer du **Add file → Upload files**.
2. Öppna den uppackade mappen i Utforskaren.
3. Markera **filerna och undermapparna inne i mappen** och dra dem till
   GitHubs uppladdningsruta. Dra inte med den yttre mappen.
4. Vänta tills listan med uppladdade filer är färdig.
5. Skriv exempelvis `Lägg till Skogskolmodellen 10.4 för Streamlit` som
   commit-meddelande. En commit är en sparad version i GitHub.
6. Klicka på **Commit changes**, eller motsvarande knapp för att spara.

Kontrollera sedan projektets startsida. Filerna nedan ska ligga direkt där,
utan att du först behöver öppna ytterligare en mapp:

| Ska synas i projektets rot | Varför den behövs |
|---|---|
| `streamlit_app.py` | Startar appen |
| `requirements.txt` | Installerar programbiblioteken |
| `model_adapter.py` | Kopplar gränssnittet till modellen |
| `Skogskolmodellen_v10_4.py` | Utför modellberäkningarna |
| `input_schema.json` | Beskriver indatafälten |
| `standardscenario.json` | Ger modellens standardindata |
| `webbmodell.html` | Visar den kompletta tidigare webbmodellen |
| `PUBLICERING.md` | Ger den inbyggda hjälpsidan |

GitHubs dokumentation beskriver uppladdningsförfarandet [2]. Alla filer i
detta paket ligger långt under GitHubs gräns på 25 MiB per fil för uppladdning
via webbläsare.

Mapparna `tests` och `.github` bör också följa med. De behövs för automatiska
kontroller. Appen kan starta även om dessa två mappar saknas. GitHub kan
be om särskild behörighet för att lägga till en workflow-fil. Om det händer
kan du först publicera appen utan `.github` och därefter lägga till
kontrollflödet genom GitHubs gränssnitt. Ingen sådan behörighet behövs för
modellens vanliga filer.

## 4. Koppla Streamlit till GitHub

1. Öppna [share.streamlit.io](https://share.streamlit.io/).
2. Skapa ett Community Cloud-konto eller logga in på ditt befintliga konto.
3. Koppla samma GitHub-konto som äger modellprojektet. Vid en ny koppling
   visas normalt **Connect GitHub account** och därefter **Authorize streamlit**.
4. Kontrollera att rätt GitHub-användare eller organisation är vald i
   Streamlits arbetsyta.

För ett projekt under en organisation, exempelvis ett institut, kan den som
administrerar organisationen behöva godkänna kopplingen. Den som publicerar
appen behöver administratörsbehörighet till GitHub-projektet [3].

## 5. Publicera appen

1. Klicka på **Create app** i Streamlit.
2. Om frågan om en befintlig app visas, välj **Yup, I have an app**.
3. Välj projektet, grenen och startfilen enligt tabellen nedan.
4. Klicka på **Advanced settings** och välj **Python 3.12**. Lämna fältet
   **Secrets** tomt. Klicka på **Save**.
5. Välj om du vill ange ett eget appnamn under **App URL**.
6. Klicka på **Deploy** och låt installationen bli klar [4].

| Fält i Streamlit | Vad du ska ange |
|---|---|
| Repository | `DITT_GITHUBNAMN/skogskolmodellen` |
| Branch | `main` |
| Main file path | `streamlit_app.py` |
| Python version | `3.12` |
| App URL, frivilligt | exempelvis `skogsnytta`, om det är ledigt |
| Secrets | Lämnas tomt |

**DITT_GITHUBNAMN är en platshållare.** Ersätt det med det användarnamn du
ser på GitHub. Om du valde ett annat projektnamn använder du det namnet i
stället för `skogskolmodellen`. Välj den gren som faktiskt syns i GitHub om
den heter något annat än `main`.

Du kan även klistra in länken till `streamlit_app.py` från GitHub om
Streamlit inte hittar projektet i sin lista.

Om du får använda namnet `skogsnytta` blir adressen
`https://skogsnytta.streamlit.app/`. Detta är ett **exempel på önskad adress**;
namnet har inte reserverats i denna leverans. Streamlit kan annars skapa en
annan adress automatiskt.

Första installationen kan ta några minuter. `requirements.txt` installerar
Streamlit, pandas och Node.js-paketet. Du behöver inte själv lägga till
`packages.txt` eller installera Node.js på din dator för denna publicering.

## 6. Kontrollera modellen efter start

Öppna appen och välj **Beräkna** i vänstermenyn. Kontrollera att den visar
modellversion **10.4**. Klicka sedan på **Återställ standardvärden** under
**Öppna eller återställ scenario**.

| Kontrollvärde för standardscenariot | Förväntat värde |
|---|---|
| Projekttyp | Nybeskogning |
| Trädslag och H100 | Gran, 24 m |
| Skötsel | Fri utveckling utan avverkning |
| Mark och referens | Åkermark; fortsatt nuvarande markanvändning |
| Areal och period | 1 ha; 200 år |
| Systemgräns | Ekosystem |
| Beräknad bonitet | 6,9 m³sk/ha,år |
| Projektets förändring efter 200 år | cirka 1 121,75 tCO₂/ha |
| Referensens förändring efter 200 år | cirka −36,67 tCO₂/ha |
| Netto efter 200 år | cirka 1 158,42 tCO₂/ha |

Resultatkorten avrundar till heltal. Netto bör alltså visas som **1 158**.
De oavrundade resultaten finns i CSV- och JSON-exporterna.

Gör därefter dessa praktiska kontroller:

1. Ändra arealen till **2 ha**. Netto per hektar ska vara oförändrat och
   totalt netto ska bli cirka **2 316,83 tCO₂**, avrundat **2 317**.
2. Välj **Jämför skötselmetoder** och klicka på **Beräkna jämförelsen**.
3. Välj **Referenskontroller** och klicka på **Kör referenskontroller**.
   Kontrollera att 40 utfall redovisas. En beräknad kontroll kan visa en
   avvikelse mot en studie; det är en del av modellens redovisning.
4. Välj **Original webbmodell**. Kontrollera att det tidigare gränssnittet
   laddas och att du kan ändra ett scenario där.
5. Hämta ett scenario som JSON och läs tillbaka det i Streamlit-vyn.

Den kompletta verifieringsredovisningen finns i `VERIFIERING.md`.

## 7. Dela webbadressen

För att alla med länken ska kunna öppna modellen behöver Streamlit-appen
vara offentlig. Öppna appens **Settings → Sharing** och kontrollera inställningen
under **Who can view this app**. Offentlig åtkomst anges som **This app is
public and searchable**. Du kan sedan kopiera adressen via **Share → Copy link** [5].

Prova länken i ett privat webbläsarfönster där du inte är inloggad på GitHub
eller Streamlit. Om modellen går att använda där är åtkomsten kontrollerad.
Offentlig betyder att fler än den avsedda mottagargruppen kan hitta appen.

Du har därefter två separata publiceringar om den tidigare Netlify-adressen
också finns kvar: en på Netlify och en på Streamlit. Ändringar i detta
GitHub-projekt förs automatiskt vidare till den kopplade Streamlit-appen.
En Netlify-publicering uppdateras när den har en motsvarande koppling till
sina egna publiceringsfiler.

## 8. Om du vill ha privat kod och offentlig app

Du kan använda ett privat GitHub-projekt och ändå göra själva Streamlit-appen
offentlig. Då behöver Streamlit få åtkomst till det privata projektet under
**Settings → Linked accounts → Source control**. Följ kopplingsstegen där [3].

Appen blir normalt privat från början om källprojektet är privat. Ändra sedan
appens delning enligt avsnitt 7 [5]. Besökare kan använda modellen utan att
GitHub-projektet blir offentligt. Modellen har samtidigt en nedladdningsbar
webbversion, vars beräkningskod levereras till besökarens webbläsare.

## 9. Uppdatera modellen senare

Streamlit följer den gren som valdes vid publiceringen [6].

1. Öppna ditt GitHub-projekt och kontrollera att grenen **main** är vald.
2. För en liten textändring: öppna filen, klicka på pennsymbolen, ändra och
   spara med **Commit changes**.
3. För en ny modellleverans: packa upp det nya paketet och välj
   **Add file → Upload files**. Ladda upp de uppdaterade filerna på samma
   platser som tidigare.
4. Spara med ett tydligt commit-meddelande, exempelvis
   `Uppdatera app och modell till nästa verifierade version`.
5. Öppna Streamlit-appen och kontrollera versionen och ett känt scenario.

Streamlit hämtar sparade ändringar automatiskt. Beroendeändringar kan ta
längre tid än rena text- och kodändringar. Om appen fastnar, använd
**Reboot app** i apphanteringen och läs loggen.

Om du arbetar i VS Code är motsvarigheten att spara, göra en commit och
sedan **Push/Sync Changes** till GitHub. En lokal sparning i VS Code räcker
inte för att uppdatera den publicerade appen.

Motorfilen, webbfilsversionen, indataschemat och standardscenariot ska hållas
samstämmiga vid framtida modelluppdateringar. Filen `original_hashes.json`
och referensbaslinjen ska bara bytas efter en avsiktlig, verifierad ny
modellversion. Enbart ändringar i Streamlit-gränssnittet kräver ingen ny
vetenskaplig modellversion.

## 10. Vanliga problem

| Vad du ser | Vad du gör |
|---|---|
| `streamlit_app.py` hittas inte | Kontrollera att filen ligger direkt i GitHub-projektets rot och att Main file path är exakt `streamlit_app.py`. |
| Bara en ZIP-fil syns i GitHub | Packa upp ZIP-filen lokalt och ladda upp innehållet. |
| Projektet saknas i Streamlit | Kontrollera valt GitHub-konto, kopplingens behörighet och eventuell organisationsåtkomst. Klistra vid behov in länken till startfilen. |
| `ModuleNotFoundError` | Kontrollera att `requirements.txt` finns i roten och att alla paket kunde installeras. Läs installationsloggen. |
| Node.js saknas eller har fel version | Kontrollera att raden `nodejs-wheel==24.19.0` finns i `requirements.txt`. Starta om appen efter att installationen är klar. |
| Appen startar men visar inga resultat | Öppna loggen i apphanteringen. Prova även vyn Original webbmodell för att skilja motorstart från webbgränssnitt. |
| Resultaten skiljer sig mellan två vyer | Spara scenariot i den ena vyn och läs in samma JSON i den andra. Kontrollera särskilt referens, systemgräns, ålder, H100/bonitet och markkol. Vyernas indata ändras separat. |
| Alla fem känslighetsutfall är lika | Variationerna gäller främst kontinuitetsskogsbruk. Om det saknas i scenariot kan utfallet bli lika. |
| Ändringen syns inte efter uppladdning | Kontrollera att du sparat en commit på rätt gren och vänta tills Streamlit har hämtat ändringen. Ladda om sidan. |
| Ett sparat scenario är borta efter omstart | Appen har ingen projektdatabas. Hämta scenario-JSON till din dator och läs tillbaka filen. |

## 11. Förvaltning och tekniska detaljer

Den nya Streamlit-vyn kör beräkningarna på servern genom originalets
Pythonanrop till JavaScript-motorn. Vyn Original webbmodell kör sin
beräkning i besökarens webbläsare. Samma antaganden och modellmotor används.

JSON-filer kan flyttas mellan vyerna. De två gränssnitten delar inte ett
automatiskt synkroniserat scenario. CSV-filerna är semikolonseparerade och
UTF-8-kodade med BOM, vilket underlättar öppning i svensk Excel. Om Excel
inte delar upp kolumnerna, välj **Data → Från text/CSV**, avgränsare
**semikolon** och UTF-8.

Känslighetsanalys och källredovisning har samma vetenskapliga begränsningar
som version 10.4. Denna leverans innehåller ingen ny kalibrering eller
granskning av skogsreferenserna.

Den automatiska kontrollen i GitHub visas under fliken **Actions** när
`.github/workflows/kontroll.yml` finns på plats. Grönt resultat betyder
att de definierade kontrollerna passerat. Dessa kontroller jämför även
Streamlit-vyns funktion med beräkningsresultaten. De ersätter inte en
vetenskaplig validering av modellens antaganden.

## Källor för publiceringsförfarandet

Kontrollerade 26 oktober 2026. Knapptexter kan ändras när tjänsterna uppdateras.

1. GitHub Docs. [Creating a new repository](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository).
2. GitHub Docs. [Adding a file to a repository](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository).
3. Streamlit Docs. [Connect your GitHub account](https://docs.streamlit.io/deploy/streamlit-community-cloud/get-started/connect-your-github-account).
4. Streamlit Docs. [Deploy your app on Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy).
5. Streamlit Docs. [Share your app](https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app).
6. Streamlit Docs. [Edit your app](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/edit-your-app).
7. Streamlit Docs. [App dependencies](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies).
8. Node.js wheel project. [nodejs-wheel](https://pypi.org/project/nodejs-wheel/).
