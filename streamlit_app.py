"""Skogskolmodellen 10.4 — starta med streamlit run streamlit_app.py."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import model_adapter as model

st.set_page_config(page_title="Skogskolmodellen 10.4", page_icon="🌲", layout="wide")
st.markdown("""<style>
    .block-container {padding-top:2rem; max-width:1500px;}
    [data-testid="stMetricValue"] {color:#205447;}
    [data-testid="stSidebar"] {background:#f3f7f4;}
    h1,h2,h3 {color:#173f35;}
    </style>""", unsafe_allow_html=True)


def capture(key: str) -> None:
    field = model.FIELDS[key]
    value = st.session_state["field_" + key]
    if field["percent"]:
        value = value / 100
    old = st.session_state.draft.get(key)
    # När H100 byts till bonitet används beräknad bonitet för de gamla indata.
    # Då blir exempelvis G24 -> 6,9, inte 24 m³sk/ha,år.
    if key in ("projectProductivityMethod", "referenceProductivityMethod") and old != value:
        prefix = "project" if key.startswith("project") else "reference"
        if value == "bonitet":
            try:
                before = model.simulate(st.session_state.draft)
                amount = before["summary"][prefix + "Bonitet"]
                st.session_state.draft[prefix + "ProductivityValue"] = amount
                st.session_state["field_" + prefix + "ProductivityValue"] = float(amount)
            except RuntimeError:
                pass
        elif old == "bonitet":
            # H100 måste kontrolleras av användaren; byt tillbaka till modellens G24-förval.
            st.session_state.draft[prefix + "ProductivityValue"] = 24.0
            st.session_state["field_" + prefix + "ProductivityValue"] = 24.0
            st.session_state.notice = "H100 återställdes till 24. Kontrollera ståndortsindexet för ditt trädslag."
    st.session_state.draft[key] = value


def set_draft(inputs: dict) -> None:
    st.session_state.draft = dict(inputs)
    # Fristående draft bevarar även parametrar vars fält tillfälligt är dolda.
    for key in model.FIELDS:
        st.session_state.pop("field_" + key, None)


@st.cache_data(show_spinner=False, max_entries=64, ttl=600)
def calculate(serialized: str, engine_hash: str) -> dict:
    return model.simulate(json.loads(serialized))


@st.cache_data(show_spinner=False, max_entries=16, ttl=600)
def compare(serialized: str, engine_hash: str) -> list:
    return model.compare(json.loads(serialized))


@st.cache_data(show_spinner=False, max_entries=16, ttl=600)
def sensitivity(serialized: str, engine_hash: str) -> dict:
    return model.sensitivity(json.loads(serialized))


@st.cache_data(show_spinner=False, max_entries=1)
def checks(engine_hash: str) -> list:
    return model.reference_checks()


def number(value: float, decimals: int = 0) -> str:
    return f"{value:,.{decimals}f}".replace(",", " ").replace(".", ",")


def render_field(field: dict, inputs: dict) -> None:
    key = field["key"]
    if not model.visible(key, inputs):
        return
    label = model.display_label(field, inputs)
    args = dict(key="field_" + key, help=field["help"] or None,
                on_change=capture, args=(key,))
    value = inputs[key]
    if field["type"] == "select":
        options = [o["value"] for o in field["options"]
                   if key != "restorationScenario" or o["value"] != "notApplicable"]
        labels = {o["value"]: o["label"] for o in field["options"]}
        disabled = key == "referenceSoilMethod" and inputs["referenceScenario"] != "continuedLandUse"
        st.selectbox(label, options, index=options.index(value), format_func=labels.get,
                     disabled=disabled, **args)
    elif field["type"] == "checkbox":
        st.checkbox(label, value=bool(value), **args)
    elif field["type"] == "number":
        factor = 100 if field["percent"] else 1
        integer = field["integer"]
        cast = int if integer else float
        opts = {name + "_value": cast(field[name]) for name in ("min", "max") if name in field}
        opts["step"] = cast(field.get("step", 1))
        disabled = (key == "referenceSoilMethod" and inputs["referenceScenario"] != "continuedLandUse")
        if key == "initialDom":
            disabled = (inputs["projectType"] == "landscape" or
                        inputs["projectType"] == "existing" and inputs["currentLandUse"] == "forest"
                        and inputs["domEquilibrium"])
        st.number_input(label, value=cast(value * factor), disabled=disabled, **opts, **args)
    else:
        st.text_input(label, value=str(value), max_chars=120, **args)


def input_panel() -> dict:
    with st.sidebar:
        with st.expander("Öppna eller återställ scenario"):
            uploaded = st.file_uploader("Scenario från webbmodellen eller Streamlit", type=["json"])
            if st.button("Läs in scenario", disabled=uploaded is None):
                try:
                    set_draft(model.read_scenario(uploaded.getvalue()))
                    st.success("Scenariot är inläst.")
                except ValueError as exc:
                    st.error(str(exc))
            if st.button("Återställ standardvärden"):
                set_draft(model.DEFAULTS)
        inputs = model.validate_inputs(st.session_state.draft)
        if inputs["restorationScenario"] != st.session_state.draft["restorationScenario"]:
            st.session_state.pop("field_restorationScenario", None)
        st.session_state.draft = inputs
        for group, title in model.SCHEMA["groups"].items():
            with st.expander(f"{group}. {title}", expanded=group == "1"):
                for field in model.SCHEMA["fields"]:
                    if str(field["group"]) == group:
                        render_field(field, inputs)
                if group == "1":
                    if inputs["projectForestScenario"] == "mix":
                        total = sum(inputs[k] for k in inputs if k.startswith("mix"))
                        st.caption(f"Summa skötselandelar: {number(total * 100, 1)} %. Motorn normaliserar andelarna.")
                    if inputs["projectType"] == "landscape":
                        total = sum(inputs[k] for k in inputs if k.startswith("ageShare"))
                        st.caption(f"Summa åldersandelar: {number(total * 100, 1)} %. Motorn normaliserar andelarna.")
                if group == "2":
                    st.caption("GIS-estimat innebär att du anger ett redan framtaget H100-värde. Appen hämtar inga GIS-data automatiskt.")
        return model.validate_inputs(dict(inputs))


def export_buttons(result: dict) -> None:
    a, b, c = st.columns(3)
    a.download_button("Spara scenario (JSON)", model.scenario_bytes(result["inputs"]),
                      "skogsscenario_10_4.json", "application/json")
    b.download_button("Hämta årsresultat (CSV)", model.csv_bytes(result["rows"]),
                      "skogskol_arsresultat.csv", "text/csv")
    c.download_button("Hämta fullständigt resultat (JSON)",
                      json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"),
                      "skogskol_resultat.json", "application/json")


def results_view(inputs: dict, serialized: str) -> None:
    with st.spinner("Beräknar scenario …"):
        result = calculate(serialized, model.ENGINE_HASH)
    summary = result["summary"]
    for warning in result["warnings"]:
        st.warning(warning)
    st.subheader(result["inputs"]["projectName"])
    st.caption(f"{summary['projectSpeciesLabel']} · {summary['projectScenarioLabel']} · "
               f"Bonitet {number(summary['projectBonitet'], 1)} m³sk/ha,år · "
               f"{inputs['analysisYears']} år · {summary['systemBoundaryLabel']}")
    cols = st.columns(4)
    for col, label, value in zip(cols,
        ["Projektets förändring (tCO₂/ha)", "Referensens förändring (tCO₂/ha)",
         "Nettoeffekt (tCO₂/ha)", "Totalt netto (tCO₂)"],
        [summary["grossCumulativeCo2PerHa"], summary["referenceCumulativeCo2PerHa"],
         summary["netCumulativeCo2PerHa"], summary["netTotalCo2"]]):
        col.metric(label, number(value))
    st.caption("Netto = projektets förändring − referensens förändring. Positivt netto innebär "
               "större beräknad klimatnytta än referensen inom vald systemgräns. "
               "Substitution är en beräknad undviken påverkan och redovisas inom den systemgräns där den valts.")
    export_buttons(result)
    tabs = st.tabs(["Kumulativt och årligt", "Kollager", "Årsdata", "Källor och antaganden"])
    frame = pd.DataFrame(result["rows"])
    with tabs[0]:
        carbon = st.radio("Enhet i diagrammen", ["tCO₂", "tC"], horizontal=True)
        factor = 1 if carbon == "tCO₂" else 12 / 44
        cumulative = frame.set_index("year")[["grossCumulativeCo2", "referenceCumulativeCo2", "netCumulativeCo2"]] * factor
        cumulative.columns = ["Projekt", "Referens", "Netto"]
        st.markdown(f"**Kumulativ förändring ({carbon}/ha)**")
        st.line_chart(cumulative, x_label="År från start", y_label=f"{carbon}/ha")
        st.markdown(f"**Årlig nettoförändring ({carbon}/ha,år)**")
        annual = frame.set_index("year")[["netAnnualCo2"]] * factor
        annual.columns = ["Årligt netto"]
        st.line_chart(annual, x_label="År från start", y_label=f"{carbon}/ha,år")
        if st.checkbox("Visa känslighetsanalys för detta scenario"):
            with st.spinner("Beräknar fem känslighetsfall …"):
                span = sensitivity(serialized, model.ENGINE_HASH)
            st.caption(span["note"] + " Variationerna gäller CCF-tillväxt och blädningsparametrar. "
                       "Markkol, substitution och all annan osäkerhet täcks inte. "
                       "Om kontinuitetsskogsbruk saknas kan alla fem utfall vara lika.")
            st.dataframe(pd.DataFrame({"Körning": ["Grundfall", "Variant 1", "Variant 2", "Variant 3", "Variant 4"],
                                      f"Netto vid slutåret ({carbon}/ha)": [v * factor for v in span["runs"]]}),
                         hide_index=True, use_container_width=True)
    with tabs[1]:
        stock = frame.set_index("year")[["projectLiveC", "projectDeadwoodC", "projectHumusC", "projectSocC", "projectHwpC", "projectStructuralC"]]
        stock.columns = ["Levande biomassa", "Död ved", "Humus", "SOC", "Träprodukter", "Inbyggt stomvirke"]
        st.markdown("**Projektets kollager (tC/ha)**")
        st.line_chart(stock, x_label="År från start", y_label="tC/ha")
        st.caption("Kollagren visas separat. Substitution är inget kollager. Stomvirke särredovisas enligt originalmotorn.")
    with tabs[2]:
        interval = st.selectbox("Visa vart", [1, 5, 10, 20, 25, 50], index=2)
        st.dataframe(frame[(frame.year % interval == 0) | (frame.year == inputs["analysisYears"])],
                     hide_index=True, use_container_width=True)
        st.caption("CSV-filen innehåller varje beräkningsår. Alla motorvariabler är per hektar; fälten med C anger ton kol "
                   "och fälten med Co2 anger ton CO₂. Årsvariabler anger mängd per år. Totala arealresultat finns i JSON-summeringen.")
    with tabs[3]:
        sources = model.original.scenario_sources(result)
        table = pd.DataFrame(sources).rename(columns={"source": "Källa", "role": "Roll", "reason": "Tillämpning", "url": "Länk"})
        st.dataframe(table, hide_index=True, use_container_width=True,
                     column_config={"Länk": st.column_config.LinkColumn("Länk")})
        st.info("Källornas roller beskriver antaganden och kalibrering. Modellen gör ingen statistisk viktning av varje studie till ditt scenario.")
        with st.expander("Visa alla indata som motorn använde"):
            st.json(result["inputs"])


def comparison_view(serialized: str) -> None:
    st.subheader("Jämför skötselmetoder")
    st.write("Alla sex metoder körs med samma ståndort, analysperiod och referens. Landskapsmixen använder dina angivna arealandelar.")
    if st.button("Beräkna jämförelsen", type="primary"):
        with st.spinner("Beräknar sex skötselmetoder …"):
            values = compare(serialized, model.ENGINE_HASH)
        st.session_state.comparison = (serialized, model.ENGINE_HASH, values)
    stored = st.session_state.get("comparison")
    if not stored or stored[:2] != (serialized, model.ENGINE_HASH):
        st.info("Klicka på Beräkna jämförelsen för aktuella indata.")
        return
    values = stored[2]
    lines = pd.DataFrame({v["label"]: v["series"] for v in values})
    lines.index.name = "År från start"
    st.line_chart(lines, x_label="År från start", y_label="Netto (tCO₂/ha)")
    table = [{"Skötselmetod": v["label"], "Netto 50 år (tCO₂/ha)": v["netAt50"],
              "Netto 100 år (tCO₂/ha)": v["netAt100"], "Netto slutår (tCO₂/ha)": v["netAtEnd"],
              "Medeluttag (m³sk/ha,år)": v["meanHarvestM3"]} for v in values]
    st.dataframe(pd.DataFrame(table), hide_index=True, use_container_width=True)
    st.download_button("Hämta jämförelse (CSV)", model.csv_bytes(table), "skogskol_jamforelse.csv", "text/csv")


def references_view() -> None:
    st.subheader("40 referenskontroller")
    st.write("27 kvalitativa utfall från tabell 13.1, åtta mått från Stål m.fl. och fem IVL-mått. "
             "Det är 40 utfall, med flera utfall från samma studie. Kontrollerna använder fasta fall och påverkas inte av ditt eget scenario.")
    if st.button("Kör referenskontroller", type="primary"):
        with st.spinner("Kör referensfallen …"):
            st.session_state.reference_result = (model.ENGINE_HASH, checks(model.ENGINE_HASH))
    stored = st.session_state.get("reference_result")
    if not stored or stored[0] != model.ENGINE_HASH:
        return
    values = stored[1]
    st.success(f"{len(values)} kontroller beräknade. Se status per utfall i tabellen och diagrammet.")
    fields = ["id", "study", "endpoint", "source", "unit", "value", "low", "high", "status", "calibration", "note", "href"]
    rows = [{key: v.get(key) for key in fields} for v in values]
    view = pd.DataFrame(rows)
    view["source"] = view["source"].map(str)
    st.dataframe(view, hide_index=True, use_container_width=True,
                 column_config={"href": st.column_config.LinkColumn("Källänk")})
    st.caption("low–high är fem styrda känslighetsfall. Tecken i källan är kvalitativa; inga numeriska källvärden har lagts till för dem.")
    st.download_button("Hämta referenskontroller (CSV)", model.csv_bytes(rows), "referenskontroller_40.csv", "text/csv")
    with tempfile.TemporaryDirectory() as tmp:
        output = model.original.write_checks_svg(values, Path(tmp) / "referenser.svg")
        svg = output.read_text(encoding="utf-8")
    st.download_button("Hämta referensdiagram (SVG)", svg.encode("utf-8"), "referensdiagram_40.svg", "image/svg+xml")
    components.html(svg, height=850, scrolling=True)


def original_view() -> None:
    st.subheader("Original webbmodell 10.4")
    st.write("Här finns hela det ursprungliga gränssnittet, med alla dess diagram och metodtexter. "
             "Scenariot i denna vy hanteras separat. Använd Spara scenario och Läs in scenario för att flytta indata mellan vyerna.")
    content = (model.BASE / "webbmodell.html").read_text(encoding="utf-8")
    st.download_button("Hämta fristående webbmodell", content.encode("utf-8"), "Skogskolmodellen_10_4.html", "text/html")
    # Ingen nätverksresurs laddas in av modellens skript. All CSS och JavaScript finns i filen.
    components.html(content, height=1500, scrolling=True)


def main() -> None:
    if "draft" not in st.session_state:
        set_draft(model.DEFAULTS)
    st.title("Skogskolmodellen")
    st.caption("Modell 10.4 · Streamlit-utgåva 1 · Jämför skogens och träprodukternas beräknade klimateffekter")
    with st.sidebar:
        st.markdown("### Skogskolmodellen 10.4")
        page = st.radio("Visa", ["Beräkna", "Jämför skötselmetoder", "Referenskontroller", "Original webbmodell", "Publicera och använd"])
    if notice := st.session_state.pop("notice", None):
        st.info(notice)
    try:
        if page in ("Beräkna", "Jämför skötselmetoder"):
            inputs = input_panel()
            serialized = json.dumps(inputs, sort_keys=True, ensure_ascii=False)
            if page == "Beräkna":
                results_view(inputs, serialized)
            else:
                comparison_view(serialized)
        elif page == "Referenskontroller":
            references_view()
        elif page == "Original webbmodell":
            original_view()
        else:
            st.markdown((model.BASE / "PUBLICERING.md").read_text(encoding="utf-8"))
    except (RuntimeError, ValueError) as exc:
        st.error(str(exc))
        st.info("Original webbmodell finns i menyn och kan användas direkt i webbläsaren.")
    with st.sidebar:
        st.caption("Spara ditt scenario som JSON innan du stänger sidan. Appen har ingen databas för sparade projekt.")


if __name__ == "__main__":
    main()
