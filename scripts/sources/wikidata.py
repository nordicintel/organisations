"""Wikidata: public bodies with organisationsnummer, codes, dates and succession (CC0)."""
import json
from pathlib import Path

from .common import cached, orgnr, sparql

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


def fetch(cache: Path):
    items = {}
    for kind, q in QUERIES.items():
        path = cached(cache, f"wikidata_{kind}.json", lambda q=q: json.dumps(sparql(ENDPOINT, q)).encode())
        for r in json.loads(path.read_text(encoding="utf-8")):
            qid = r["item"]["value"].rsplit("/", 1)[-1]
            rec = items.setdefault(qid, {"kind": kind, "label": r["label"]["value"], "replaced_by": []})
            if "label_en" in r:
                rec["label_en"] = r["label_en"]["value"]
            for k in ("orgnr", "kommunkod", "inception", "dissolved", "department", "riksarkivet"):
                if k in r:  # several statements may exist; keep the smallest for a stable build
                    rec[k] = min(filter(None, [rec.get(k), r[k]["value"]]))
            if "replacedBy" in r:
                rec["replaced_by"].append(r["replacedBy"]["value"].rsplit("/", 1)[-1])
            if rec.get("orgnr"):
                rec["orgnr"] = orgnr(rec["orgnr"])
    return items
