"""data.europa.eu SPARQL: the agents behind the Swedish catalogues, with identifiers and types.

The Swedish catalogues are those the hub files under Sweden (``dct:spatial`` = country SWE
on the catalogue): oppnadata (dataportal.se), geodata-se (Geodataportalen) and nsip-se.
Every dataset is its own named graph, which also describes its publisher, creator and
rights holder.

The endpoint sits behind a gateway that cuts every request at 60 s. One query joining all
properties over the catalogues' 25,000 dataset graphs runs past that; one small query per
catalogue, role and property answers in a second or two.

Agents with a URI are keyed by it. Geodataportalen names no URIs: its rights holders are
blank contact nodes (a name such as "Kundservice", a mailbox, sometimes the organisation
through org:memberOf). Those are keyed by their mailbox, the one stable thing they carry,
with the organisation's name where given, so a reader can still tie them to a body by name
or mail domain.
"""
import json
from pathlib import Path

from .common import cached, skip, sparql

ENDPOINT = "https://data.europa.eu/sparql"
SWEDEN = "http://publications.europa.eu/resource/authority/country/SWE"
PREFIXES = """PREFIX dct: <http://purl.org/dc/terms/> PREFIX dcat: <http://www.w3.org/ns/dcat#>
PREFIX foaf: <http://xmlns.com/foaf/0.1/> PREFIX owl: <http://www.w3.org/2002/07/owl#> PREFIX org: <http://www.w3.org/ns/org#>"""
ROLES = ("publisher", "creator", "rightsHolder")
PROPERTIES = {"names": "foaf:name", "identifier": "dct:identifier", "type": "dct:type",
              "homepage": "foaf:homepage", "same_as": "owl:sameAs"}
CATALOGUES_Q = f"{PREFIXES}\nSELECT DISTINCT ?cat WHERE {{ ?cat a dcat:Catalog ; dct:spatial <{SWEDEN}> }}"


def _query(catalogue, role, prop=None, blank=False):
    """Agents of ``role`` in one catalogue (URIs, or blank nodes keyed by mailbox), or every
    (agent, value) pair of one property."""
    if blank:
        select, pattern = "?uri (SAMPLE(?org) AS ?value)", \
            "?d dct:%s ?a FILTER(isBLANK(?a)) ?a foaf:mbox ?uri OPTIONAL { ?a org:memberOf/foaf:name ?org }" % role
        tail = "GROUP BY ?uri"
    else:
        select = "?uri ?value" if prop else "?uri"
        pattern = f"?d dct:{role} ?uri FILTER(isIRI(?uri))" + (f" ?uri {PROPERTIES[prop]} ?value" if prop else "")
        tail = ""
    return f"""{PREFIXES}
SELECT DISTINCT {select} WHERE {{ <{catalogue}> dcat:dataset ?d . GRAPH ?d {{ {pattern} }} }} {tail}"""


def _rows(cache, name, query):
    path = cached(cache, name, lambda: json.dumps(sparql(ENDPOINT, query)).encode())
    return json.loads(path.read_text(encoding="utf-8"))


def fetch(cache: Path):
    out = {}
    catalogues = sorted(r["cat"]["value"] for r in _rows(cache, "data_europa_catalogues.json", CATALOGUES_Q))
    if not catalogues:
        raise ValueError("no catalogue filed under Sweden")

    def agent(uri, role, catalogue):
        rec = out.setdefault(uri, {"roles": [], "catalogue": [], "names": {}, "same_as": []})
        for key, value in (("roles", role), ("catalogue", catalogue.rsplit("/", 1)[-1])):
            if value not in rec[key]:
                rec[key].append(value)
        return rec

    for catalogue in catalogues:
        short = catalogue.rsplit("/", 1)[-1]
        for role in ROLES:
            for r in _rows(cache, f"data_europa_{short}_{role}_agent.json", _query(catalogue, role)):
                try:
                    agent(r["uri"]["value"], role, catalogue)
                except Exception as error:  # noqa: BLE001
                    skip("data_europa", r, error)
            for prop in PROPERTIES:
                for r in _rows(cache, f"data_europa_{short}_{role}_{prop}.json", _query(catalogue, role, prop)):
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
            for r in _rows(cache, f"data_europa_{short}_{role}_blank.json", _query(catalogue, role, blank=True)):
                try:
                    mailbox = r["uri"]["value"].strip().rstrip(".").lower()  # one contact appears in several spellings
                    if mailbox == "mailto:":
                        continue
                    rec = agent(mailbox, role, catalogue)
                    if r.get("value", {}).get("value"):
                        rec["names"]["und"] = min(filter(None, [rec["names"].get("und"), r["value"]["value"].strip()]))
                except Exception as error:  # noqa: BLE001
                    skip("data_europa", r, error)
    for rec in out.values():
        rec["roles"].sort()
        rec["catalogue"].sort()
        rec["names"] = dict(sorted(rec["names"].items()))
    return dict(sorted(out.items()))
