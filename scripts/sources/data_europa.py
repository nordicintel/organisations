"""data.europa.eu SPARQL: publishers and creators of the Swedish catalogue with identifiers and types.

The endpoint sits behind a gateway that cuts every request at 60 s. One query joining all
properties (several OPTIONALs, GROUP_CONCAT) over the catalogue's 23,000 dataset graphs
runs past that; one small query per property answers in about a second. Each dataset is
its own named graph, which also holds the description of its publisher and creator.
"""
import json
from pathlib import Path

from .common import cached, skip, sparql

ENDPOINT = "https://data.europa.eu/sparql"
CATALOGUE = "http://data.europa.eu/88u/catalogue/oppnadata"
PREFIXES = """PREFIX dct: <http://purl.org/dc/terms/> PREFIX dcat: <http://www.w3.org/ns/dcat#>
PREFIX foaf: <http://xmlns.com/foaf/0.1/> PREFIX owl: <http://www.w3.org/2002/07/owl#>"""
PROPERTIES = {"names": "foaf:name", "identifier": "dct:identifier", "type": "dct:type",
              "homepage": "foaf:homepage", "same_as": "owl:sameAs"}


def _query(role, prop=None):
    """Every agent in ``role``, or every (agent, value) pair of one property."""
    pattern = f"?uri {PROPERTIES[prop]} ?value" if prop else ""
    return f"""{PREFIXES}
SELECT DISTINCT ?uri {"?value" if prop else ""} WHERE {{
  <{CATALOGUE}> dcat:dataset ?d . GRAPH ?d {{ ?d dct:{role} ?uri . {pattern} }} }}"""


def _rows(cache, role, prop=None):
    name = f"data_europa_{role}_{prop or 'agent'}.json"
    path = cached(cache, name, lambda: json.dumps(sparql(ENDPOINT, _query(role, prop))).encode())
    return json.loads(path.read_text(encoding="utf-8"))


def fetch(cache: Path):
    out = {}
    for role in ("publisher", "creator"):
        for r in _rows(cache, role):
            try:
                rec = out.setdefault(r["uri"]["value"], {"roles": [], "names": {}, "same_as": []})
                rec["roles"].append(role)
            except Exception as error:  # noqa: BLE001
                skip("data_europa", r, error)
        for prop in PROPERTIES:
            for r in _rows(cache, role, prop):
                try:
                    rec, value = out[r["uri"]["value"]], r["value"]["value"].strip()
                    if not value:
                        continue
                    # Several datasets may describe one agent differently; the smallest value wins so the build is stable.
                    if prop == "names":
                        lang = r["value"].get("xml:lang") or "und"
                        rec["names"][lang] = min(filter(None, [rec["names"].get(lang), value]))
                    elif prop == "same_as":
                        rec["same_as"] = sorted(set(rec["same_as"]) | {value})
                    else:
                        rec[prop] = min(filter(None, [rec.get(prop), value]))
                except Exception as error:  # noqa: BLE001
                    skip("data_europa", r, error)
    for rec in out.values():
        rec["roles"] = sorted(set(rec["roles"]))
        rec["names"] = dict(sorted(rec["names"].items()))
    return dict(sorted(out.items()))
