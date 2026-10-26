#!/usr/bin/env python3
# coding: utf-8
"""Skogskolmodellen 10.4 – kör modellen och 40 referenskontroller från Python.

Den oförändrade JavaScript-motorn från webbversion 10.4 finns inbäddad längst
ned i den här filen. Python sköter indata, resultat, export och diagram. Detta
ger samma beräkningsvärden som webbmodellen och är ingen oberoende Python-port.

Krav: Python >= 3.10 och Node.js >= 18 på datorn; inga Python-paket behövs.
https://nodejs.org/ visar hur Node.js installeras. Ange SKOGS_NODE om kommandot
node inte finns i sökvägen, till exempel en fullständig sökväg till node.exe.

Exempel:
    python Skogskolmodellen_v10_4.py --defaults mitt_scenario.json
    # Ändra projekt- och referensvärden i JSON-filen.
    python Skogskolmodellen_v10_4.py --scenario mitt_scenario.json --annual-csv arsresultat.csv
    python Skogskolmodellen_v10_4.py --checks --outdir resultat

I annan Python-kod:
    from Skogskolmodellen_v10_4 import simulate, reference_checks, scenario_range
    result = simulate({"projectType": "new", "analysisYears": 100})
    print(result["summary"]["netCumulativeCo2PerHa"])
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Mapping, Sequence
from xml.sax.saxutils import escape as xml_escape

VERSION = "10.4"

# Engångskod som kör den publicerade motorn i en isolerad Node.js-kontext.
_NODE_RUNNER = r"""
'use strict';
const fs = require('node:fs');
const vm = require('node:vm');
try {
  const req = JSON.parse(fs.readFileSync(0, 'utf8'));
  const ctx = vm.createContext({});
  ctx.self = ctx;
  for (const [i, code] of [req.model, req.studies, req.controls].entries()) {
    vm.runInContext(code, ctx, {filename:`skogskolmodellen-10.4-${i}.js`,timeout:60000});
  }
  const M = ctx.ForestModel, C = ctx.ForestChecks, S = ctx.ForestStudies;
  if (!M || !C || !S || M.MODEL_VERSION !== '10.4')
    throw new Error('Modell 10.4 och referenskontrollerna kunde inte laddas.');
  let value;
  if (req.action === 'simulate') value = M.simulate(req.inputs || {});
  else if (req.action === 'defaults') value = M.DEFAULT_INPUTS;
  else if (req.action === 'checks') value = C.runAll();
  else if (req.action === 'compare') value = M.compareScenarios(req.inputs || {}, req.scenarios || undefined);
  else if (req.action === 'study_cases') value = S.CASES.map(s => ({
    id:s.id, name:s.name, note:s.note, source:s.published, inputs:S.inputsFor(s.id)
  }));
  else if (req.action === 'sensitivity') {
    const base = M.simulate(req.inputs || {});
    const boundary = base.inputs.systemBoundary;
    const candidates = C.variants(base.inputs).slice(1);
    const values = [base, ...candidates.map(i => M.simulate(i))]
      .map(r => r.summary.netByBoundaryCo2PerHa[boundary]);
    value = {unit:'tCO2/ha', systemBoundary:boundary, base:values[0],
      low:Math.min(...values), high:Math.max(...values), runs:values,
      note:'Fem styrda scenariokörningar; inget statistiskt konfidensintervall.'};
  } else throw new Error('Okänt anrop: ' + req.action);
  process.stdout.write(JSON.stringify(value));
} catch (error) {
  process.stderr.write(String(error && error.stack || error) + '\n');
  process.exitCode = 1;
}
"""


def _call(action: str, *, inputs: Mapping[str, Any] | None = None,
          scenarios: Sequence[str] | None = None) -> Any:
    node = os.environ.get('SKOGS_NODE') or shutil.which('node')
    if not node:
        raise RuntimeError('Node.js 18 eller senare behövs. Installera Node.js och '
                           'lägg "node" i PATH, eller ange SKOGS_NODE.')
    request = {'action': action, 'inputs': dict(inputs or {}),
               'scenarios': list(scenarios) if scenarios else None,
               'model': _JS_MODEL, 'studies': _JS_STUDIES,
               'controls': _JS_CONTROLS}
    try:
        completed = subprocess.run([node, '-e', _NODE_RUNNER],
                                   input=json.dumps(request, ensure_ascii=False),
                                   capture_output=True, text=True, encoding='utf-8',
                                   timeout=300, check=False)
    except FileNotFoundError as exc:
        raise RuntimeError(f'Kan inte starta Node.js: {node}') from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError('Modellkörningen tog mer än fem minuter.') from exc
    if completed.returncode != 0:
        raise RuntimeError('Modellen kunde inte beräkna resultatet:\n' +
                           completed.stderr[:3000].strip())
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError('Modellens svar var inte giltig JSON.') from exc


def default_inputs() -> dict[str, Any]:
    """Indatanycklar och förval som i webbmodellens Spara scenario-funktion."""
    return _call('defaults')


def simulate(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Årsserier, summering, normaliserade indata och varningar.

    Återger samma enheter och teckenkonvention som webbversionen: positivt
    kumulativt netto i tCO2/ha betyder större beräknad klimatnytta än referensen.
    """
    if not isinstance(inputs, Mapping):
        raise TypeError('inputs måste vara en ordbok med modellens indatanycklar.')
    return _call('simulate', inputs=inputs)


def compare_scenarios(inputs: Mapping[str, Any],
                      scenarios: Sequence[str] | None = None) -> list[dict[str, Any]]:
    """Jämför skötselmetoder vid samma ståndort och referens."""
    return _call('compare', inputs=inputs, scenarios=scenarios)


def reference_checks() -> list[dict[str, Any]]:
    """Beräkna 27 tecken från tabell 13.1, åtta Stål-mått och fem IVL-mått.

    Varje post innehåller 'source' (publicerat tal eller tecken), 'value'
    (modell), 'low' och 'high' (fem modellkörningar), 'status' och källhänvisning.
    Dessa är 40 utfall, inte 40 oberoende studier eller försöksplatser.
    """
    return _call('checks')


def study_cases() -> list[dict[str, Any]]:
    """De åtta justerbara fallen ur tabell 13.1 med sina förvalda indata."""
    return _call('study_cases')


def scenario_range(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Grundvärde och fyra känslighetsvarianter för exakt de valda indata.

    Ändrar CCF-tillväxt och blädningsandel eller målförråd som i 10.4:s
    Referenskontroll. Täcker inte hela osäkerheten i markkol eller substitution.
    """
    return _call('sensitivity', inputs=inputs)


def load_scenario(path: str | Path) -> dict[str, Any]:
    """Läs både ett vanligt JSON-indataobjekt och webbmodellens sparade JSON."""
    data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict):
        raise ValueError('Scenariofilen måste innehålla ett JSON-objekt.')
    inputs = data.get('inputs', data)
    if not isinstance(inputs, dict):
        raise ValueError('Scenariofilens inputs måste vara ett JSON-objekt.')
    return inputs


def scenario_sources(result: Mapping[str, Any]) -> list[dict[str, str]]:
    """Beskriv spårbart vilka källor och egna val som gäller för ett scenario.

    Denna lista är en beskrivning av modellens antaganden, inte en statistisk
    viktning av enskilda studier till användarens slutresultat.
    """
    i = result['inputs']
    sources: list[dict[str, str]] = []

    def add(name: str, role: str, reason: str, link: str = '') -> None:
        sources.append({'source': name, 'role': role, 'reason': reason, 'url': link})

    add('SLU Riksskogstaxeringen, Skogsdata 2025', 'Grund för åldersprofil',
        'Tillväxtprofil för Götaland, skalad med vald bonitet. Inte en lokal prognos.',
        'https://internt.slu.se/globalassets/ew/org/centrb/rt/dokument/skogsdata/skogsdata_2025_web.pdf')
    conventional_reference = (i['referenceScenario'] == 'conventionalForest' and
                              i['referenceForestScenario'] == 'conventional')
    has_ccf = (i['projectForestScenario'] == 'continuous' or
               i['projectForestScenario'] == 'mix' and i['mixContinuous'] > 0 or
               i['referenceScenario'] == 'conventionalForest' and
               i['referenceForestScenario'] == 'continuous')
    if conventional_reference or i['projectForestScenario'] == 'conventional':
        add('Skogskunskap, slutavverkningsålder', 'Omloppstidens tidsskala',
            'Skötsel och gallringar är även modellantaganden, inte lokala mätningar.',
            'https://www.skogskunskap.se/skota-skog/slutavverka/slutavverkningens-grunder/nar-ska-jag-slutavverka/')
    if has_ccf:
        reason = ('S01 (förråd +47 %) och S03 (uttagskvot 0,85) användes med '
                  'samma skala 0,05 för att välja standardfaktorn 1,06. '
                  'Om du ändrat faktorn är det nya värdet inte kalibrerat mot dessa mål.')
        add('Stål m.fl. (2024)', 'Två kalibreringsmål', reason,
            'https://doi.org/10.1080/02827581.2024.2437409')
        if i['ccfMethod'] == 'target':
            add('Pukkala (2022)', 'Bakgrund till blädningsregel',
                'Målförråden i modellen är schabloner, inte direkt uppmätta i studien.',
                'https://doi.org/10.1016/j.forpol.2021.102646')
        else:
            add('Islam m.fl. (2024)', 'Exempel på intervallskötsel',
                'Ditt val av intervall och uttagsandel styr den egna simuleringen.',
                'https://doi.org/10.1016/j.agrformet.2024.109959')
    if i['includeSoilDom']:
        add('Larsson m.fl. (2025); Vestin m.fl. (2020)', 'Bakgrund markschabloner',
            'Initiala SOC- och DOM-lager kommer från dina indata.',
            'https://doi.org/10.1016/j.foreco.2024.122458')
    if i['systemBoundary'] != 'ecosystem':
        add('IPCC (2019), volym 4', 'Träprodukternas lager',
            'Träprodukternas halveringstider och fördelning är modellantaganden.',
            'https://www.ipcc-nggip.iges.or.jp/public/2019rf/vol4.html')
    if i['systemBoundary'] == 'substitution':
        if i['substitutionSet'] == 'high':
            add('Leskinen m.fl. (2018)', 'Hög substitutionsnivå',
                'Produktfaktorer i modellen, inte uppmätt bindning i skogen.',
                'https://efi.int/sites/default/files/files/publication-bank/2019/efi_fstp_7_2018.pdf')
        elif i['substitutionSet'] == 'custom':
            add('Egen substitutionsfaktor', 'Användarens val',
                'Faktorerna kommer från dina egna indata.')
        elif i['substitutionSet'] == 'none':
            add('Ingen substitution', 'Avstängd effekt',
                'Substitution ingår inte med vald nivå.')
        else:
            add('Hurmekoski m.fl. (2023)', 'Substitutionsantaganden',
                'Vald nivå och framtidsbana styr det beräknade resultatet.',
                'https://doi.org/10.1016/j.rser.2023.113152')
    if has_ccf and conventional_reference:
        add('Pukkala, Malmaeus & Mattsson (2026)', 'Oberoende jämförelse',
            'Svenska landskap över 75 år; används inte för kalibrering i 10.4.',
            'https://www.diva-portal.org/smash/get/diva2:2057070/FULLTEXT01.pdf')
        add('Högbom m.fl. (2025), tabell 13.1', 'Kvalitativ jämförelse',
            '27 tecken för kollager från andra studier och scenarier.',
            'https://doi.org/10.1007/978-3-031-70484-0_13')
    return sources


def write_annual_csv(result: Mapping[str, Any], path: str | Path) -> Path:
    """Exportera alla beräknade årsvariabler till semikolonseparerad CSV."""
    rows = result['rows']
    if not rows:
        raise ValueError('Årsserien är tom.')
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter=';')
        writer.writeheader()
        writer.writerows(rows)
    return dest


def write_checks_csv(checks: Sequence[Mapping[str, Any]], path: str | Path) -> Path:
    """Spara källvärden, modellvärden, scenariospann och källänkar."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fields = ['id', 'study', 'endpoint', 'source', 'unit', 'value', 'low',
              'high', 'status', 'horizon', 'comparable', 'calibration', 'href', 'note']
    with dest.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream, delimiter=';')
        writer.writerow(fields)
        for c in checks:
            writer.writerow([c.get(k, '') for k in fields])
    return dest


def _unit(value: Any, unit: str) -> str:
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        return '—'
    if unit == 'andel':
        return f'{value * 100:.1f} %'.replace('.', ',')
    if unit == 'kvot':
        return f'{value:.2f}'.replace('.', ',') + ' kvot'
    return f'{value:.1f}'.replace('.', ',') + f' {unit}'


def write_checks_svg(checks: Sequence[Mapping[str, Any]], path: str | Path) -> Path:
    """Gör en fristående vektorgraf med alla publicerade resultat och modellspann.

    Romb ritas bara för publicerade tal. Ett publicerat +/−/n.d. får endast
    en text om riktning; ingen numerisk punkt hittas på.
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    height = 115 * len(checks) + 145
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="{height}" viewBox="0 0 1000 {height}">',
           f'<rect width="1000" height="{height}" fill="white"/>',
           '<text x="24" y="35" fill="#173f35" font-size="24" font-weight="bold">Skogskolmodellen 10.4 · Referenskontroll</text>',
           '<text x="24" y="60" fill="#33443d" font-size="13">◆ publicerat tal (om det finns) · ● modellvärde · linje modellens scenariospann · egen skala per rad</text>',
           '<text x="24" y="80" fill="#586963" font-size="12">Fem valda känslighetskörningar; spannet är inget statistiskt konfidensintervall.</text>']
    def text(x: int | float, y: int | float, content: Any, *, size: int = 12,
             color: str = '#26332f', weight: str = 'normal') -> str:
        return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" '
                f'font-weight="{weight}">{xml_escape(str(content))}</text>')
    for n, c in enumerate(checks):
        y = 102 + n * 115
        model, lo, hi = (c.get('value'), c.get('low'), c.get('high'))
        unit = str(c['unit'])
        sign = str(c['source'])
        numeric = isinstance(c['source'], (int, float)) and not isinstance(c['source'], bool)
        study = _unit(c['source'], unit) if numeric else sign
        title = f"{c['id']} · {c['study']} · {c['endpoint']}"
        label = f'Studie: {study}   |   Modell: {_unit(model, unit)}'
        svg.append(f'<g><title>{xml_escape(title + " · " + str(c["status"]))}</title>')
        svg.append(f'<rect x="24" y="{y}" width="952" height="105" rx="7" fill="#f4f8f6"/>')
        svg.append(text(38, y + 22, title[:49] + ('…' if len(title) > 49 else ''),
                        size=12, color='#173f35', weight='bold'))
        svg.append(text(38, y + 43, label[:49] + ('…' if len(label) > 49 else ''), size=11))
        svg.append(text(38, y + 64, f"Tolkning: {c['status']}", size=11))
        svg.append(text(38, y + 86, f"Spann: {_unit(lo, unit)} till {_unit(hi, unit)}", size=11))
        if all(isinstance(v, (int, float)) and math.isfinite(v) for v in [model, lo, hi]):
            x0, x1, yy = 430, 955, y + 53
            midpoint = 1.0 if unit in ('andel', 'kvot') else 0.0
            values = [midpoint, model, lo, hi] + ([float(c['source'])] if numeric else [])
            a, b = min(values), max(values)
            span = b - a or max(.1, abs(b) * .25)
            a = max(0, a - span * .12) if unit in ('andel', 'kvot') else a - span * .12
            b += span * .12
            x = lambda v: x0 + (v - a) * (x1 - x0) / (b - a)
            status = str(c['status']).lower()
            color = '#ae4144' if 'avvikande' in status or 'utanför spann' in status else (
                '#ae710f' if 'känsligt' in status else '#197b78')
            svg.extend([f'<rect x="415" y="{y+8}" width="550" height="92" fill="white"/>',
                        f'<path d="M{x0} {yy}H{x1}" stroke="#ced8d4" stroke-width="2"/>',
                        f'<path d="M{x(midpoint)} {yy-24}V{yy+16}" stroke="#8d9b96" stroke-dasharray="3 3"/>',
                        f'<path d="M{x(lo)} {yy}H{x(hi)}" stroke="{color}" stroke-width="5"/>',
                        f'<circle cx="{x(model)}" cy="{yy}" r="6" fill="{color}" stroke="white"/>'])
            if numeric:
                t = x(float(c['source']))
                points = f'{t},{yy-10} {t+7},{yy-3} {t},{yy+4} {t-7},{yy-3}'
                svg.append(f'<polygon points="{points}" fill="#b76419" stroke="white"/>')
            else:
                svg.append(text(x0 + 8, y + 26, 'Källa: ' + sign, size=11, color='#a45611'))
            svg.append(text(x0, y + 85, _unit(a, unit), size=10, color='#51615b'))
            svg.append(text(x1 - 80, y + 85, _unit(b, unit), size=10, color='#51615b'))
        svg.append('</g>')
    svg.append('</svg>')
    dest.write_text('\n'.join(svg), encoding='utf-8')
    return dest


def _print_scenario(result: Mapping[str, Any], *, with_sensitivity: bool) -> None:
    summary = result['summary']
    i = result['inputs']
    amounts = summary['netByBoundaryCo2PerHa']
    eco, hwp, total = amounts['ecosystem'], amounts['hwp'], amounts['substitution']
    boundary = i['systemBoundary']
    fmt = lambda n: f'{n:+.1f}'.replace('.', ',')
    print(f'Skogskolmodellen {VERSION}: {i["projectName"]}')
    print(f'{i["analysisYears"]} år; {i["projectForestScenario"]} mot '
          f'{i["referenceScenario"]} · {boundary}')
    print(f'Netto vald gräns: {fmt(amounts[boundary])} tCO2/ha')
    print(f'  Skog och mark:         {fmt(eco)} tCO2/ha')
    print(f'  Träprodukter:          {fmt(hwp - eco)} tCO2/ha')
    print(f'  Substitution:          {fmt(total - hwp)} tCO2/ha')
    if with_sensitivity:
        rng = scenario_range(i)
        print(f'Scenariospann: {fmt(rng["low"])} till {fmt(rng["high"])} '
              'tCO2/ha (fem körningar, inget konfidensintervall)')
    print('Referenser bakom valda antaganden (ingen viktad medelberäkning):')
    for ref in scenario_sources(result):
        print(f'  - {ref["source"]}: {ref["role"]}. {ref["reason"]}')
    if i['projectType'] == 'new' and i['projectForestScenario'] in ('continuous', 'mix'):
        print('OBS: De 40 kontrollerna återskapar inte exakt nybeskogning på denna plats.')
    for warning in result['warnings']:
        print(f'Obs: {warning}')


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--defaults', metavar='FIL', help='Skriv modellens förvalda indata som JSON.')
    parser.add_argument('--scenario', metavar='FIL', help='Läs indata eller webbmodellens sparade scenario-JSON.')
    parser.add_argument('--annual-csv', metavar='FIL', help='Spara årsraderna efter --scenario.')
    parser.add_argument('--result-json', metavar='FIL', help='Spara fullständigt resultat efter --scenario.')
    parser.add_argument('--checks', action='store_true', help='Kör alla 40 referenskontroller och spara CSV, JSON och SVG.')
    parser.add_argument('--outdir', metavar='MAPP', default='.', help='Utdatamapp för --checks; förvalt aktuell mapp.')
    parser.add_argument('--compare', action='store_true', help='Visa övriga skötselmetoders netto för --scenario.')
    parser.add_argument('--version', action='version', version=VERSION)
    args = parser.parse_args(argv)
    if not any([args.defaults, args.scenario, args.checks]):
        parser.print_help()
        return 0
    if (args.annual_csv or args.result_json or args.compare) and not args.scenario:
        parser.error('--annual-csv, --result-json och --compare kräver --scenario.')
    if args.defaults:
        dest = Path(args.defaults)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(default_inputs(), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print('Sparade förvalda indata:', dest)
    if args.scenario:
        inputs = load_scenario(args.scenario)
        result = simulate(inputs)
        _print_scenario(result, with_sensitivity=True)
        if args.annual_csv:
            print('Årsresultat:', write_annual_csv(result, args.annual_csv))
        if args.result_json:
            dest = Path(args.result_json)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print('Fullständigt resultat:', dest)
        if args.compare:
            for item in compare_scenarios(inputs):
                print(f'  {item["scenario"]:<15} {item["netAtEnd"]:+.1f} tCO2/ha')
    if args.checks:
        out = Path(args.outdir)
        out.mkdir(parents=True, exist_ok=True)
        checks = reference_checks()
        if len(checks) != 40:
            raise RuntimeError(f'Förväntade 40 kontroller, fick {len(checks)}.')
        csv_path = write_checks_csv(checks, out / 'referenskontroll_40_v10.4.csv')
        json_path = out / 'referenskontroll_40_v10.4.json'
        json_path.write_text(json.dumps({'version': VERSION, 'records': checks},
                                        ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        svg_path = write_checks_svg(checks, out / 'Referenskontroll_diagram_v10.4.svg')
        print('Sparade 40 kontroller:', csv_path, json_path, svg_path, sep='\n  ')
    return 0


# Exakta källkoder ur Skogskolmodellen 10.4:s fristående index.html.
# Läsbara för revision och helt inbäddade, så ingen HTML-fil krävs vid körning.
_JS_MODEL = r"""

(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.ForestModel = api;
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const MODEL_VERSION = '10.4'; // Fit mot Stål 2024, se kalibreringsavsnittet.
  const CO2_PER_C = 44 / 12;

  const SPECIES_LABELS = {
    pine: 'Tall',
    spruce: 'Gran',
    conifers: 'Barrskog (gran/tall)',
    mixed: 'Blandskog (gran/bok)',
    beech: 'Bok',
    oak: 'Ek',
  };

  const SCENARIO_LABELS = {
    natural: 'Fri utveckling utan avverkning',
    conventional: 'Trakthyggesbruk, normal omloppstid',
    extended: 'Trakthyggesbruk, förlängd omloppstid',
    continuous: 'Kontinuitetsskogsbruk (blädning)',
    intensive: 'Intensifierat trakthyggesbruk',
    mix: 'Landskapsmix av skötselmetoder',
  };
  const PURE_SCENARIOS = ['natural', 'conventional', 'extended', 'continuous', 'intensive'];
  const COMPARISON_SCENARIOS = ['natural', 'conventional', 'extended', 'continuous', 'intensive', 'mix'];
  const CLEARCUT_SCENARIOS = ['conventional', 'extended', 'intensive'];

  const BOUNDARY_LABELS = {
    ecosystem: 'Ekosystem',
    hwp: 'Ekosystem + träprodukter',
    substitution: 'Ekosystem + träprodukter + substitution',
  };

  const H100_TABLES = {
    pineNormal: {10: 1.4, 12: 1.9, 14: 2.4, 16: 2.9, 18: 3.6, 20: 4.3, 22: 5.1, 24: 5.9, 26: 6.8, 28: 7.7, 30: 8.8},
    pineWeak: {10: 1.1, 12: 1.6, 14: 1.9, 16: 2.5, 18: 3.1, 20: 3.7, 22: 4.4, 24: 5.2, 26: 6.0, 28: 7.1},
    spruce: {16: 3.6, 18: 4.4, 20: 5.2, 22: 6.0, 24: 6.9, 26: 7.9, 28: 9.0, 30: 10.1, 32: 11.3, 34: 12.6, 36: 13.9},
    beech: {20: 3.6, 22: 4.3, 24: 5.1, 26: 5.6, 28: 6.3, 30: 7.1, 32: 7.8},
    oak: {20: 3.3, 22: 3.9, 24: 4.6, 26: 5.2, 28: 5.9},
  };

  // Förenklade planeringsparametrar. Tillväxtprofilen är kalibrerad mot
  // Riksskogstaxeringen (Skogsdata 2025); övriga parametrar är schabloner.
  const SPECIES_PARAMS = {
    pine: {rotation: 90, bef: 1.35, woodDensity: 0.42, rootRatio: 0.25, matureAge: 100,
      mortalityBase: 0.0035, mortalityOldAdd: 0.0025, deadwoodDecay: 0.040, litterTurnover: 0.004,
      humificationShare: 0.12, humusDecay: 0.030, socStabilisation: 0.020, socDecay: 0.003},
    spruce: {rotation: 70, bef: 1.40, woodDensity: 0.38, rootRatio: 0.28, matureAge: 100,
      mortalityBase: 0.0040, mortalityOldAdd: 0.0025, deadwoodDecay: 0.050, litterTurnover: 0.004,
      humificationShare: 0.12, humusDecay: 0.030, socStabilisation: 0.020, socDecay: 0.003},
    mixed: {rotation: 95, bef: 1.425, woodDensity: 0.47, rootRatio: 0.265, matureAge: 110,
      mortalityBase: 0.0035, mortalityOldAdd: 0.0025, deadwoodDecay: 0.043, litterTurnover: 0.005,
      humificationShare: 0.135, humusDecay: 0.028, socStabilisation: 0.023, socDecay: 0.003},
    beech: {rotation: 120, bef: 1.45, woodDensity: 0.56, rootRatio: 0.25, matureAge: 120,
      mortalityBase: 0.0030, mortalityOldAdd: 0.0025, deadwoodDecay: 0.035, litterTurnover: 0.006,
      humificationShare: 0.15, humusDecay: 0.025, socStabilisation: 0.025, socDecay: 0.003},
    oak: {rotation: 140, bef: 1.50, woodDensity: 0.56, rootRatio: 0.30, matureAge: 140,
      mortalityBase: 0.0025, mortalityOldAdd: 0.0025, deadwoodDecay: 0.030, litterTurnover: 0.006,
      humificationShare: 0.15, humusDecay: 0.025, socStabilisation: 0.025, socDecay: 0.003},
  };

  const NFI_GOTALAND_MEAN_BONITET = 8.8;
  // v10: styckvis linjär profil genom åldersklassernas mittpunkter; nodvärdena bevarar klassmedelvärdena.
  const NFI_PROFILE_NODES = [[0, 0.0], [10, 2.63], [30, 9.626], [50, 8.614], [70, 7.682], [90, 7.048], [110, 5.453], [130, 4.492]];
  // Markmodul v10 (kalibrerad mot Larsson m.fl. 2025, Gundale m.fl. 2024, Vestin m.fl. 2020, Grelle m.fl. 2023).
  const SOIL = {
    litterMax: 2.6, litterHalfLive: 20.0, groundLitter: 0.15, groundOpen: 0.5, openHalfLive: 15.0,
    kLitter: 0.30, hLitter: 0.20, kFine: 0.07, hFine: 0.25, hCoarse: 0.25,
    kHumus: 0.012, sHumus: 0.35, kSoc: 0.003, coarseRootShare: 0.75,
  };
  const DOM_SPLIT = {coarse: 0.15, fine: 0.05, litter: 0.05, humus: 0.75};
  const CCF_TARGET_EXPONENT = 0.5;
  // Lägsta ålder för föryngringsavverkning (skogsvårdslagen; Skogskunskap) som tidsskala.
  const LAF_SOUTH = {12: 90, 16: 80, 20: 70, 24: 65, 28: 60, 32: 50, 36: 45};
  const LAF_NORTH = {12: 100, 16: 90, 20: 80, 24: 70, 28: 65, 32: 55, 36: 50};
  const LAF_REFERENCE = 60.0;
  const LAF_ROTATION_BASE = 65.0;
  const DISTURBANCE_LEVELS = {off: 0, low: 0.001, medium: 0.0025, high: 0.005};
  const DISTURBANCE_SPECIES = {spruce: 1.0, pine: 0.5, mixed: 0.6, beech: 0.3, oak: 0.2};
  const NFI_GOTALAND_INCREMENT_BY_AGE = [
    {maxAge: 20, increment: 3.0},
    {maxAge: 40, increment: 8.7},
    {maxAge: 60, increment: 8.6},
    {maxAge: 80, increment: 7.7},
    {maxAge: 100, increment: 6.9},
    {maxAge: 120, increment: 5.5},
    {maxAge: Infinity, increment: 4.6},
  ];

  // tC/ha,år. Schabloner för planeringsbruk; lokala värden bör prioriteras.
  const LAND_FACTORS = {
    'cropland|mineral|notApplicable': {soc1to20: -0.10, soc21to100: 0.05, soc101plus: 0.02, dom1to20: 0.05, dom21to100: 0.02, dom101plus: 0.01, refSoc: -0.05, refDom: 0.00, uncertainty: 'Hög'},
    'grassland|mineral|notApplicable': {soc1to20: 0.00, soc21to100: 0.03, soc101plus: 0.01, dom1to20: 0.04, dom21to100: 0.02, dom101plus: 0.01, refSoc: 0.00, refDom: 0.00, uncertainty: 'Hög'},
    'sealed|mineral|full': {soc1to20: 0.03, soc21to100: 0.05, soc101plus: 0.02, dom1to20: 0.03, dom21to100: 0.02, dom101plus: 0.01, refSoc: 0.00, refDom: 0.00, uncertainty: 'Mycket hög'},
    'sealed|mineral|partial': {soc1to20: 0.01, soc21to100: 0.02, soc101plus: 0.01, dom1to20: 0.01, dom21to100: 0.01, dom101plus: 0.005, refSoc: 0.00, refDom: 0.00, uncertainty: 'Mycket hög'},
    'sealed|mineral|unspecified': {soc1to20: 0.00, soc21to100: 0.00, soc101plus: 0.00, dom1to20: 0.00, dom21to100: 0.00, dom101plus: 0.00, refSoc: 0.00, refDom: 0.00, uncertainty: 'Mycket hög'},
    'otherOpen|mineral|notApplicable': {soc1to20: 0.00, soc21to100: 0.02, soc101plus: 0.01, dom1to20: 0.03, dom21to100: 0.02, dom101plus: 0.01, refSoc: 0.00, refDom: 0.00, uncertainty: 'Hög'},
    'forest|mineral|notApplicable': {soc1to20: 0.00, soc21to100: 0.00, soc101plus: 0.02, dom1to20: 0.00, dom21to100: 0.00, dom101plus: 0.01, refSoc: 0.00, refDom: 0.00, uncertainty: 'Hög'},
    'any|organic|notApplicable': {soc1to20: -1.00, soc21to100: -0.70, soc101plus: -0.50, dom1to20: 0.00, dom21to100: 0.00, dom101plus: 0.00, refSoc: -1.20, refDom: 0.00, uncertainty: 'Mycket hög'},
    'unknown|mineral|notApplicable': {soc1to20: 0.00, soc21to100: 0.00, soc101plus: 0.00, dom1to20: 0.00, dom21to100: 0.00, dom101plus: 0.00, refSoc: 0.00, refDom: 0.00, uncertainty: 'Mycket hög'},
  };

  // Substitutionsfaktorer, tC undvikt fossilt kol per tC i produkten.
  // Värden [år 2020, år 2050]; linjär interpolation däremellan, konstant utanför.
  // eolSawnwood/eolPaper avser energiåtervinning när produkten kasseras.
  const SUBSTITUTION_SETS = {
    none: {label: 'Ingen substitution', sawnwood: [0, 0], paper: [0, 0], energy: [0, 0], eolSawnwood: [0, 0], eolPaper: [0, 0]},
    lowDecarb: {label: 'Låg, avtagande till 2050 (Hurmekoski m.fl.)', sawnwood: [0.93, 0.34], paper: [0.10, 0.07], energy: [0.57, 0.11], eolSawnwood: [0.22, 0.09], eolPaper: [0.26, 0.09]},
    low: {label: 'Låg, dagens nivå konstant', sawnwood: [0.93, 0.93], paper: [0.10, 0.10], energy: [0.57, 0.57], eolSawnwood: [0.22, 0.22], eolPaper: [0.26, 0.26]},
    high: {label: 'Hög, produktnivå (Leskinen m.fl. 2018)', sawnwood: [1.30, 1.30], paper: [1.00, 1.00], energy: [0.57, 0.57], eolSawnwood: [0.22, 0.22], eolPaper: [0.26, 0.26]},
  };
  const AGE_CLASS_KEYS = ['ageShare0to20', 'ageShare21to40', 'ageShare41to60', 'ageShare61to80',
    'ageShare81to100', 'ageShare101to120', 'ageShare121to140'];

  const DEFAULT_INPUTS = Object.freeze({
    projectName: 'Nytt skogsscenario',
    areaHa: 1,
    analysisYears: 200,
    startYear: 2026,
    projectType: 'new',
    region: 'south',
    disturbanceLevel: 'off',
    salvageShare: 0.7,
    domEquilibrium: true,
    projectForestScenario: 'natural',
    projectSpecies: 'spruce',
    projectProductivityMethod: 'h100',
    projectProductivityValue: 24,
    projectPineSiteClass: 'normal',
    projectMixedSpruceShare: 0.50,
    projectStartAge: 0,
    initialLiveC: 0,

    ageShare0to20: 0.30,
    ageShare21to40: 0.28,
    ageShare41to60: 0.20,
    ageShare61to80: 0.12,
    ageShare81to100: 0.05,
    ageShare101to120: 0.03,
    ageShare121to140: 0.02,
    landscapeProtectOldest: true,
    landscapeBacklogYears: 20,

    mixNatural: 0.20,
    mixConventional: 0.47,
    mixExtended: 0.00,
    mixContinuous: 0.33,
    mixIntensive: 0.00,

    referenceScenario: 'continuedLandUse',
    referenceForestScenario: 'conventional',
    referenceSpeciesMode: 'same',
    referenceSpecies: 'spruce',
    referenceProductivityMode: 'same',
    referenceProductivityMethod: 'h100',
    referenceProductivityValue: 24,
    referencePineSiteClass: 'normal',
    referenceMixedSpruceShare: 0.50,
    referenceStartAge: 0,

    includeSoilDom: true,
    currentLandUse: 'cropland',
    soilType: 'mineral',
    restorationScenario: 'notApplicable',
    initialSoc0to50: 80,
    initialDom: 10,
    referenceSoilMethod: 'internal',
    gisRefSocChange: 0,
    gisRefDomChange: 0,

    // Skötselparametrar
    extensionYears: 30,
    thinningCount: 2,
    thinningShare: 0.25,
    ccfMethod: 'target',
    ccfUpperStock: 250,
    ccfLowerStock: 150,
    ccfInterval: 20,
    ccfRemoval: 0.30,
    ccfGrowthFactor: 1.06,
    ccfFirstCutFraction: 0.60,
    ccfStructuralAge: 70,
    breedingGain: 0.20,
    intensiveGrowthBoost: 0.15,
    intensiveGrotShare: 0.65,
    grotShare: 0.30,
    retentionShare: 0.00,
    clearcutHumusLoss: 0.15,

    // Träprodukter och substitution
    systemBoundary: 'ecosystem',
    substitutionSet: 'lowDecarb',
    customDfSawnwood: 0.9,
    customDfPaper: 0.1,
    customDfEnergy: 0.5,
    hwpHalfLifeSawnwood: 35,
    hwpHalfLifePaper: 2,
    productSawnFinal: 0.30,
    productPaperFinal: 0.40,
    productSawnCcf: 0.38,
    productPaperCcf: 0.32,
    productSawnThinning: 0.10,
    productPaperThinning: 0.60,

    // Inbyggt långlivat stomvirke (särredovisas). 0 % ger samma resultat som version 9.0.
    structuralShareProject: 0,
    structuralShareReference: 0,
    structuralHalfLife: 100,
    includeStructural: true,
  });

  function numberOr(value, fallback) {
    if (typeof value === 'string') value = value.replace(',', '.').trim();
    if (value === '' || value === null || value === undefined) return fallback;
    const n = Number(value);
    return Number.isFinite(n) ? n : fallback;
  }

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  function normaliseInputs(raw) {
    const d = DEFAULT_INPUTS;
    const i = Object.assign({}, d, raw || {});
    const num = (key, min, max) => clamp(numberOr(i[key], d[key]), min, max);
    i.areaHa = num('areaHa', 0.0001, 1e7);
    i.analysisYears = Math.round(num('analysisYears', 1, 300));
    i.startYear = Math.round(num('startYear', 1900, 2200));
    i.projectProductivityValue = num('projectProductivityValue', 0.1, 50);
    i.projectMixedSpruceShare = num('projectMixedSpruceShare', 0, 1);
    i.projectStartAge = Math.round(num('projectStartAge', 0, 400));
    i.initialLiveC = Math.max(0, numberOr(i.initialLiveC, 0));
    i.referenceProductivityValue = num('referenceProductivityValue', 0.1, 50);
    i.referenceMixedSpruceShare = num('referenceMixedSpruceShare', 0, 1);
    i.referenceStartAge = Math.round(clamp(numberOr(i.referenceStartAge, i.projectStartAge), 0, 400));
    i.initialSoc0to50 = Math.max(0, numberOr(i.initialSoc0to50, 80));
    i.initialDom = Math.max(0, numberOr(i.initialDom, 10));
    i.gisRefSocChange = numberOr(i.gisRefSocChange, 0);
    i.gisRefDomChange = numberOr(i.gisRefDomChange, 0);
    i.includeSoilDom = Boolean(i.includeSoilDom);
    ['mixNatural', 'mixConventional', 'mixExtended', 'mixContinuous', 'mixIntensive'].forEach((k) => { i[k] = num(k, 0, 1); });
    AGE_CLASS_KEYS.forEach((k) => { i[k] = num(k, 0, 1); });
    i.landscapeProtectOldest = Boolean(i.landscapeProtectOldest);
    i.landscapeBacklogYears = Math.round(num('landscapeBacklogYears', 0, 60));
    if (!['new', 'existing', 'landscape'].includes(i.projectType)) i.projectType = d.projectType;
    if (!['target', 'interval'].includes(i.ccfMethod)) i.ccfMethod = d.ccfMethod;
    i.ccfUpperStock = num('ccfUpperStock', 20, 1000);
    i.ccfLowerStock = clamp(numberOr(i.ccfLowerStock, d.ccfLowerStock), 10, i.ccfUpperStock * 0.95);
    i.breedingGain = num('breedingGain', 0, 1);
    if (!['south', 'north'].includes(i.region)) i.region = d.region;
    if (!(i.disturbanceLevel in DISTURBANCE_LEVELS)) i.disturbanceLevel = d.disturbanceLevel;
    i.salvageShare = num('salvageShare', 0, 1);
    i.domEquilibrium = i.domEquilibrium === undefined ? true : Boolean(i.domEquilibrium);
    if (!SCENARIO_LABELS[i.projectForestScenario]) i.projectForestScenario = d.projectForestScenario;
    if (!PURE_SCENARIOS.includes(i.referenceForestScenario)) i.referenceForestScenario = d.referenceForestScenario;
    i.extensionYears = Math.round(num('extensionYears', 0, 150));
    i.thinningCount = Math.round(num('thinningCount', 0, 3));
    i.thinningShare = num('thinningShare', 0, 0.6);
    i.ccfInterval = Math.round(num('ccfInterval', 5, 60));
    i.ccfRemoval = num('ccfRemoval', 0.05, 0.6);
    i.ccfGrowthFactor = num('ccfGrowthFactor', 0.3, 1.5);
    i.ccfFirstCutFraction = num('ccfFirstCutFraction', 0.2, 1.5);
    i.ccfStructuralAge = Math.round(num('ccfStructuralAge', 20, 200));
    i.intensiveGrowthBoost = num('intensiveGrowthBoost', 0, 1);
    i.intensiveGrotShare = num('intensiveGrotShare', 0, 1);
    i.grotShare = num('grotShare', 0, 1);
    i.retentionShare = num('retentionShare', 0, 0.5);
    i.clearcutHumusLoss = num('clearcutHumusLoss', 0, 0.6);
    if (!BOUNDARY_LABELS[i.systemBoundary]) i.systemBoundary = d.systemBoundary;
    if (!SUBSTITUTION_SETS[i.substitutionSet] && i.substitutionSet !== 'custom') i.substitutionSet = d.substitutionSet;
    i.customDfSawnwood = num('customDfSawnwood', 0, 5);
    i.customDfPaper = num('customDfPaper', 0, 5);
    i.customDfEnergy = num('customDfEnergy', 0, 5);
    i.hwpHalfLifeSawnwood = num('hwpHalfLifeSawnwood', 1, 200);
    i.hwpHalfLifePaper = num('hwpHalfLifePaper', 0.5, 50);
    i.productSawnFinal = num('productSawnFinal', 0, 1);
    i.productPaperFinal = clamp(numberOr(i.productPaperFinal, d.productPaperFinal), 0, 1 - i.productSawnFinal);
    i.productSawnThinning = num('productSawnThinning', 0, 1);
    i.productPaperThinning = clamp(numberOr(i.productPaperThinning, d.productPaperThinning), 0, 1 - i.productSawnThinning);
    i.structuralShareProject = num('structuralShareProject', 0, 1);
    i.structuralShareReference = num('structuralShareReference', 0, 1);
    i.structuralHalfLife = num('structuralHalfLife', 5, 1000);
    i.includeStructural = i.includeStructural === undefined ? true : Boolean(i.includeStructural);
    i.productSawnCcf = num('productSawnCcf', 0, 1);
    i.productPaperCcf = clamp(numberOr(i.productPaperCcf, d.productPaperCcf), 0, 1 - i.productSawnCcf);
    return i;
  }

  function interpolateTable(table, x) {
    const xs = Object.keys(table).map(Number).sort((a, b) => a - b);
    if (x <= xs[0]) return table[xs[0]];
    if (x >= xs[xs.length - 1]) return table[xs[xs.length - 1]];
    for (let idx = 0; idx < xs.length - 1; idx += 1) {
      const lo = xs[idx];
      const hi = xs[idx + 1];
      if (x >= lo && x <= hi) return table[lo] + ((x - lo) * (table[hi] - table[lo])) / (hi - lo);
    }
    throw new Error('Interpolation misslyckades.');
  }

  function bonitetFromForestConfig(config) {
    if (config.productivityMethod === 'bonitet') return numberOr(config.productivityValue, 0);
    const h100 = numberOr(config.productivityValue, 24);
    const pineTable = config.pineSiteClass === 'weak' ? H100_TABLES.pineWeak : H100_TABLES.pineNormal;
    if (config.species === 'pine') return interpolateTable(pineTable, h100);
    if (config.species === 'spruce') return interpolateTable(H100_TABLES.spruce, h100);
    if (config.species === 'beech') return interpolateTable(H100_TABLES.beech, h100);
    if (config.species === 'oak') return interpolateTable(H100_TABLES.oak, h100);
    if (config.species === 'conifers') {
      const s = clamp(numberOr(config.mixedSpruceShare, 0.5), 0, 1);
      return s * interpolateTable(H100_TABLES.spruce, h100) + (1 - s) * interpolateTable(pineTable, h100);
    }
    const share = clamp(numberOr(config.mixedSpruceShare, 0.5), 0, 1);
    return share * interpolateTable(H100_TABLES.spruce, h100) + (1 - share) * interpolateTable(H100_TABLES.beech, h100);
  }

  function projectForestConfig(i) {
    return {
      species: i.projectSpecies,
      productivityMethod: i.projectProductivityMethod,
      productivityValue: i.projectProductivityValue,
      pineSiteClass: i.projectPineSiteClass,
      mixedSpruceShare: i.projectMixedSpruceShare,
    };
  }

  function referenceForestConfig(i) {
    const sameSpecies = i.referenceSpeciesMode === 'same';
    const sameProductivity = i.referenceProductivityMode === 'same';
    return {
      species: sameSpecies ? i.projectSpecies : i.referenceSpecies,
      productivityMethod: sameProductivity ? i.projectProductivityMethod : i.referenceProductivityMethod,
      productivityValue: sameProductivity ? i.projectProductivityValue : i.referenceProductivityValue,
      pineSiteClass: sameProductivity ? i.projectPineSiteClass : i.referencePineSiteClass,
      mixedSpruceShare: sameSpecies ? i.projectMixedSpruceShare : i.referenceMixedSpruceShare,
    };
  }

  function curveParams(config) {
    const p = SPECIES_PARAMS[config.species];
    if (!p) throw new Error('Okänd trädart.');
    return {p, bonitet: bonitetFromForestConfig(config)};
  }

  // Fördelning av levande kol på stam, grenar/toppar och stubbe/rötter.
  function carbonPartition(config) {
    const part = (p) => {
      const factor = p.bef * p.woodDensity * 0.5 * (1 + p.rootRatio);
      const stemCPerM3 = p.woodDensity * 0.5;
      const rootC = factor * p.rootRatio / (1 + p.rootRatio);
      return {factor, stemCPerM3, rootC};
    };
    let factor;
    let stemCPerM3;
    let rootC;
    if (config.species === 'mixed') {
      const s = clamp(numberOr(config.mixedSpruceShare, 0.5), 0, 1);
      const a = part(SPECIES_PARAMS.spruce);
      const b = part(SPECIES_PARAMS.beech);
      factor = s * a.factor + (1 - s) * b.factor;
      stemCPerM3 = s * a.stemCPerM3 + (1 - s) * b.stemCPerM3;
      rootC = s * a.rootC + (1 - s) * b.rootC;
    } else {
      const r = part(SPECIES_PARAMS[config.species]);
      factor = r.factor;
      stemCPerM3 = r.stemCPerM3;
      rootC = r.rootC;
    }
    const stemShare = stemCPerM3 / factor;
    const rootShare = rootC / factor;
    return {carbonFactor: factor, stemCPerM3, stemShare, rootShare, branchShare: Math.max(0, 1 - stemShare - rootShare)};
  }

  function carbonPerStemVolume(config) {
    return carbonPartition(config).carbonFactor;
  }

  function nfiIncrementAtAge(age, bonitet, scale) {
    const sc = scale === undefined ? 1 : scale;
    const a = Math.max(0.5, numberOr(age, 1)) / Math.max(0.3, sc);
    const nodes = NFI_PROFILE_NODES;
    let inc = nodes[nodes.length - 1][1];
    for (let k = 0; k < nodes.length - 1; k += 1) {
      const [x0, y0] = nodes[k];
      const [x1, y1] = nodes[k + 1];
      if (x0 <= a && a <= x1) { inc = y0 + ((a - x0) * (y1 - y0)) / (x1 - x0); break; }
    }
    return inc * (bonitet / NFI_GOTALAND_MEAN_BONITET);
  }

  function inverseTable(table, y) {
    const xs = Object.keys(table).map(Number).sort((a, b) => a - b);
    if (y <= table[xs[0]]) return xs[0];
    if (y >= table[xs[xs.length - 1]]) return xs[xs.length - 1];
    for (let k = 0; k < xs.length - 1; k += 1) {
      const lo = xs[k];
      const hi = xs[k + 1];
      if (table[lo] <= y && y <= table[hi]) return lo + ((y - table[lo]) * (hi - lo)) / (table[hi] - table[lo]);
    }
    return xs[xs.length - 1];
  }

  function siteIndex(config) {
    const sp = config.species;
    if (sp === 'beech' || sp === 'oak') return null;
    const tableSp = sp === 'pine' ? 'pine' : 'spruce';
    if (config.productivityMethod === 'bonitet') {
      const bon = numberOr(config.productivityValue, 0);
      let t = H100_TABLES.spruce;
      if (tableSp === 'pine') t = config.pineSiteClass === 'weak' ? H100_TABLES.pineWeak : H100_TABLES.pineNormal;
      return inverseTable(t, bon);
    }
    return numberOr(config.productivityValue, 24);
  }

  function timeScale(config, region) {
    const si = siteIndex(config);
    if (si === null) return 1;
    return interpolateTable(region === 'north' ? LAF_NORTH : LAF_SOUTH, si) / LAF_REFERENCE;
  }

  function scaledRotation(config, region) {
    const p = SPECIES_PARAMS[config.species];
    if (siteIndex(config) === null) return p.rotation;
    return Math.round((p.rotation * timeScale(config, region) * LAF_REFERENCE) / LAF_ROTATION_BASE);
  }

  function mortalityRateAtAge(age, p, mode, scale) {
    const sc = scale === undefined ? 1 : scale;
    const ageFactor = Math.min(1, Math.max(0, age) / Math.max(1, p.matureAge * sc));
    if (mode === 'managed') return p.mortalityBase;
    if (mode === 'continuous') return p.mortalityBase + 0.5 * p.mortalityOldAdd * ageFactor;
    return p.mortalityBase + p.mortalityOldAdd * ageFactor;
  }

  function liveCarbonAtAge(age, config, mode) {
    const boundedAge = Math.round(clamp(numberOr(age, 0), 0, 400));
    const {p, bonitet} = curveParams(config);
    const carbonFactor = carbonPerStemVolume(config);
    let stock = 0;
    for (let standAge = 1; standAge <= boundedAge; standAge += 1) {
      stock = Math.max(0, stock + nfiIncrementAtAge(standAge, bonitet) * carbonFactor
        - stock * mortalityRateAtAge(standAge - 1, p, mode));
    }
    return stock;
  }

  function thinningAges(baseRotation, count) {
    const fractions = {0: [], 1: [0.5], 2: [0.4, 0.6], 3: [0.3, 0.45, 0.6]}[count] || [];
    return fractions.map((f) => Math.max(1, Math.round(f * baseRotation)));
  }

  // Skattat år-0-lager för befintlig skog: brukat bestånd med gallringar men utan slutavverkning.
  function estimateInitialLiveC(config, startAge, params) {
    const {p, bonitet} = curveParams(config);
    const sc = timeScale(config, params.region);
    const cf = carbonPerStemVolume(config);
    const thinAges = thinningAges(scaledRotation(config, params.region), params.thinningCount);
    let stock = 0;
    for (let age = 0; age < Math.round(startAge); age += 1) {
      if (thinAges.includes(age)) stock *= (1 - params.thinningShare);
      stock = Math.max(0, stock - stock * mortalityRateAtAge(age, p, 'managed', sc) + nfiIncrementAtAge(age + 1, bonitet, sc) * cf);
    }
    return stock;
  }

  function substitutionFactors(params, calendarYear) {
    if (params.substitutionSet === 'custom') {
      return {sawnwood: params.customDfSawnwood, paper: params.customDfPaper, energy: params.customDfEnergy,
        eolSawnwood: params.customDfEnergy, eolPaper: params.customDfEnergy};
    }
    const set = SUBSTITUTION_SETS[params.substitutionSet] || SUBSTITUTION_SETS.none;
    const t = clamp((calendarYear - 2020) / 30, 0, 1);
    const lerp = (pair) => pair[0] + (pair[1] - pair[0]) * t;
    return {sawnwood: lerp(set.sawnwood), paper: lerp(set.paper), energy: lerp(set.energy),
      eolSawnwood: lerp(set.eolSawnwood), eolPaper: lerp(set.eolPaper)};
  }

  function landFactorKey(i) {
    if (i.soilType === 'organic') return 'any|organic|notApplicable';
    if (i.currentLandUse === 'sealed') return `sealed|mineral|${i.restorationScenario}`;
    return `${i.currentLandUse}|mineral|notApplicable`;
  }

  function annualFactor(year, f1, f2, f3, longTerm) {
    if (year <= 0) return 0;
    if (year <= 20) return f1;
    if (year <= 100) return f2;
    return longTerm ? f3 : 0;
  }

  const SERIES_KEYS = ['live', 'deadwood', 'humus', 'soc', 'hwpSawn', 'hwpPaper', 'substCum', 'substAnnual',
    'mortality', 'residue', 'litter', 'harvestStemC', 'harvestTotalC', 'harvestM3', 'energyC', 'sawnIn', 'paperIn', 'structural', 'structIn',
    'rh', 'stormC', 'pLit', 'pFine', 'pCoarse', 'pHum'];

  // Simulerar ett bestånd med en ren skötselmetod och ett konkret trädslag, år för år.
  // firstActionYear skjuter upp första slutavverkning/blädning (landskapsläge).
  function runForest(opts) {
    const {scenario, config, startAge, initialLiveC, years, params, factors, applyLandUseFactors, includeSoil,
      initialSoc, initialDom, startYear} = opts;
    const firstActionYear = opts.firstActionYear || 1;
    const structuralShare = opts.structuralShare || 0;
    const kStruct = Math.LN2 / params.structuralHalfLife;
    const {p, bonitet} = curveParams(config);
    const sc = timeScale(config, params.region);
    const part = carbonPartition(config);
    const cf = part.carbonFactor;
    const isRotation = CLEARCUT_SCENARIOS.includes(scenario);
    const baseRotation = scaledRotation(config, params.region);
    const rotation = scenario === 'extended' ? baseRotation + params.extensionYears : baseRotation;
    const thinAges = isRotation ? thinningAges(baseRotation, params.thinningCount) : [];
    const firstCutAge = Math.max(1, Math.round(params.ccfFirstCutFraction * baseRotation));
    const structuralAge = params.ccfStructuralAge * sc;
    const mortalityMode = scenario === 'natural' ? 'natural' : (scenario === 'continuous' ? 'continuous' : 'managed');
    const longTerm = scenario === 'natural' || scenario === 'continuous';
    const grot = scenario === 'intensive' ? params.intensiveGrotShare : params.grotShare;
    const kSawn = Math.LN2 / params.hwpHalfLifeSawnwood;
    const kPaper = Math.LN2 / params.hwpHalfLifePaper;
    const targetScale = Math.pow(bonitet / NFI_GOTALAND_MEAN_BONITET, CCF_TARGET_EXPONENT);
    const upperC = params.ccfUpperStock * cf * targetScale;
    const lowerC = params.ccfLowerStock * cf * targetScale;
    const plantedMult = (1 + params.breedingGain) * (scenario === 'intensive' ? 1 + params.intensiveGrowthBoost : 1);
    const rootCoarse = part.rootShare * SOIL.coarseRootShare;
    const rootFine = part.rootShare - rootCoarse;
    const fineFrac = part.branchShare + rootFine;
    const coarseFracMort = part.stemShare + rootCoarse;
    const stormMax = (DISTURBANCE_LEVELS[params.disturbanceLevel] || 0) * (DISTURBANCE_SPECIES[config.species] ?? 0.5);
    const salvage = scenario === 'natural' ? 0 : params.salvageShare;
    const litterMax = (SOIL.litterMax * bonitet) / NFI_GOTALAND_MEAN_BONITET;

    const out = {};
    SERIES_KEYS.forEach((k) => { out[k] = new Array(years + 1).fill(0); });
    out.age = new Array(years + 1).fill(0);
    out.event = new Array(years + 1).fill('');

    let live = initialLiveC > 0 ? initialLiveC : (startAge > 0 ? estimateInitialLiveC(config, startAge, params) : 0);
    let age = Math.round(startAge);
    const d0 = opts.initialDomPools;
    let lit = d0 ? d0.litter : initialDom * DOM_SPLIT.litter;
    let fine = d0 ? d0.fine : initialDom * DOM_SPLIT.fine;
    let coarse = d0 ? d0.coarse : initialDom * DOM_SPLIT.coarse;
    let hum = d0 ? d0.humus : initialDom * DOM_SPLIT.humus;
    if (!includeSoil) { lit = 0; fine = 0; coarse = 0; hum = 0; }
    let soc = includeSoil ? initialSoc : 0;
    let hwpSawn = 0;
    let hwpPaper = 0;
    let structural = 0;
    let substCum = 0;
    let planted = Math.round(startAge) === 0 && !(initialLiveC > 0);
    let converted = false;
    let refStock = 0;
    let sinceCut = 0;
    let sinceThin = 99;
    let humusLossPerYear = 0;
    let humusLossYears = 0;

    out.live[0] = live;
    out.age[0] = age;
    out.deadwood[0] = fine + coarse;
    out.humus[0] = lit + hum;
    out.soc[0] = soc;
    out.pLit[0] = lit; out.pFine[0] = fine; out.pCoarse[0] = coarse; out.pHum[0] = hum;

    for (let y = 1; y <= years; y += 1) {
      let event = '';
      let removed = 0;
      let mix = null;
      let resFine = 0;
      let resCoarse = 0;
      let grotC = 0;
      const allowed = y >= firstActionYear;

      if (isRotation && age >= rotation && live > 0 && allowed) {
        event = 'Slutavverkning';
        removed = live;
        mix = 'final';
        const branches = live * part.branchShare;
        grotC = branches * grot;
        resFine = branches - grotC + live * rootFine;
        resCoarse = live * rootCoarse;
        live = 0;
        age = 0;
        planted = true;
        if (includeSoil && params.clearcutHumusLoss > 0) {
          humusLossPerYear = (hum * params.clearcutHumusLoss) / 10;
          humusLossYears = 10;
        }
      } else if (isRotation && thinAges.includes(age) && live > 0 && params.thinningShare > 0) {
        event = 'Gallring';
        removed = live * params.thinningShare;
        mix = 'thinning';
        resFine = removed * fineFrac;
        resCoarse = removed * rootCoarse;
        live -= removed;
        sinceThin = 0;
      } else if (scenario === 'continuous' && live > 0) {
        const canStart = age >= firstCutAge && allowed;
        const trigger = params.ccfMethod === 'target'
          ? live >= upperC && (converted || canStart)
          : (!converted && canStart) || (converted && sinceCut >= params.ccfInterval);
        if (trigger) {
          event = converted ? 'Blädning' : 'Första blädning';
          if (!converted) {
            converted = true;
            refStock = params.ccfMethod === 'target' ? upperC : live;
          }
          removed = params.ccfMethod === 'target' ? Math.max(0, live - lowerC) : live * params.ccfRemoval;
          mix = 'ccf';
          resFine = removed * fineFrac;
          resCoarse = removed * rootCoarse;
          live -= removed;
          sinceCut = 0;
          sinceThin = 0;
        }
      }

      const liveStart = live;
      let increment;
      let mortRate;
      let effAge;
      if (scenario === 'continuous' && converted) {
        const modifier = Math.sqrt(clamp(refStock > 0 ? live / refStock : 1, 0.3, 1));
        increment = nfiIncrementAtAge(structuralAge, bonitet, sc) * cf * params.ccfGrowthFactor * modifier;
        mortRate = mortalityRateAtAge(structuralAge, p, 'continuous', sc);
        sinceCut += 1;
        effAge = structuralAge;
      } else {
        const mult = planted ? plantedMult : 1;
        increment = nfiIncrementAtAge(age + 1, bonitet, sc) * cf * mult;
        mortRate = mortalityRateAtAge(age, p, mortalityMode, sc);
        effAge = age;
      }
      const mortality = liveStart * mortRate;
      live = Math.max(0, liveStart + increment - mortality);
      age += 1;
      sinceThin += 1;

      let storm = 0;
      let stormStemSalvaged = 0;
      if (stormMax > 0 && live > 0) {
        const ageFactor = clamp((effAge / sc - 40) / 60, 0, 1);
        const rate = stormMax * ageFactor * (sinceThin <= 10 ? 1.5 : 1);
        storm = live * rate;
        live -= storm;
        stormStemSalvaged = storm * part.stemShare * salvage;
      }

      const stemC = removed * part.stemShare;
      let sawnShare = params.productSawnFinal;
      let paperShare = params.productPaperFinal;
      if (mix === 'thinning') { sawnShare = params.productSawnThinning; paperShare = params.productPaperThinning; }
      else if (mix === 'ccf') { sawnShare = params.productSawnCcf; paperShare = params.productPaperCcf; }
      const sawnTotal = stemC * sawnShare;
      const structIn = structuralShare > 0 ? Math.min(stemC * structuralShare, sawnTotal) : 0;
      const carve = params.includeStructural;
      const sawnIn = carve ? sawnTotal - structIn : sawnTotal;
      const paperIn = stemC * paperShare + stormStemSalvaged * params.productPaperThinning;
      const energyIn = stemC * Math.max(0, 1 - sawnShare - paperShare) + grotC
        + stormStemSalvaged * Math.max(0, 1 - params.productPaperThinning);
      const discardSawn = hwpSawn * kSawn;
      const discardPaper = hwpPaper * kPaper;
      const discardStruct = structural * kStruct;
      hwpSawn = hwpSawn - discardSawn + sawnIn;
      hwpPaper = hwpPaper - discardPaper + paperIn;
      structural = structural - discardStruct + structIn;
      const df = substitutionFactors(params, startYear + y);
      const substAnnual = sawnTotal * df.sawnwood + paperIn * df.paper + energyIn * df.energy
        + (discardSawn + (carve ? discardStruct : 0)) * df.eolSawnwood + discardPaper * df.eolPaper;
      substCum += substAnnual;

      let litterIn = 0;
      let rh = 0;
      if (includeSoil) {
        const stormDead = storm - stormStemSalvaged;
        const toFine = mortality * fineFrac + resFine + storm * fineFrac;
        const toCoarse = mortality * coarseFracMort + resCoarse + Math.max(0, stormDead - storm * fineFrac);
        litterIn = litterMax * (1 - Math.exp(-liveStart / SOIL.litterHalfLive)) + SOIL.groundLitter
          + SOIL.groundOpen * Math.exp(-liveStart / SOIL.openHalfLive);
        const dLit = lit * SOIL.kLitter;
        const dFine = fine * SOIL.kFine;
        const dCoarse = coarse * p.deadwoodDecay;
        lit += litterIn - dLit;
        fine += toFine - dFine;
        coarse += toCoarse - dCoarse;
        const humIn = dLit * SOIL.hLitter + dFine * SOIL.hFine + dCoarse * SOIL.hCoarse;
        const domF = applyLandUseFactors ? annualFactor(y, factors.dom1to20, factors.dom21to100, factors.dom101plus, longTerm) : 0;
        const socF = applyLandUseFactors ? annualFactor(y, factors.soc1to20, factors.soc21to100, factors.soc101plus, longTerm) : 0;
        let humusLoss = 0;
        if (humusLossYears > 0) {
          humusLoss = humusLossPerYear;
          humusLossYears -= 1;
        }
        const dHum = hum * SOIL.kHumus;
        const socIn = dHum * SOIL.sHumus;
        const socOut = (soc - initialSoc) * SOIL.kSoc;
        hum = Math.max(0, hum + humIn + domF - dHum - humusLoss);
        soc = Math.max(0, soc + socF + socIn - socOut);
        rh = (dLit + dFine + dCoarse - humIn) + (dHum - socIn) + socOut + humusLoss;
      }

      out.live[y] = live;
      out.age[y] = age;
      out.event[y] = event;
      out.deadwood[y] = fine + coarse;
      out.humus[y] = lit + hum;
      out.soc[y] = soc;
      out.hwpSawn[y] = hwpSawn;
      out.hwpPaper[y] = hwpPaper;
      out.substCum[y] = substCum;
      out.substAnnual[y] = substAnnual;
      out.mortality[y] = mortality;
      out.residue[y] = resFine + resCoarse;
      out.litter[y] = litterIn;
      out.harvestStemC[y] = stemC + stormStemSalvaged;
      out.harvestTotalC[y] = removed + storm;
      out.harvestM3[y] = (stemC + stormStemSalvaged) / part.stemCPerM3;
      out.energyC[y] = energyIn;
      out.sawnIn[y] = sawnTotal;
      out.paperIn[y] = stemC * paperShare;
      out.structural[y] = structural;
      out.structIn[y] = structIn;
      out.rh[y] = rh;
      out.stormC[y] = storm;
      out.pLit[y] = lit; out.pFine[y] = fine; out.pCoarse[y] = coarse; out.pHum[y] = hum;
    }
    out.rotation = isRotation ? rotation : null;
    return out;
  }

  function combineRuns(weighted) {
    const active = weighted.filter((w) => w.weight > 0);
    const n = active[0].run.live.length;
    const out = {};
    SERIES_KEYS.forEach((k) => {
      const acc = new Array(n).fill(0);
      active.forEach(({weight, run}) => {
        const arr = run[k];
        for (let t = 0; t < n; t += 1) acc[t] += weight * arr[t];
      });
      out[k] = acc;
    });
    let dominant = active[0];
    active.forEach((a) => { if (a.weight > dominant.weight) dominant = a; });
    out.age = dominant.run.age.slice();
    out.event = new Array(n).fill('');
    for (let t = 0; t < n; t += 1) {
      const seen = [];
      active.forEach((a) => { const e = a.run.event[t]; if (e && !seen.includes(e)) seen.push(e); });
      out.event[t] = seen.join(', ');
    }
    out.rotation = dominant.run.rotation;
    return out;
  }

  function mixWeights(i) {
    const raw = {
      natural: i.mixNatural, conventional: i.mixConventional, extended: i.mixExtended,
      continuous: i.mixContinuous, intensive: i.mixIntensive,
    };
    const sum = Object.values(raw).reduce((a, b) => a + b, 0);
    if (sum <= 0) return {natural: 0, conventional: 1, extended: 0, continuous: 0, intensive: 0};
    const out = {};
    Object.keys(raw).forEach((k) => { out[k] = raw[k] / sum; });
    return out;
  }

  // Åldersfördelning i 5-åriga delklasser: [[ålder, arealandel]], summa 1.
  function landscapeUnits(i) {
    let shares = AGE_CLASS_KEYS.map((k) => i[k]);
    let total = shares.reduce((a, b) => a + b, 0);
    if (total <= 0) { shares = AGE_CLASS_KEYS.map(() => 1); total = AGE_CLASS_KEYS.length; }
    const units = [];
    shares.forEach((share, idx) => {
      for (let sub = 0; sub < 4; sub += 1) units.push([idx * 20 + sub * 5 + 2, share / total / 4]);
    });
    return units;
  }

  function speciesConfigs(config) {
    if (config.species !== 'conifers') return [[1, config]];
    const s = clamp(numberOr(config.mixedSpruceShare, 0.5), 0, 1);
    return [[s, Object.assign({}, config, {species: 'spruce'})], [1 - s, Object.assign({}, config, {species: 'pine'})]];
  }

  // Kör och cachar beståndssimuleringar inom en beräkning.
  function Runner(base, i, initialDomBySpecies) {
    this.base = base;
    this.i = i;
    this.dom = initialDomBySpecies || {};
    this.cache = new Map();
  }
  Runner.prototype.unit = function (scenario, config, startAge, initialLive, firstActionYear) {
    const fy = firstActionYear || 1;
    const key = [scenario, config.species, config.productivityMethod, config.productivityValue, config.pineSiteClass,
      startAge, initialLive, fy].join('|');
    if (!this.cache.has(key)) {
      this.cache.set(key, runForest(Object.assign({}, this.base, {
        scenario, config, startAge, initialLiveC: initialLive, firstActionYear: fy,
        initialDomPools: this.dom[config.species] || null,
      })));
    }
    return this.cache.get(key);
  };
  Runner.prototype.withRetention = function (scenario, config, startAge, initialLive, landscape) {
    const i = this.i;
    const rot = scaledRotation(config, i.region);
    let base;
    if (landscape && i.landscapeBacklogYears > 0 && scenario !== 'natural') {
      let limit = rot + (scenario === 'extended' ? i.extensionYears : 0);
      if (scenario === 'continuous') limit = Math.max(1, Math.round(i.ccfFirstCutFraction * rot));
      if (startAge >= limit) {
        const parts = [0, 1, 2, 3].map((q) => ({weight: 0.25,
          run: this.unit(scenario, config, startAge, initialLive, 1 + Math.round((i.landscapeBacklogYears * q) / 4))}));
        base = combineRuns(parts);
      } else {
        base = this.unit(scenario, config, startAge, initialLive);
      }
    } else {
      base = this.unit(scenario, config, startAge, initialLive);
    }
    if (!CLEARCUT_SCENARIOS.includes(scenario) || i.retentionShare <= 0) return base;
    return combineRuns([
      {weight: 1 - i.retentionShare, run: base},
      {weight: i.retentionShare, run: this.unit('natural', config, startAge, initialLive)},
    ]);
  };
  Runner.prototype.management = function (scenario, config, startAge, initialLive, landscape) {
    const i = this.i;
    const weights = scenario === 'mix' ? mixWeights(i) : {[scenario]: 1};
    const parts = [];
    speciesConfigs(config).forEach(([sw, scfg]) => {
      if (!landscape) {
        PURE_SCENARIOS.forEach((s) => {
          const w = weights[s] || 0;
          if (w > 0) parts.push({weight: sw * w, run: this.withRetention(s, scfg, startAge, initialLive, false)});
        });
        return;
      }
      const units = landscapeUnits(i);
      const wn = weights.natural || 0;
      const protect = i.landscapeProtectOldest && wn > 0 && wn < 1;
      const protFrac = {};
      if (protect) {
        let remaining = wn;
        for (let idx = units.length - 1; idx >= 0; idx -= 1) {
          const [age, uw] = units[idx];
          const take = Math.min(uw, remaining);
          protFrac[age] = uw > 0 ? take / uw : 0;
          remaining -= take;
        }
      }
      units.forEach(([age, uw]) => {
        const pf = protect ? (protFrac[age] || 0) : null;
        PURE_SCENARIOS.forEach((s) => {
          const w = weights[s] || 0;
          if (w <= 0) return;
          const frac = protect ? (s === 'natural' ? pf : ((1 - pf) * w) / (1 - wn)) : w;
          if (frac > 0) parts.push({weight: sw * uw * frac, run: this.withRetention(s, scfg, age, 0, true)});
        });
      });
    });
    return combineRuns(parts);
  };

  function staticReference(i, factors, initialLive, dom0) {
    const n = i.analysisYears + 1;
    const out = {};
    SERIES_KEYS.forEach((k) => { out[k] = new Array(n).fill(0); });
    out.age = new Array(n).fill(0);
    out.event = new Array(n).fill('');
    const startAge = i.projectType === 'existing' ? i.referenceStartAge : 0;
    const [dw0, hu0] = dom0 || [i.initialDom * 0.2, i.initialDom * 0.8];
    const domInit = dw0 + hu0;
    const dwShare = domInit > 0 ? dw0 / domInit : 0.2;
    for (let y = 0; y < n; y += 1) {
      out.live[y] = initialLive;
      out.age[y] = startAge + y;
      if (!i.includeSoilDom) continue;
      let domTotal;
      let socStock;
      if (i.referenceScenario === 'noChange') {
        domTotal = domInit;
        socStock = i.initialSoc0to50;
      } else if (i.referenceSoilMethod === 'gisDirect') {
        domTotal = domInit + y * i.gisRefDomChange;
        socStock = i.initialSoc0to50 + y * i.gisRefSocChange;
      } else {
        domTotal = domInit + y * factors.refDom;
        socStock = i.initialSoc0to50 + y * factors.refSoc;
      }
      domTotal = Math.max(0, domTotal);
      out.deadwood[y] = domTotal * dwShare;
      out.humus[y] = domTotal * (1 - dwShare);
      out.soc[y] = Math.max(0, socStock);
    }
    out.rotation = null;
    return out;
  }

  // Avklingande historiskt produktlager inkl. substitution när produkterna kasseras.
  function addHistoricHwp(run, poolSawn, poolPaper, i) {
    const kSawn = Math.LN2 / i.hwpHalfLifeSawnwood;
    const kPaper = Math.LN2 / i.hwpHalfLifePaper;
    let cum = 0;
    for (let t = 0; t < run.live.length; t += 1) {
      if (t > 0) {
        const df = substitutionFactors(i, i.startYear + t);
        const extra = poolSawn * Math.pow(1 - kSawn, t - 1) * kSawn * df.eolSawnwood
          + poolPaper * Math.pow(1 - kPaper, t - 1) * kPaper * df.eolPaper;
        cum += extra;
        run.substAnnual[t] += extra;
      }
      run.substCum[t] += cum;
      run.hwpSawn[t] += poolSawn * Math.pow(1 - kSawn, t);
      run.hwpPaper[t] += poolPaper * Math.pow(1 - kPaper, t);
    }
  }

  // Död ved och förna/humus i jämvikt med historiskt trakthyggesbruk (landskapsläge), per trädslag.
  let spinMemo = {key: null, value: null};
  function spinUpDom(i, projectConfig, common) {
    const memoKey = JSON.stringify(Object.assign({}, i, {projectForestScenario: null, systemBoundary: null,
      referenceScenario: null, referenceForestScenario: null, projectName: null}));
    if (spinMemo.key === memoKey) return spinMemo.value;
    const value = spinUpDomRaw(i, projectConfig, common);
    spinMemo = {key: memoKey, value};
    return value;
  }
  function spinUpDomRaw(i, projectConfig, common) {
    const spin = Object.assign({}, i, {analysisYears: 300, includeSoilDom: true});
    const base = Object.assign({}, common, {years: 300, params: spin, includeSoil: true, applyLandUseFactors: false});
    const out = {};
    speciesConfigs(projectConfig).forEach(([, scfg]) => {
      const runner = new Runner(base, spin, null);
      const hist = runner.management('conventional', scfg, 0, 0, true);
      const rot = scaledRotation(scfg, i.region);
      const acc = {litter: 0, fine: 0, coarse: 0, humus: 0};
      let count = 0;
      for (let t = Math.max(0, 300 - 2 * rot); t <= 300; t += 1) {
        acc.litter += hist.pLit[t]; acc.fine += hist.pFine[t]; acc.coarse += hist.pCoarse[t]; acc.humus += hist.pHum[t]; count += 1;
      }
      out[scfg.species] = {litter: acc.litter / count, fine: acc.fine / count, coarse: acc.coarse / count, humus: acc.humus / count};
    });
    return out;
  }

  function boundaryStock(run, t, boundary, includeStruct) {
    const struct = includeStruct ? run.structural[t] : 0;
    return boundaryStockBase(run, t, boundary) + struct;
  }
  function boundaryStockBase(run, t, boundary) {
    const eco = run.live[t] + run.deadwood[t] + run.humus[t] + run.soc[t];
    if (boundary === 'ecosystem') return eco;
    const hwp = run.hwpSawn[t] + run.hwpPaper[t];
    if (boundary === 'hwp') return eco + hwp;
    return eco + hwp + run.substCum[t];
  }

  function parityYear(series) {
    // Första år varefter det kumulativa nettot förblir >= 0 resten av perioden.
    let candidate = null;
    for (let t = series.length - 1; t >= 0; t -= 1) {
      if (series[t] >= -1e-9) candidate = t;
      else break;
    }
    return candidate;
  }

  function simulate(rawInputs) {
    const i = normaliseInputs(rawInputs);
    const projectConfig = projectForestConfig(i);
    const refConfig = referenceForestConfig(i);
    const projectCurve = {bonitet: bonitetFromForestConfig(projectConfig)};
    const refCurve = {bonitet: bonitetFromForestConfig(refConfig)};
    const landKey = landFactorKey(i);
    const factors = LAND_FACTORS[landKey] || LAND_FACTORS['unknown|mineral|notApplicable'];
    const warnings = [];
    const params = i;
    const existing = i.projectType === 'existing';
    const landscape = i.projectType === 'landscape';

    if (i.currentLandUse === 'sealed' && i.restorationScenario === 'unspecified') {
      warnings.push('Hårdgjord mark utan specificerad återställning ger ett försiktigt markkolsantagande nära noll.');
    }
    if (i.soilType === 'organic') {
      warnings.push('Organisk jord/torv har mycket hög osäkerhet och kan ge stora långvariga utsläpp. Platsspecifik utredning krävs.');
      if (i.projectForestScenario === 'continuous' || i.projectForestScenario === 'mix') {
        warnings.push('Finska studier (Lehtonen m.fl. 2023; Korkiakoski m.fl. 2023) visar att kontinuitetsskogsbruk på näringsrik dikad torvmark kan minska markens utsläpp jämfört med kalhygge. Den effekten ingår inte i modellens torvfaktorer.');
      }
    }
    if (existing && i.initialLiveC <= 0) {
      warnings.push('Initial levande biomassa saknas för befintlig skog. År-0-lagret skattas från tillväxtkurvan för ett gallrat bestånd.');
    }
    if (i.referenceScenario === 'continuedLandUse' && i.currentLandUse === 'forest') {
      warnings.push('”Fortsatt nuvarande markanvändning” för skogsmark håller levande trädbiomassa konstant. Välj skogsbruk som referens för aktivt brukande.');
    }
    if (i.referenceSoilMethod === 'gisDirect' && i.referenceScenario !== 'conventionalForest') {
      warnings.push('GIS Change_SOC och Change_DOM behandlas som färdiga årliga nettoförändringar. Ingen extra processmodell läggs på referensens SOC/DOM.');
    }
    if (i.analysisYears > 200) {
      warnings.push('Resultat efter cirka 200 år är särskilt osäkra och bör tolkas som scenarier, inte prognoser.');
    }
    if (projectCurve.bonitet < 4 || projectCurve.bonitet > 12) {
      warnings.push('Vald bonitet ligger långt från Götalands medelbonitet 8,8 m³sk/ha,år. Skalning av Riksskogstaxeringens åldersprofil blir då extra osäker.');
    }
    if (i.systemBoundary === 'substitution') {
      warnings.push('Substitution ingår inte i den nationella växthusgasrapporteringen och är mycket osäker. Val av substitutionsnivå kan avgöra vilket scenario som ser bäst ut (Englund m.fl. 2025).');
    }
    if (i.projectForestScenario === 'continuous' && i.projectType === 'new') {
      warnings.push('Kontinuitetsskogsbruk på ny mark förutsätter att ett bestånd först etableras. Modellen låter beståndet växa som likåldrigt fram till första blädningen.');
    }
    const capCheck = (share, who) => {
      if (share <= 0) return;
      const caps = [i.productSawnFinal, i.productSawnCcf].concat(i.thinningCount > 0 ? [i.productSawnThinning] : []);
      const minCap = Math.min.apply(null, caps);
      if (share > minCap + 1e-9) {
        warnings.push(`Andelen stomvirke i ${who} (${Math.round(share * 100)} %) är större än andelen sågade trävaror för vissa avverkningstyper (minst ${Math.round(minCap * 100)} %). Stomvirket begränsas då till hela det sågade flödet för de avverkningarna.`);
      }
    };
    capCheck(i.structuralShareProject, 'projektet');
    if (i.referenceScenario === 'conventionalForest') capCheck(i.structuralShareReference, 'referensen');
    if ((i.structuralShareProject > 0 || i.structuralShareReference > 0) && i.includeStructural) {
      warnings.push('Inbyggt stomvirke ingår i nettoresultatet och redovisas separat. Lagringen i byggnader ingår i den nationella rapporteringen endast som en del av träprodukter och räknas inte som ett separat upptag.');
    } else if (i.structuralShareProject > 0 || i.structuralShareReference > 0) {
      warnings.push('Inbyggt stomvirke redovisas separat men ingår inte i nettoresultatet, som då beräknas precis som utan stomvirke.');
    }
    if (i.disturbanceLevel !== 'off') {
      warnings.push('Stormrisk är en förenklad känslighetsanalys: en förväntad årlig andel stormfälld biomassa som ökar med ålder och strax efter gallring. Enskilda stormar och granbarkborreutbrott modelleras inte.');
    }
    if (landscape && i.currentLandUse !== 'forest') {
      warnings.push('Landskapsläget beskriver befintlig skog. Välj Skogsmark som nuvarande markanvändning för rimliga mark- och referensantaganden.');
    }

    const common = {
      years: i.analysisYears,
      params,
      factors,
      includeSoil: i.includeSoilDom,
      initialSoc: i.initialSoc0to50,
      initialDom: i.initialDom,
      startYear: i.startYear,
    };

    const startP = existing ? i.projectStartAge : 0;
    const startR = existing ? i.referenceStartAge : 0;
    const initLive = existing ? i.initialLiveC : 0;
    const useEq = i.includeSoilDom && (landscape || (existing && i.currentLandUse === 'forest' && i.domEquilibrium));
    const dom0 = useEq ? spinUpDom(i, projectConfig, common) : null;
    const prun = new Runner(Object.assign({}, common, {applyLandUseFactors: true, structuralShare: i.structuralShareProject}), i, dom0);
    const project = prun.management(i.projectForestScenario, projectConfig, startP, initLive, landscape);
    const rrun = new Runner(Object.assign({}, common, {applyLandUseFactors: false, structuralShare: i.structuralShareReference}), i, dom0);
    let reference;
    if (i.referenceScenario === 'conventionalForest') {
      reference = rrun.management(i.referenceForestScenario, refConfig, startR, initLive, landscape);
    } else {
      reference = staticReference(i, factors,
        landscape ? project.live[0] : (existing ? i.initialLiveC : 0),
        useEq ? [project.deadwood[0], project.humus[0]] : null);
    }
    if (landscape) {
      // Historiskt produktlager i jämvikt med trakthyggesbruk; samma i projekt och referens.
      const hist = rrun.management('conventional', projectConfig, 0, 0, true);
      const n = Math.max(1, i.analysisYears);
      let sumSawn = 0;
      let sumPaper = 0;
      for (let t = 1; t < hist.sawnIn.length; t += 1) { sumSawn += hist.sawnIn[t]; sumPaper += hist.paperIn[t]; }
      const poolSawn = sumSawn / n / (Math.LN2 / i.hwpHalfLifeSawnwood);
      const poolPaper = sumPaper / n / (Math.LN2 / i.hwpHalfLifePaper);
      addHistoricHwp(project, poolSawn, poolPaper, i);
      addHistoricHwp(reference, poolSawn, poolPaper, i);
    }

    const rows = [];
    const boundary = i.systemBoundary;
    const inc = i.includeStructural;
    const p0 = {eco: boundaryStock(project, 0, 'ecosystem'), hwp: boundaryStock(project, 0, 'hwp'), sub: boundaryStock(project, 0, 'substitution')};
    const r0 = {eco: boundaryStock(reference, 0, 'ecosystem'), hwp: boundaryStock(reference, 0, 'hwp'), sub: boundaryStock(reference, 0, 'substitution')};
    const netSeries = {ecosystem: [], hwp: [], substitution: [], structural: []};

    for (let t = 0; t <= i.analysisYears; t += 1) {
      const pEco = boundaryStock(project, t, 'ecosystem');
      const rEco = boundaryStock(reference, t, 'ecosystem');
      const pSys = boundaryStock(project, t, boundary, inc);
      const rSys = boundaryStock(reference, t, boundary, inc);
      const pSysPrev = t > 0 ? boundaryStock(project, t - 1, boundary, inc) : pSys;
      const rSysPrev = t > 0 ? boundaryStock(reference, t - 1, boundary, inc) : rSys;
      const p0b = (boundary === 'ecosystem' ? p0.eco : (boundary === 'hwp' ? p0.hwp : p0.sub)) + (inc ? project.structural[0] : 0);
      const r0b = (boundary === 'ecosystem' ? r0.eco : (boundary === 'hwp' ? r0.hwp : r0.sub)) + (inc ? reference.structural[0] : 0);

      const grossAnnualC = pSys - pSysPrev;
      const referenceAnnualC = rSys - rSysPrev;
      const grossCumulativeC = pSys - p0b;
      const referenceCumulativeC = rSys - r0b;
      const netAnnualC = grossAnnualC - referenceAnnualC;
      const netCumulativeC = grossCumulativeC - referenceCumulativeC;

      netSeries.ecosystem.push(((pEco - p0.eco) - (rEco - r0.eco)) * CO2_PER_C);
      netSeries.hwp.push(((boundaryStock(project, t, 'hwp') - p0.hwp) - (boundaryStock(reference, t, 'hwp') - r0.hwp)) * CO2_PER_C);
      netSeries.substitution.push(((boundaryStock(project, t, 'substitution') - p0.sub) - (boundaryStock(reference, t, 'substitution') - r0.sub)) * CO2_PER_C);
      netSeries.structural.push(((project.structural[t] - project.structural[0]) - (reference.structural[t] - reference.structural[0])) * CO2_PER_C);

      rows.push({
        year: t,
        calendarYear: i.startYear + t,
        projectAge: project.age[t],
        projectEvent: project.event[t],
        projectHarvest: Boolean(project.event[t]),
        projectLiveC: project.live[t],
        projectMortalityC: project.mortality[t],
        projectHarvestResidueC: project.residue[t],
        projectDeadwoodC: project.deadwood[t],
        projectLitterInputC: project.litter[t],
        projectHumusC: project.humus[t],
        projectSocC: project.soc[t],
        projectEcosystemC: pEco,
        projectHwpC: project.hwpSawn[t] + project.hwpPaper[t],
        projectHwpSawnC: project.hwpSawn[t],
        projectHwpPaperC: project.hwpPaper[t],
        projectSubstAnnualC: project.substAnnual[t],
        projectSubstCumC: project.substCum[t],
        projectHarvestStemC: project.harvestStemC[t],
        projectHarvestTotalC: project.harvestTotalC[t],
        projectSawnInC: project.sawnIn[t],
        projectHarvestM3: project.harvestM3[t],
        projectEnergyC: project.energyC[t],
        projectRhC: project.rh[t],
        projectStormC: project.stormC[t],
        referenceRhC: reference.rh[t],
        projectStructuralC: project.structural[t],
        projectStructuralInC: project.structIn[t],
        projectSystemC: pSys,
        grossAnnualC,
        grossCumulativeC,
        grossAnnualCo2: grossAnnualC * CO2_PER_C,
        grossCumulativeCo2: grossCumulativeC * CO2_PER_C,

        referenceAge: reference.age[t],
        referenceEvent: reference.event[t],
        referenceHarvest: Boolean(reference.event[t]),
        referenceLiveC: reference.live[t],
        referenceMortalityC: reference.mortality[t],
        referenceHarvestResidueC: reference.residue[t],
        referenceDeadwoodC: reference.deadwood[t],
        referenceLitterInputC: reference.litter[t],
        referenceHumusC: reference.humus[t],
        referenceSocC: reference.soc[t],
        referenceEcosystemC: rEco,
        referenceHwpC: reference.hwpSawn[t] + reference.hwpPaper[t],
        referenceSubstCumC: reference.substCum[t],
        referenceHarvestStemC: reference.harvestStemC[t],
        referenceHarvestTotalC: reference.harvestTotalC[t],
        referenceSawnInC: reference.sawnIn[t],
        referenceHarvestM3: reference.harvestM3[t],
        referenceStructuralC: reference.structural[t],
        referenceStructuralInC: reference.structIn[t],
        referenceSystemC: rSys,
        referenceAnnualC,
        referenceCumulativeC,
        referenceAnnualCo2: referenceAnnualC * CO2_PER_C,
        referenceCumulativeCo2: referenceCumulativeC * CO2_PER_C,

        netAnnualC,
        netCumulativeC,
        netAnnualCo2: netAnnualC * CO2_PER_C,
        netCumulativeCo2: netCumulativeC * CO2_PER_C,
        netCumulativeEcosystemCo2: netSeries.ecosystem[t],
        netCumulativeHwpCo2: netSeries.hwp[t],
        netCumulativeSubstitutionCo2: netSeries.substitution[t],
        netCumulativeStructuralCo2: netSeries.structural[t],
        projectStockCo2: pSys * CO2_PER_C,
        referenceStockCo2: rSys * CO2_PER_C,
      });
    }

    const last = rows[rows.length - 1];
    const years = Math.max(1, i.analysisYears);
    const sum = (key) => rows.reduce((acc, r) => acc + r[key], 0);
    const summary = {
      modelVersion: MODEL_VERSION,
      systemBoundary: boundary,
      systemBoundaryLabel: BOUNDARY_LABELS[boundary],
      projectScenarioLabel: SCENARIO_LABELS[i.projectForestScenario],
      referenceScenarioLabel: i.referenceScenario === 'conventionalForest' ? SCENARIO_LABELS[i.referenceForestScenario] : null,
      projectBonitet: projectCurve.bonitet,
      referenceBonitet: refCurve.bonitet,
      projectSpeciesLabel: SPECIES_LABELS[projectConfig.species],
      referenceSpeciesLabel: SPECIES_LABELS[refConfig.species],
      landFactorKey: landKey,
      soilUncertainty: factors.uncertainty,
      grossCumulativeCo2PerHa: last.grossCumulativeCo2,
      referenceCumulativeCo2PerHa: last.referenceCumulativeCo2,
      netCumulativeCo2PerHa: last.netCumulativeCo2,
      netByBoundaryCo2PerHa: {
        ecosystem: last.netCumulativeEcosystemCo2,
        hwp: last.netCumulativeHwpCo2,
        substitution: last.netCumulativeSubstitutionCo2,
      },
      grossAverageCo2PerHaYear: last.grossCumulativeCo2 / years,
      netAverageCo2PerHaYear: last.netCumulativeCo2 / years,
      grossTotalCo2: last.grossCumulativeCo2 * i.areaHa,
      netTotalCo2: last.netCumulativeCo2 * i.areaHa,
      projectStockCo2PerHa: last.projectStockCo2,
      referenceStockCo2PerHa: last.referenceStockCo2,
      projectMeanHarvestM3: sum('projectHarvestM3') / years,
      referenceMeanHarvestM3: sum('referenceHarvestM3') / years,
      carbonParityYear: parityYear(rows.map((r) => r.netCumulativeCo2)),
      structural: {
        active: i.structuralShareProject > 0 || i.structuralShareReference > 0,
        included: inc,
        shareProject: i.structuralShareProject,
        shareReference: i.structuralShareReference,
        projectStockCo2PerHa: last.projectStructuralC * CO2_PER_C,
        referenceStockCo2PerHa: last.referenceStructuralC * CO2_PER_C,
        netCo2PerHa: last.netCumulativeStructuralCo2,
        projectMeanInflowCo2PerHaYear: (sum('projectStructuralInC') / years) * CO2_PER_C,
        referenceMeanInflowCo2PerHaYear: (sum('referenceStructuralInC') / years) * CO2_PER_C,
      },
      projectRotation: project.rotation,
      referenceRotation: reference.rotation,
      mixWeights: i.projectForestScenario === 'mix' ? mixWeights(i) : null,
      calibration: 'Riksskogstaxeringen Skogsdata 2025 (grundtillväxt); Stål m.fl. 2024 (CCF-faktor 1,06)',
    };

    return {inputs: i, rows, summary, warnings};
  }

  // Kör alla skötselmetoder med samma ståndort, referens och parametrar.
  function compareScenarios(rawInputs, scenarios) {
    const list = scenarios || COMPARISON_SCENARIOS;
    return list.map((scenario) => {
      const result = simulate(Object.assign({}, rawInputs, {projectForestScenario: scenario}));
      const pick = (year) => {
        const row = result.rows[Math.min(year, result.rows.length - 1)];
        return row ? row.netCumulativeCo2 : null;
      };
      return {
        scenario,
        label: SCENARIO_LABELS[scenario],
        series: result.rows.map((r) => r.netCumulativeCo2),
        netAt50: result.inputs.analysisYears >= 50 ? pick(50) : null,
        netAt100: result.inputs.analysisYears >= 100 ? pick(100) : null,
        netAtEnd: result.summary.netCumulativeCo2PerHa,
        meanHarvestM3: result.summary.projectMeanHarvestM3,
        parityYear: result.summary.carbonParityYear,
        endStockCo2: result.summary.projectStockCo2PerHa,
        structuralNetAtEnd: result.summary.structural.netCo2PerHa,
      };
    });
  }

  return {
    MODEL_VERSION,
    CO2_PER_C,
    DEFAULT_INPUTS,
    SPECIES_LABELS,
    SCENARIO_LABELS,
    PURE_SCENARIOS,
    COMPARISON_SCENARIOS,
    BOUNDARY_LABELS,
    SUBSTITUTION_SETS,
    H100_TABLES,
    SPECIES_PARAMS,
    NFI_GOTALAND_MEAN_BONITET,
    NFI_GOTALAND_INCREMENT_BY_AGE,
    LAND_FACTORS,
    normaliseInputs,
    bonitetFromForestConfig,
    projectForestConfig,
    referenceForestConfig,
    carbonPartition,
    carbonPerStemVolume,
    nfiIncrementAtAge,
    mortalityRateAtAge,
    liveCarbonAtAge,
    estimateInitialLiveC,
    substitutionFactors,
    runForest,
    siteIndex,
    timeScale,
    scaledRotation,
    SOIL,
    landscapeUnits,
    AGE_CLASS_KEYS,
    simulate,
    compareScenarios,
  };
});

  
"""

_JS_STUDIES = r"""

/* Publicerade tecken är observationer i tabellen, aldrig indata till simuleringen. */
(function (root, factory) {
  const api = factory(root.ForestModel);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.ForestStudies = api;
})(typeof self !== 'undefined' ? self : this, function (Model) {
  'use strict';
  if (!Model) throw new Error('Skogskolmodellens kärna saknas.');
  const BASE = {
    projectType:'landscape', currentLandUse:'forest', soilType:'mineral', region:'south',
    projectSpecies:'spruce', projectProductivityMethod:'bonitet', projectProductivityValue:8.8,
    referenceSpeciesMode:'same', referenceProductivityMode:'same', referenceScenario:'conventionalForest',
    referenceForestScenario:'conventional', projectForestScenario:'continuous', analysisYears:100,
    includeSoilDom:true, domEquilibrium:true, initialSoc0to50:80, initialDom:10,
    breedingGain:0, disturbanceLevel:'off', systemBoundary:'ecosystem', includeStructural:false,
    structuralShareProject:0, structuralShareReference:0,
    thinningCount:2, thinningShare:.25, grotShare:0, retentionShare:0,
    ccfMethod:'interval', ccfRemoval:.3, ccfInterval:20, ccfGrowthFactor:.9,
  };
  const CASES = [
    {id:'nilsen13', name:'Nilsen & Strand (2013)', href:'https://doi.org/10.14214/sf.1024',
      published:['−','n.d.','−','−'], note:'Norsk fältstudie: 81 år, endast ett bestånd per behandling. Illustrativt befintligt granbestånd, ej replikation av mätdata.',
      overrides:{projectType:'existing',projectStartAge:80,referenceStartAge:80,analysisYears:81,ccfRemoval:.4,ccfInterval:10,ccfGrowthFactor:.8,productSawnFinal:.4,productSawnCcf:.35}},
    {id:'pukkala14low', name:'Pukkala (2014), låg gallring', href:'https://doi.org/10.1016/j.forpol.2014.03.004',
      published:['+','−','+',''], note:'RF låg gallring utan biobränsle jämfört med CCF. Vald gallringsstyrka är en proxy: modellen kan inte skilja gallring nedifrån från ovan.',
      overrides:{ccfRemoval:.2,ccfInterval:25,ccfGrowthFactor:1,thinningCount:2,thinningShare:.25,grotShare:0,clearcutHumusLoss:.05}},
    {id:'pukkala14high', name:'Pukkala (2014), hög gallring', href:'https://doi.org/10.1016/j.forpol.2014.03.004',
      published:['−','−','−',''], note:'RF hög gallring med biobränsle jämfört med CCF. Högre RF-uttag och GROT är proxier; ursprungsstudiens gallringsmetod och processutsläpp saknas.',
      overrides:{ccfRemoval:.45,ccfInterval:10,ccfGrowthFactor:.8,thinningCount:3,thinningShare:.35,grotShare:.65,clearcutHumusLoss:.05}},
    {id:'lundmark16same', name:'Lundmark m.fl. (2016), lika tillväxt', href:'https://doi.org/10.1007/s13280-015-0756-3',
      published:['n.d.','+','+','−'], note:'Studien antar lika faktisk biomassaproduktion. Modellens tillväxtfaktor 1,0 avser potentiell CCF-tillväxt efter omföring och garanterar inte lika faktisk produktion.',
      overrides:{analysisYears:200,ccfInterval:10,ccfGrowthFactor:1,ccfRemoval:.3,retentionShare:.05,clearcutHumusLoss:.05}},
    {id:'lundmark16low', name:'Lundmark m.fl. (2016), 80 %', href:'https://doi.org/10.1007/s13280-015-0756-3',
      published:['−','+','','−'], note:'80 % i ursprungsstudien avser realiserad årsproduktion i CCF relativt RF. Tillväxtfaktor 0,8 här är en sensitivitet, inte ett exakt produktionsvillkor.',
      overrides:{analysisYears:200,ccfInterval:10,ccfGrowthFactor:.8,ccfRemoval:.3,retentionShare:.05,clearcutHumusLoss:.05,grotShare:.8}},
    {id:'lagergren17', name:'Lagergren & Jönsson (2017)', href:'https://doi.org/10.1016/j.ecoser.2017.06.007',
      published:['n.d.','n.d.','n.d.','+'], note:'Studiens RF hade 45 % lövträd och CCF 13–20 %. Här används gran/bok som proxy (45 % respektive 17 % bok), utan LPJ-GUESS eller framtida klimat.',
      overrides:{projectSpecies:'mixed',projectMixedSpruceShare:.83,referenceSpeciesMode:'custom',referenceSpecies:'mixed',referenceMixedSpruceShare:.55,ccfRemoval:.3,ccfInterval:20,ccfGrowthFactor:.9}},
    {id:'peura18', name:'Peura m.fl. (2018)', href:'https://doi.org/10.1016/j.biocon.2017.10.018',
      published:['','', '(+)', '−'], note:'Minskat uttag vid CCF. Källan visar svagt positiv ekosystemeffekt; antagen blädningsstyrka här är en förenklad känslighet.',
      overrides:{ccfRemoval:.18,ccfInterval:25,ccfGrowthFactor:.9}},
    {id:'kellomaki21', name:'Kellomäki m.fl. (2021)', href:'https://doi.org/10.1093/forestry/cpab010',
      published:['−','+','−','+'], note:'Central Finland, ursprunglig simulering 401–1 000 år; illustrativt 200 år i modellen. Albedo och ursprunglig klimatutveckling ingår inte.',
      overrides:{analysisYears:200,projectType:'existing',projectStartAge:40,referenceStartAge:40,ccfRemoval:.35,ccfInterval:10,ccfGrowthFactor:1.1,productSawnFinal:.50,productSawnCcf:.40,breedingGain:.20,clearcutHumusLoss:.05}},
  ];
  function inputsFor(id) {
    const study = CASES.find((s) => s.id === id);
    if (!study) throw new Error('Okänt studiefall: ' + id);
    return Object.assign({}, Model.DEFAULT_INPUTS, BASE, study.overrides, {projectName:'Tabell 13.1 – ' + study.name});
  }
  function delta(end, start, p, r) {
    return (end[p] - start[p]) - (end[r] - start[r]);
  }
  function poolDifferences(simulation) {
    const start = simulation.rows[0], end = simulation.rows[simulation.rows.length-1];
    return {
      biomass:delta(end,start,'projectLiveC','referenceLiveC'),
      soil:delta(end,start,'projectHumusC','referenceHumusC') + delta(end,start,'projectSocC','referenceSocC'),
      ecosystem:delta(end,start,'projectEcosystemC','referenceEcosystemC'),
      hwp:delta(end,start,'projectHwpC','referenceHwpC'),
    };
  }
  function direction(value) { return value > 2 ? '+' : value < -2 ? '−' : '≈0'; }
  function runCase(id) { const inputs=inputsFor(id); return {inputs, result:Model.simulate(inputs)}; }
  return {CASES, inputsFor, poolDifferences, direction, runCase};
});

"""

_JS_CONTROLS = r"""
/* 40 spårbara utfall: 27 tecken ur tabell 13.1, åtta utfall ur Stål 2024,
   fem ur IVL 2026. Resultat och känslighet kommer alltid från ForestModel.simulate. */
(function (root, factory) {
  const api = factory(root.ForestModel, root.ForestStudies);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.ForestChecks = api;
})(typeof self !== 'undefined' ? self : this, function (Model, Studies) {
  'use strict';
  if (!Model || !Studies) throw new Error('Skogsmodellen och referensfallen behövs.');
  const BOOK = 'https://doi.org/10.1007/978-3-031-70484-0_13';
  const STAL = 'https://doi.org/10.1080/02827581.2024.2437409';
  const IVL = 'https://www.diva-portal.org/smash/get/diva2:2057070/FULLTEXT01.pdf';
  const POOLS = [
    ['biomass', 'Levande biomassa'], ['soil', 'Mark (förna/humus + SOC)'],
    ['ecosystem', 'Ekosystemkol'], ['hwp', 'Träprodukter'],
  ];
  const SIGN_CHECKS = [];
  Studies.CASES.forEach((study) => {
    study.published.forEach((source, idx) => {
      if (!source) return;
      SIGN_CHECKS.push({id:'T' + String(SIGN_CHECKS.length + 1).padStart(2, '0'),
        group:'Tabell 13.1', caseId:study.id, study:study.name, href:study.href,
        evidenceHref:BOOK, endpoint:POOLS[idx][1], key:POOLS[idx][0],
        source, unit:'tC/ha', horizon:study.overrides.analysisYears || 100,
        note:study.note, comparable:study.id !== 'kellomaki21' ? 'Förenklad jämförelse' : 'Utanför studiens tidshorisont',
      });
    });
  });
  // 2024 års svenska RegWise-studie: en 50-årig övergång på produktiv skogsmark.
  // källvärdena nedan är publicerade tal; 3,1/2,2 och 10,3/6,6 är beräknade kvoter.
  const STAL_CHECKS = [
    ['S01','Förrådsökning CCF under 50 år',.47,'andel','ccfStockGain','Stål: 47 % från start.',true],
    ['S02','Virkesförråd CCF/RF år 50',3.1/2.2,'kvot','stockRatio','Härlett ur avrundade 3,1 och 2,2 miljarder m³. Stort strukturellt avstånd mellan nation och schablon.',false],
    ['S03','Genomsnittligt virkesuttag CCF/RF',.85,'kvot','harvestRatio','Källa: 85 % i genomsnitt över 50 år. Träningsmål.',true],
    ['S04','Sågtimmerflöde CCF/RF',.86,'kvot','sawnRatio','Källa: 86 %. Modellens inflöde till sågade trävaror är en proxy, inte sågade timmerstockar.',false],
    ['S05','Lägsta 5-åriga uttagskvot CCF/RF',.50,'kvot','harvestMin','Källa: minsta uppmätta 5-årsperiod 50 %; vår modell saknar ekonomiska/juridiska begränsningar.',false],
    ['S06','Högsta 5-åriga uttagskvot CCF/RF',1.08,'kvot','harvestMax','Källa: högsta uppmätta 5-årsperiod 108 %.',false],
    ['S07','Död ved CCF/RF år 50',10.3/6.6,'kvot','deadwoodRatio','Härledd kvot ur 10,3/6,6 m³/ha. Modellens död ved mäts i tC/ha (proxy för volymkvot).',false],
    ['S08','Nettotillväxt CCF/RF sista året',.91,'kvot','growthRatio','Källa: CCF:s tillväxt 9 % lägre år 50. Modellen approximerar nettotillväxt med biomassatillväxt + avgång och uttag; ej identiska definitioner.',false],
  ].map(([id,endpoint,target,unit,metric,note,calibration])=>({id, group:'Stål m.fl. 2024', study:'Stål m.fl. (2024)',
    href:STAL,endpoint,source:target,unit,metric,caseId:'stal',horizon:50,note,
    comparable:metric==='sawnRatio'||metric==='deadwoodRatio'||metric==='growthRatio'?'Proxy':'Nationell jämförelse', calibration}));
  // IVL 2026 ger kvalitativa riktningar, inte konfidensintervall eller exakta
  // kvoter i löptexten. "Likartat" bedöms illustrativt som 0,85–1,15.
  const IVL_CHECKS = [
    ['I01','Södra Sverige: virkesuttag CCF/RF','harvestRatio','south','ungefär lika (kvalitativt)','≈1'],
    ['I02','Mellersta Sverige: virkesuttag CCF/RF','harvestRatio','south','ungefär lika (kvalitativt)','≈1',true],
    ['I03','Norra Sverige: virkesuttag CCF/RF','harvestRatio','north','ungefär lika (kvalitativt)','≈1'],
    ['I04','Mellersta Sverige: kol i levande träd CCF–RF','liveDiff','south','CCF högre (+)','+ ',true],
    ['I05','Norra Sverige: kol i levande träd CCF–RF','liveDiff','north','CCF högre (+)','+ '],
  ].map(([id,endpoint,metric,region,source,expect,central])=>({id,group:'IVL 2026',study:'Pukkala, Malmaeus & Mattsson (2026)',
    href:IVL,caseId:id,endpoint,metric,region,source,expect,unit:metric==='liveDiff'?'tC/ha':'kvot',
    horizon:75,note:'75 år; 20 % äldsta skogen skyddas i båda körningarna. ' + (central?'"Mellersta Sverige" approximeras av södra tillväxtprofilen: kvalitativ proxy.':'Modellens region och åldersprofil är förenklade.'),
    comparable:central?'Geografisk proxy':'Förenklad landskapsjämförelse', calibration:false}));
  const CHECKS = [...SIGN_CHECKS,...STAL_CHECKS,...IVL_CHECKS];
  if (CHECKS.length !== 40) throw new Error('Exakt 40 referensutfall krävs, fick ' + CHECKS.length);

  function stalInputs() {
    return {...Model.DEFAULT_INPUTS, projectType:'landscape', currentLandUse:'forest',
      projectSpecies:'conifers',projectProductivityMethod:'h100',projectProductivityValue:22,
      analysisYears:50,projectForestScenario:'continuous',referenceScenario:'conventionalForest',
      referenceForestScenario:'conventional', systemBoundary:'ecosystem', disturbanceLevel:'off'};
  }
  function ivlInputs(check, scenario) {
    // Oberoende simulerade körningar med samma skyddade areal i RF och CCF.
    return {...Model.DEFAULT_INPUTS, projectType:'landscape',currentLandUse:'forest',
      region:check.region,projectSpecies:'conifers',projectProductivityMethod:'bonitet',
      projectProductivityValue:check.region==='north'?4.5:check.id==='I02'||check.id==='I04'?6.0:8.8,
      analysisYears:75,projectForestScenario:'mix',referenceScenario:'conventionalForest',
      referenceForestScenario:'conventional',mixNatural:.20,mixConventional:scenario==='RF'?.80:0,
      mixContinuous:scenario==='CCF'?.80:0,mixExtended:0,mixIntensive:0,
      landscapeProtectOldest:true,systemBoundary:'ecosystem',
      grotShare:scenario==='RF'?.65:0,disturbanceLevel:'off'};
  }
  // För södra och mellersta Sverige används samma matematiska sydprofil men
  // olika bonitet; modellen har ingen särskild regionkod för Svealand.
  function variants(i) {
    const scale = (v,low,high)=>Math.max(low,Math.min(high,v));
    const base = i.ccfGrowthFactor;
    if (i.ccfMethod==='interval') return [i,
      {...i,ccfGrowthFactor:scale(base-.15,.3,1.5),ccfRemoval:scale(i.ccfRemoval-.08,.05,.6)},
      {...i,ccfGrowthFactor:scale(base+.15,.3,1.5),ccfRemoval:scale(i.ccfRemoval+.08,.05,.6)},
      {...i,ccfGrowthFactor:scale(base-.15,.3,1.5),ccfRemoval:scale(i.ccfRemoval+.08,.05,.6)},
      {...i,ccfGrowthFactor:scale(base+.15,.3,1.5),ccfRemoval:scale(i.ccfRemoval-.08,.05,.6)}];
    return [i,
      {...i,ccfGrowthFactor:scale(base-.15,.3,1.5),ccfUpperStock:i.ccfUpperStock-30,ccfLowerStock:i.ccfLowerStock-20},
      {...i,ccfGrowthFactor:scale(base+.15,.3,1.5),ccfUpperStock:i.ccfUpperStock+30,ccfLowerStock:i.ccfLowerStock+20},
      {...i,ccfGrowthFactor:scale(base-.15,.3,1.5),ccfUpperStock:i.ccfUpperStock+30,ccfLowerStock:i.ccfLowerStock+20},
      {...i,ccfGrowthFactor:scale(base+.15,.3,1.5),ccfUpperStock:i.ccfUpperStock-30,ccfLowerStock:i.ccfLowerStock-20}];
  }
  const div = (a,b)=>Math.abs(b)>1e-8?a/b:NaN;
  function sum(rows,key,start,end) {let s=0;for(let t=start;t<=end;t++)s+=rows[t][key];return s;}
  function stalMetric(r,key) {
    const rows=r.rows,a=rows[0],z=rows[50];
    if (key==='ccfStockGain') return div(z.projectLiveC,a.projectLiveC)-1;
    if (key==='stockRatio') return div(z.projectLiveC,z.referenceLiveC);
    if (key==='harvestRatio') return div(r.summary.projectMeanHarvestM3,r.summary.referenceMeanHarvestM3);
    if (key==='sawnRatio') return div(sum(rows,'projectSawnInC',1,50),sum(rows,'referenceSawnInC',1,50));
    if (key==='deadwoodRatio') return div(z.projectDeadwoodC,z.referenceDeadwoodC);
    if (key==='growthRatio') {
      const p=z.projectLiveC-rows[49].projectLiveC+z.projectHarvestTotalC;
      const rf=z.referenceLiveC-rows[49].referenceLiveC+z.referenceHarvestTotalC;
      return div(p,rf);
    }
    if (key==='harvestMin'||key==='harvestMax') {
      const periods=[];
      for(let start=1;start<=50;start+=5) periods.push(div(sum(rows,'projectHarvestM3',start,start+4),sum(rows,'referenceHarvestM3',start,start+4)));
      return key==='harvestMin'?Math.min(...periods):Math.max(...periods);
    }
    throw new Error('Okänt Stål-mått: '+key);
  }
  function ivlMetric(project,reference,key) {
    if (key==='harvestRatio') return div(project.summary.projectMeanHarvestM3,reference.summary.projectMeanHarvestM3);
    if (key==='liveDiff') return (project.rows[75].projectLiveC-project.rows[0].projectLiveC)-
      (reference.rows[75].projectLiveC-reference.rows[0].projectLiveC);
    throw new Error('Okänt IVL-mått: '+key);
  }
  function evaluate(check,results) {
    const values = results.filter(Number.isFinite);
    if (!values.length) return {...check,value:null,low:null,high:null,status:'Ej beräkningsbar'};
    const value=values[0],low=Math.min(...values),high=Math.max(...values);
    let status;
    if(check.id[0]==='T') {
      const eq=(v)=>check.source==='n.d.'?Math.abs(v)<=2:(check.source==='−'?v < -2:v > 2);
      const canAgree=check.source==='n.d.'?low<=2&&high>=-2:
        check.source==='−'?low < -2:high > 2;
      status=check.comparable==='Utanför studiens tidshorisont'?'Utanför källans period':
        check.source==='(+)'&&eq(value)?'Positiv riktning; styrkan okänd':
        eq(value)?'Samma tecken':canAgree?'Känsligt tecken':'Avvikande tecken';
    } else if(check.id[0]==='I') {
      const eq=(v)=>check.expect==='≈1'?v>=.85&&v<=1.15:v>2;
      status=eq(value)?'Förenligt (proxy)':values.some(eq)?'Känsligt (proxy)':'Avvikande (proxy)';
    } else {
      status=Math.abs(value-check.source)<1e-9?'Samma värde':low<=check.source&&high>=check.source?'Källvärde inom spann':'Källvärde utanför spann';
    }
    return {...check,value,low,high,status};
  }
  function runAll() {
    const cache={};
    for(const study of Studies.CASES) {
      const input=Studies.inputsFor(study.id);
      cache[study.id]=variants(input).map(i=>Studies.poolDifferences(Model.simulate(i)));
    }
    cache.stal=variants(stalInputs()).map(i=>Model.simulate(i));
    for(const check of IVL_CHECKS) {
      const project=variants(ivlInputs(check,'CCF'));
      const reference=ivlInputs(check,'RF');
      // Endast CCF-skötselparametrar ändras; RF-körningen hålls fast.
      const rf=Model.simulate(reference);
      cache[check.id]=project.map(i=>ivlMetric(Model.simulate(i),rf,check.metric));
    }
    return CHECKS.map(check=>evaluate(check,check.id[0]==='T'?cache[check.caseId].map(v=>v[check.key]):
      check.id[0]==='S'?cache.stal.map(v=>stalMetric(v,check.metric)):cache[check.id]));
  }
  return {CHECKS,runAll,stalInputs,ivlInputs,variants};
});


"""


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print(f'Fel: {error}', file=sys.stderr)
        sys.exit(1)
