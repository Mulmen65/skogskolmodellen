"""Streamlit-adapter; originalets beräkningsmotor lämnas oförändrad."""
from __future__ import annotations

import csv
import hashlib
from functools import lru_cache
import io
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

import Skogskolmodellen_v10_4 as original

BASE = Path(__file__).resolve().parent
APP_VERSION = "10.4-streamlit.2"
ENGINE_HASH = hashlib.sha256((original._JS_MODEL + original._JS_STUDIES +
                              original._JS_CONTROLS).encode("utf-8")).hexdigest()
SCHEMA = json.loads((BASE / "input_schema.json").read_text(encoding="utf-8"))
DEFAULTS = json.loads((BASE / "standardscenario.json").read_text(encoding="utf-8"))
FIELDS = {field["key"]: field for field in SCHEMA["fields"]}
SCENARIOS = {
    "natural": "Fri utveckling utan avverkning",
    "conventional": "Trakthyggesbruk, normal omloppstid",
    "extended": "Trakthyggesbruk, förlängd omloppstid",
    "continuous": "Kontinuitetsskogsbruk (blädning)",
    "intensive": "Intensifierat trakthyggesbruk",
    "mix": "Landskapsmix av skötselmetoder",
}


@lru_cache(maxsize=1)
def ensure_node() -> str:
    """nodejs-wheel i requirements.txt ger Node även på Community Cloud."""
    node = os.environ.get("SKOGS_NODE") or shutil.which("node")
    # Även en Pythonmiljö vars Scripts/bin inte finns i PATH stöds.
    if not node:
        import sysconfig
        scripts = Path(sysconfig.get_path("scripts"))
        node = next((str(p) for p in (scripts / "node", scripts / "node.exe")
                     if p.is_file()), None)
    if not node:
        raise RuntimeError("Node.js saknas. Installera alla paket i requirements.txt "
                           "och starta om appen. Original webbmodell kan användas under tiden.")
    try:
        proc = subprocess.run([node, "--version"], capture_output=True, text=True,
                              timeout=15, check=True)
        version = proc.stdout.strip()
        if int(version.lstrip("v").split(".")[0]) < 18:
            raise ValueError(version)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise RuntimeError("Node.js 18 eller senare krävs. Kontrollera att "
                           "requirements.txt har installerats.") from exc
    os.environ["SKOGS_NODE"] = node
    return version


def validate_inputs(values: dict[str, Any]) -> dict[str, Any]:
    """Kontrollera JSON-indata utan att ändra beräkningsmotorns antaganden."""
    if not isinstance(values, dict):
        raise ValueError("Scenariot måste vara ett JSON-objekt.")
    result = dict(DEFAULTS)
    for key, value in values.items():
        if key not in FIELDS:
            continue
        field = FIELDS[key]
        default = DEFAULTS[key]
        if field["type"] == "checkbox":
            if not isinstance(value, bool):
                raise ValueError(f"{field['label']} måste vara true eller false.")
        elif isinstance(default, (float, int)) and not isinstance(default, bool):
            if isinstance(value, bool):
                raise ValueError(f"{field['label']} måste vara ett tal.")
            try:
                value = float(value.replace(",", ".")) if isinstance(value, str) else float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{field['label']} måste vara ett tal.") from exc
            if not math.isfinite(value):
                raise ValueError(f"{field['label']} måste vara ett ändligt tal.")
            scale = 100 if field["percent"] else 1
            shown = value * scale
            for bound, test in (("min", lambda a, b: a < b - 1e-9),
                                ("max", lambda a, b: a > b + 1e-9)):
                if bound in field and test(shown, field[bound]):
                    raise ValueError(f"{field['label']}: värdet ligger utanför "
                                     f"gränsen {field[bound]:g} {field['unit']}.")
            if field["integer"]:
                if not value.is_integer():
                    raise ValueError(f"{field['label']} måste vara ett heltal.")
                value = int(value)
        elif not isinstance(value, str):
            raise ValueError(f"{field['label']} måste vara text.")
        if field["type"] == "select":
            choices = [o["value"] for o in field["options"]]
            if value not in choices:
                raise ValueError(f"Ogiltigt val för {field['label']}: {value!r}.")
        if key == "projectName":
            value = value.strip()[:120] or DEFAULTS[key]
        result[key] = value
    # Samma UI-regel som i den ursprungliga webbmodellen.
    hard_surface = result["currentLandUse"] == "sealed" and result["soilType"] != "organic"
    if not hard_surface:
        result["restorationScenario"] = "notApplicable"
    elif result["restorationScenario"] == "notApplicable":
        result["restorationScenario"] = "full"
    return result


def read_scenario(content: bytes) -> dict[str, Any]:
    if len(content) > 2_000_000:
        raise ValueError("Scenariofilen får vara högst 2 MB.")
    try:
        data = json.loads(content.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Filen är inte en giltig UTF-8-kodad JSON-fil.") from exc
    if not isinstance(data, dict):
        raise ValueError("Scenariofilen måste innehålla ett JSON-objekt.")
    return validate_inputs(data.get("inputs", data))


def scenario_bytes(inputs: dict[str, Any]) -> bytes:
    return json.dumps({"modelVersion": "10.4", "appVersion": APP_VERSION,
                       "inputs": validate_inputs(inputs)}, ensure_ascii=False,
                      indent=2, allow_nan=False).encode("utf-8")


def csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    if not rows:
        return b""
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=list(rows[0]), delimiter=";",
                            extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode("utf-8-sig")


def simulate(inputs: dict[str, Any]) -> dict[str, Any]:
    ensure_node()
    return original.simulate(validate_inputs(inputs))


def compare(inputs: dict[str, Any]) -> list[dict[str, Any]]:
    ensure_node()
    return original.compare_scenarios(validate_inputs(inputs))


def sensitivity(inputs: dict[str, Any]) -> dict[str, Any]:
    ensure_node()
    return original.scenario_range(validate_inputs(inputs))


def reference_checks() -> list[dict[str, Any]]:
    ensure_node()
    return original.reference_checks()


def visible(key: str, i: dict[str, Any]) -> bool:
    """Visa villkorade fält på samma sätt som i webbmodellen."""
    field = FIELDS[key]
    if key.startswith("ageShare") or key in ("landscapeProtectOldest", "landscapeBacklogYears"):
        return i["projectType"] == "landscape"
    if key.startswith("mix"):
        return i["projectForestScenario"] == "mix"
    if key in ("projectStartAge", "initialLiveC"):
        return i["projectType"] == "existing"
    if key == "projectMixedSpruceShare":
        return i["projectSpecies"] in ("mixed", "conifers")
    if key == "projectPineSiteClass":
        return i["projectSpecies"] in ("pine", "mixed", "conifers")
    forest_ref = i["referenceScenario"] == "conventionalForest"
    if field["group"] == 3 and key != "referenceScenario":
        if not forest_ref:
            return False
        if key == "referenceStartAge":
            return i["projectType"] == "existing"
        if key in ("referenceSpecies", "referenceMixedSpruceShare"):
            if i["referenceSpeciesMode"] != "custom":
                return False
            if key == "referenceMixedSpruceShare":
                return i["referenceSpecies"] in ("mixed", "conifers")
        if key in ("referenceProductivityMethod", "referenceProductivityValue", "referencePineSiteClass"):
            if i["referenceProductivityMode"] != "custom":
                return False
            sp = i["referenceSpecies"] if i["referenceSpeciesMode"] == "custom" else i["projectSpecies"]
            if key == "referencePineSiteClass":
                return sp in ("pine", "mixed", "conifers")
    if field["group"] == 4 and key != "includeSoilDom":
        if not i["includeSoilDom"]:
            return False
        if key == "domEquilibrium":
            return i["projectType"] == "existing" and i["currentLandUse"] == "forest"
        if key == "restorationScenario":
            return i["currentLandUse"] == "sealed" and i["soilType"] != "organic"
        if key in ("gisRefSocChange", "gisRefDomChange"):
            return (i["referenceSoilMethod"] == "gisDirect" and
                    i["referenceScenario"] == "continuedLandUse")
    if key in ("ccfUpperStock", "ccfLowerStock"):
        return i["ccfMethod"] == "target"
    if key in ("ccfInterval", "ccfRemoval"):
        return i["ccfMethod"] == "interval"
    if key.startswith("customDf"):
        return i["substitutionSet"] == "custom"
    if key == "structuralShareReference":
        return forest_ref
    return True


def display_label(field: dict[str, Any], inputs: dict[str, Any]) -> str:
    key, label, unit = field["key"], field["label"], field["unit"]
    if key in ("projectProductivityValue", "referenceProductivityValue"):
        prefix = "project" if key.startswith("project") else "reference"
        bonitet = inputs[prefix + "ProductivityMethod"] == "bonitet"
        label = "Bonitet" if bonitet else "H100-värde"
        if prefix == "reference":
            label += " i referensen"
        unit = "m³sk/ha,år" if bonitet else "m"
    if key in ("projectMixedSpruceShare", "referenceMixedSpruceShare"):
        prefix = "project" if key.startswith("project") else "reference"
        species = inputs[prefix + "Species"]
        label = "Andel gran (resten tall)" if species == "conifers" else "Andel gran (resten bok)"
        if prefix == "reference":
            label += " i referensen"
    return label + (f" ({unit})" if unit else "")
