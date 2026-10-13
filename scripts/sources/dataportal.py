"""dataportal.se: the curated organisation registry (EntryStore context 827) and active publishers."""
import json
import urllib.parse
from pathlib import Path

from .common import cached, http, sparql

STORE = "https://admin.dataportal.se/store"
SPARQL = "https://admin.dataportal.se/sparql"
CTX = "827"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
P = {
    "name": "http://xmlns.com/foaf/0.1/name", "identifier": "http://purl.org/dc/terms/identifier",
    "type": "http://purl.org/dc/terms/type", "homepage": "http://xmlns.com/foaf/0.1/homepage",
    "page": "http://xmlns.com/foaf/0.1/page", "mbox": "http://xmlns.com/foaf/0.1/mbox",
    "sameAs": "http://www.w3.org/2002/07/owl#sameAs",
}


def _registry_page(offset):
    query = f"context:{STORE.replace(':', chr(92) + ':')}/{CTX} AND rdfType:http\\://xmlns.com/foaf/0.1/Agent"
    q = urllib.parse.urlencode({"type": "solr", "query": query, "limit": 100, "offset": offset})
    return http(f"{STORE}/search?{q}")


def _values(graph, uri, pred):
    out = []
    for o in graph.get(uri, {}).get(pred, []):
        out.append((o.get("value"), o.get("lang")))
    return out


def fetch_registry(cache: Path):
    orgs = {}
    offset = 0
    while True:
        path = cached(cache, f"dataportal_ctx827_{offset:04d}.json", lambda offset=offset: _registry_page(offset))
        data = json.loads(path.read_text(encoding="utf-8"))
        resources = data.get("resource", {}).get("children", [])
        for entry in resources:
            uri = entry.get("info", {}).get(f"{STORE}/{CTX}/entry/{entry['entryId']}", {}) \
                .get("http://entrystore.org/terms/resource", [{}])[0].get("value")
            md = entry.get("metadata", {})
            if not uri or uri not in md:
                continue
            names = {lang or "sv": v for v, lang in _values(md, uri, P["name"]) if v}
            orgs[uri] = {
                "names": names,
                "identifier": next((v for v, _ in _values(md, uri, P["identifier"])), None),
                "type": next((v.rsplit("/", 1)[-1] for v, _ in _values(md, uri, P["type"])), None),
                "homepage": next((v for v, _ in _values(md, uri, P["homepage"]) + _values(md, uri, P["page"])), None),
                "email": next((v.replace("mailto:", "") for v, _ in _values(md, uri, P["mbox"])), None),
                "same_as": [v for v, _ in _values(md, uri, P["sameAs"])],
            }
        if len(resources) < 100 or offset >= 5000:
            break
        offset += 100
    return orgs


PUBLISHERS_Q = """
PREFIX dct: <http://purl.org/dc/terms/> PREFIX foaf: <http://xmlns.com/foaf/0.1/>
SELECT ?uri (SAMPLE(?n) AS ?name) (SAMPLE(?i) AS ?identifier) (SAMPLE(?t) AS ?type) (COUNT(DISTINCT ?ds) AS ?datasets)
WHERE { ?ds dct:publisher ?uri . OPTIONAL { ?uri foaf:name ?n } OPTIONAL { ?uri dct:identifier ?i } OPTIONAL { ?uri dct:type ?t } }
GROUP BY ?uri
"""


def fetch_publishers(cache: Path):
    path = cached(cache, "dataportal_publishers.json",
                  lambda: json.dumps(sparql(SPARQL, PUBLISHERS_Q)).encode())
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {r["uri"]["value"]: {k: r[k]["value"] for k in ("name", "identifier", "type", "datasets") if k in r}
            for r in rows}


def fetch(cache: Path):
    return {"registry": fetch_registry(cache), "publishers": fetch_publishers(cache)}
