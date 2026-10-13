"""data.europa.eu SPARQL: publishers and creators of the Swedish catalogue with identifiers and types."""
import json
from pathlib import Path

from .common import cached, sparql

ENDPOINT = "https://data.europa.eu/sparql"
CATALOGUE = "http://data.europa.eu/88u/catalogue/oppnadata"


def _query(role):
    return f"""
PREFIX dct: <http://purl.org/dc/terms/> PREFIX dcat: <http://www.w3.org/ns/dcat#>
PREFIX foaf: <http://xmlns.com/foaf/0.1/> PREFIX owl: <http://www.w3.org/2002/07/owl#>
SELECT ?uri (GROUP_CONCAT(DISTINCT CONCAT(STR(?n), "@", LANG(?n)); separator="|") AS ?names)
       (SAMPLE(?i) AS ?identifier) (SAMPLE(?t) AS ?type) (SAMPLE(?h) AS ?homepage)
       (GROUP_CONCAT(DISTINCT STR(?s); separator="|") AS ?same_as) (COUNT(DISTINCT ?d) AS ?datasets)
WHERE {{
  <{CATALOGUE}> dcat:dataset ?d .
  GRAPH ?d {{ ?d dct:{role} ?uri .
    OPTIONAL {{ ?uri foaf:name ?n }} OPTIONAL {{ ?uri dct:identifier ?i }} OPTIONAL {{ ?uri dct:type ?t }}
    OPTIONAL {{ ?uri foaf:homepage ?h }} OPTIONAL {{ ?uri owl:sameAs ?s }} }}
}} GROUP BY ?uri
"""


def fetch(cache: Path):
    out = {}
    for role in ("publisher", "creator"):
        path = cached(cache, f"data_europa_{role}s.json", lambda role=role: json.dumps(sparql(ENDPOINT, _query(role))).encode())
        for r in json.loads(path.read_text(encoding="utf-8")):
            uri = r["uri"]["value"]
            rec = out.setdefault(uri, {"roles": [], "names": {}, "same_as": []})
            rec["roles"].append(role)
            for part in (r.get("names", {}).get("value") or "").split("|"):
                if "@" in part:
                    name, _, lang = part.rpartition("@")
                    rec["names"].setdefault(lang or "und", name)
            for k in ("identifier", "type", "homepage"):
                if k in r:
                    rec[k] = r[k]["value"]
            rec["same_as"] = sorted(set(rec["same_as"]) | {s for s in (r.get("same_as", {}).get("value") or "").split("|") if s})
    return out
