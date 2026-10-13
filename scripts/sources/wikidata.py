"""Wikidata: public bodies with organisationsnummer, codes, dates and succession, and every
name they have carried (official names, P1448, and alternative names, in Swedish) as
aliases (CC0). Names are a query of their own per kind: joined into the main query they
push the kommun and myndighet queries past the endpoint's 60 s limit."""
import json
from pathlib import Path

from .common import cached, orgnr, skip, sparql

ENDPOINT = "https://query.wikidata.org/sparql"
QUERIES = {
    "kommun": """
SELECT ?item ?label ?label_en ?orgnr ?kommunkod ?inception ?dissolved ?replacedBy WHERE {
  ?item wdt:P31 wd:Q127448 .
  OPTIONAL { ?item wdt:P6460 ?orgnr } OPTIONAL { ?item wdt:P525 ?kommunkod }
  OPTIONAL { ?item wdt:P571 ?inception } OPTIONAL { ?item wdt:P576 ?dissolved } OPTIONAL { ?item wdt:P1366 ?replacedBy }
  ?item rdfs:label ?label FILTER(LANG(?label)="sv")
  OPTIONAL { ?item rdfs:label ?label_en FILTER(LANG(?label_en)="en") } }""",
    "region": """
SELECT ?item ?label ?label_en ?orgnr ?inception ?dissolved ?replacedBy WHERE {
  ?item wdt:P31 wd:Q1754161 .
  OPTIONAL { ?item wdt:P6460 ?orgnr } OPTIONAL { ?item wdt:P571 ?inception }
  OPTIONAL { ?item wdt:P576 ?dissolved } OPTIONAL { ?item wdt:P1366 ?replacedBy }
  ?item rdfs:label ?label FILTER(LANG(?label)="sv")
  OPTIONAL { ?item rdfs:label ?label_en FILTER(LANG(?label_en)="en") } }""",
    "myndighet": """
SELECT ?item ?label ?label_en ?orgnr ?inception ?dissolved ?replacedBy ?department ?riksarkivet WHERE {
  ?item wdt:P31/wdt:P279* wd:Q68295960 .
  OPTIONAL { ?item wdt:P6460 ?orgnr } OPTIONAL { ?item wdt:P571 ?inception } OPTIONAL { ?item wdt:P576 ?dissolved }
  OPTIONAL { ?item wdt:P1366 ?replacedBy } OPTIONAL { ?item wdt:P749 ?d . ?d rdfs:label ?department FILTER(LANG(?department)="sv") }
  OPTIONAL { ?item wdt:P14316 ?riksarkivet }
  ?item rdfs:label ?label FILTER(LANG(?label)="sv")
  OPTIONAL { ?item rdfs:label ?label_en FILTER(LANG(?label_en)="en") } }""",
}
NAMES = """
SELECT ?item ?official ?alt WHERE { ?item %s .
  OPTIONAL { ?item p:P1448/ps:P1448 ?official FILTER(LANG(?official)="sv") }
  OPTIONAL { ?item skos:altLabel ?alt FILTER(LANG(?alt)="sv") } }"""
NAME_QUERIES = {"kommun": NAMES % "wdt:P31 wd:Q127448", "region": NAMES % "wdt:P31 wd:Q1754161",
                "myndighet": NAMES % "wdt:P31/wdt:P279* wd:Q68295960"}


def _rows(cache, name, query):
    path = cached(cache, name, lambda: json.dumps(sparql(ENDPOINT, query)).encode())
    return json.loads(path.read_text(encoding="utf-8"))


def fetch(cache: Path):
    items = {}
    for kind, q in QUERIES.items():
        for r in _rows(cache, f"wikidata_{kind}.json", q):
            try:
                qid = r["item"]["value"].rsplit("/", 1)[-1]
                rec = items.setdefault(qid, {"kind": kind, "label": r["label"]["value"], "replaced_by": [], "names": []})
                if "label_en" in r:
                    rec["label_en"] = r["label_en"]["value"]
                for k in ("orgnr", "kommunkod", "inception", "dissolved", "department", "riksarkivet"):
                    if k in r:  # several statements may exist; keep the smallest for a stable build
                        rec[k] = min(filter(None, [rec.get(k), r[k]["value"]]))
                if "replacedBy" in r:
                    rec["replaced_by"].append(r["replacedBy"]["value"].rsplit("/", 1)[-1])
                if rec.get("orgnr"):
                    rec["orgnr"] = orgnr(rec["orgnr"])
            except Exception as error:  # noqa: BLE001
                skip("wikidata", r, error)
    for kind, q in NAME_QUERIES.items():
        for r in _rows(cache, f"wikidata_{kind}_names.json", q):
            qid = (r.get("item") or {}).get("value", "").rsplit("/", 1)[-1]
            if qid not in items:
                continue
            for k in ("official", "alt"):
                if k in r and r[k]["value"] != items[qid]["label"] and r[k]["value"] not in items[qid]["names"]:
                    items[qid]["names"].append(r[k]["value"])
    for rec in items.values():
        rec["replaced_by"] = sorted(set(rec["replaced_by"]))
        rec["names"].sort()
    return items
