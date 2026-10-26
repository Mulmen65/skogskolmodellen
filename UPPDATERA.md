# Rätta den redan publicerade appen – utgåva 2

26 oktober 2026. Modell 10.4, apputgåva 10.4-streamlit.2.

Det tidigare paketet kunde krascha vid första diagrammet med `StepKwds`,
`TypedDict` och `closed=True` i felmeddelandet. Orsaken var kombinationen
Streamlit 1.50, Altair 5 och Python 3.14. Originalets skogsberäkningar har
inte ändrats i denna rättning.

## Uppdatera samma GitHub-projekt

1. Packa upp `Skogskolmodellen_Streamlit_fix_2.zip` på datorn.
2. Öppna ditt befintliga GitHub-projekt **skogskolmodellen**.
3. Kontrollera att samma gren är vald som Streamlit använder, normalt **main**.
4. Välj **Add file → Upload files**.
5. Dra in de tre filerna `requirements.txt`, `streamlit_app.py` och
   `model_adapter.py` från det uppackade paketet. De ska ersätta filerna
   med samma namn direkt i projektets rot. `UPPDATERA.md` kan också följa med.
6. Skriv exempelvis `Rätta diagram och mörkt tema – Streamlit-utgåva 2`
   och klicka på **Commit changes**.
7. Öppna Streamlit-appen. Streamlit hämtar ändringarna och installerar de
   nya paketversionerna. Låt installationen bli färdig.
8. Om den gamla felbilden ligger kvar, välj **Manage app → Reboot app**
   och ladda därefter om sidan i webbläsaren.

Du kan behålla både ditt befintliga GitHub-projekt och appens webbadress.
Paketuppdateringen kräver inget byte av Pythonversion. Python 3.12 och
3.14 ingår i det medföljande testflödet i det kompletta paketet.

## Snabb åtgärd direkt i GitHub

Om du vill rätta enbart det rapporterade diagramfelet genom webbredigeraren:
öppna `requirements.txt` i GitHub, klicka på pennsymbolen, ersätt hela
innehållet med följande och spara med **Commit changes**:

```text
streamlit==1.66.1
altair==6.3.0
typing_extensions==4.15.0
pandas==2.3.3
nodejs-wheel==24.19.0
```

Det ändrar paketkombinationen. Uppdatera även de två Pythonfilerna enligt
huvudförfarandet ovan för att få versionsmarkeringen utgåva 2 och rättningen
av färgerna i sidomenyn. Sidomenyn och resultatvärdena följer då Streamlits
ljusa eller mörka tema.

## Kontrollera att rättningen är installerad

Efter uppladdning av alla tre filer ska appens underrubrik visa
**Streamlit-utgåva 2**. Under **Beräkna** ska både de kumulativa och de
årliga diagrammen visas. Öppna även fliken **Kollager**.

Återställ standardscenariot. Netto efter 200 år ska vara cirka
**1 158 tCO₂/ha**. Byt till **Jämför skötselmetoder** och kör jämförelsen.
Kontrollera att sidomenyn är läsbar i det tema du använder.

Om ett fel kvarstår: öppna loggen under **Manage app** och kontrollera
att installationen använder `streamlit 1.66.1` och `altair 6.3.0`.
Om loggen fortfarande visar Altair-moduler under `vegalite/v5` har den
gamla installationen inte ersatts. Kontrollera att rätt `requirements.txt`
ligger på rätt gren och i projektets rot.

## Vad som är kontrollerat

Den rapporterade stacktracen överensstämmer med Altairs dokumenterade fel
på Python 3.14. De valda nya versionerna anger stöd för Python 3.14.
Beräkningsmotorn och originalets webbfil är oförändrade. Medföljande
kontroller jämför även modellresultaten med tidigare leverans.

Arbetsmiljön där denna rättning tas fram blockerar installation av
Streamlit. Lokal körning i den riktiga Streamlit-miljön har därför inte
kunnat genomföras. Det kompletta paketets GitHub Actions testar både
diagramimport och appflöden under Python 3.12 och 3.14 när filerna
har laddats upp.

## Dokumentation

- Altair: [känt fel med identisk stacktrace](https://github.com/vega/altair/issues/3874).
- Altair: [version 6.0.0 introducerade Python 3.14-stöd](https://github.com/vega/altair/releases/tag/v6.0.0).
- [Streamlit 1.66.1](https://pypi.org/project/streamlit/1.66.1/) och [Altair 6.3.0](https://pypi.org/project/altair/6.3.0/).
- Streamlit: [uppdatera en befintlig app genom GitHub](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/edit-your-app).
- Streamlit: [byte av själva Pythonversionen kräver ompublicering](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/upgrade-python). Det behövs inte för huvudförfarandet ovan.
