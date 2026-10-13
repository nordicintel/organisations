"""Build data/organisations.json and links/*.json from the free registers.

Usage: python scripts/build.py [--cache DIR]
Downloads are cached in DIR (default .cache) and reused when present.
"""
import argparse
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from sources import data_europa, dataportal, myndighetsregistret, scb_bulk, wikidata  # noqa: E402
from sources.common import org_id, orgnr  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FORM_TO_TYPE = {"81": "NationalAuthority", "82": "LocalAuthority", "83": "LocalAuthority", "84": "RegionalAuthority",
                "85": "NationalAuthority", "87": "NonProfitOrganisation", "88": "Company", "89": "NationalAuthority",
                "49": "Company", "41": "Company", "42": "Company", "31": "Company", "51": "NonProfitOrganisation",
                "61": "NonProfitOrganisation", "63": "NonProfitOrganisation", "71": "NonProfitOrganisation",
                "72": "NonProfitOrganisation", "93": "Company", "95": "NonProfitOrganisation"}


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=str(ROOT / ".cache"))
    args = ap.parse_args()
    cache = Path(args.cache)

    slugs = json.loads((ROOT / "slugs.json").read_text(encoding="utf-8"))
    aliases = json.loads((ROOT / "aliases.json").read_text(encoding="utf-8"))
    manual = json.loads((ROOT / "manual.json").read_text(encoding="utf-8"))

    portal = dataportal.fetch(cache)
    europa = data_europa.fetch(cache)
    wd = wikidata.fetch(cache)
    state = myndighetsregistret.fetch(cache)

    # every organisationsnummer any other source or our own files mention
    wanted = set()
    for uri, rec in list(portal["registry"].items()) + list(portal["publishers"].items()):
        for v in (uri, rec.get("identifier")):
            if (n := orgnr(v)):
                wanted.add(n)
    for uri, rec in europa.items():
        for v in (uri, rec.get("identifier")):
            if (n := orgnr(v)):
                wanted.add(n)
    wanted |= {r["orgnr"] for r in wd.values() if r.get("orgnr")}
    wanted |= set(state)
    wanted |= {orgnr(v) for v in list(slugs.values()) + list(aliases.values()) + list(manual) if orgnr(v)}
    scb = scb_bulk.fetch(cache, wanted=frozenset(wanted))

    orgs = {}
    names = {}  # id -> {lang: [(priority, name)]}
    PRIORITY = {"manual": 0, "dataportal": 1, "myndighetsregistret": 2, "wikidata": 3, "data_europa": 4, "scb_bulk": 5}

    def rec(number, suffix=""):
        key = org_id(number) + suffix
        return orgs.setdefault(key, {"id": key, "names": {}, "status": "unknown", "identifiers": {"orgnr": number}, "sources": []})

    def name(r, lang, value, source):
        if value:
            names.setdefault(r["id"], {}).setdefault(lang, []).append((PRIORITY[source], value))

    def canonical(number, suffix=""):
        return f"http://dataportal.se/organisation/SE{number}{suffix}"

    def add_same_as(r, *uris):
        own = {canonical(r["identifiers"]["orgnr"], r["id"][12:]) if "orgnr" in r["identifiers"] else None}
        extra = {u for u in uris if u and u not in own}
        if extra:
            r["same_as"] = sorted(set(r.get("same_as", [])) | extra)

    def suffix_of(uri):
        m = re.search(r"organisation/(?:SE)?\d{10}(-[A-Z0-9]+)", uri or "")
        return m.group(1) if m else ""

    for number, row in scb.items():
        r = rec(number)
        r["registered_name"] = row["name"]
        name(r, "sv", row["name"].title() if row["name"].isupper() else row["name"], "scb_bulk")
        r["status"] = "active" if row["jestat"] in ("1", "2") and row["ftgstat"] != "9" else "deregistered"
        r["legal_form"] = {"code": row["legal_form"], "label": scb_bulk.LEGAL_FORMS.get(row["legal_form"], "")}
        if row["legal_form"] in FORM_TO_TYPE:
            r["publisher_type"] = FORM_TO_TYPE[row["legal_form"]]
        if row["registered"]:
            r["established"] = row["registered"]
        r["sources"].append("scb_bulk")

    for number, row in state.items():
        r = rec(number)
        name(r, "sv", row["name"].title() if row["name"].isupper() else row["name"], "myndighetsregistret")
        r["state_body_group"] = row["group"]
        if row["sfs"]:
            r["sfs"] = row["sfs"]
        if row["web"] and "homepage" not in r:
            r["homepage"] = row["web"] if row["web"].startswith("http") else "https://" + row["web"]
        if row["email"]:
            r.setdefault("email", row["email"])
        r["sources"].append("myndighetsregistret")

    links_portal, links_europa, links_wd = {}, {}, {}
    for uri, row in portal["registry"].items():
        number = orgnr(uri) or orgnr(row.get("identifier"))
        if not number:
            links_portal[uri] = None
            continue
        r = rec(number, suffix_of(uri))
        for lang, value in row["names"].items():
            name(r, lang, value, "dataportal")
        if row.get("type") and "publisher_type" not in r:
            r["publisher_type"] = row["type"]
        if row.get("homepage"):
            r.setdefault("homepage", row["homepage"])
        if row.get("email"):
            r.setdefault("email", row["email"])
        r["identifiers"]["dataportal"] = canonical(number, suffix_of(uri))
        add_same_as(r, uri, *row.get("same_as", []))
        r["sources"].append("dataportal")
        links_portal[uri] = r["id"]
    for uri, row in portal["publishers"].items():
        number = orgnr(uri) or orgnr(row.get("identifier"))
        links_portal.setdefault(uri, (org_id(number) + suffix_of(uri)) if number else None)
        if number:
            r = rec(number, suffix_of(uri))
            r["identifiers"].setdefault("dataportal", canonical(number, suffix_of(uri)))
            add_same_as(r, uri)
            if "dataportal" not in r["sources"]:
                r["sources"].append("dataportal")

    for uri, row in europa.items():
        number = orgnr(uri) or orgnr(row.get("identifier"))
        links_europa[uri] = org_id(number) if number else None
        if not number:
            continue
        r = rec(number, suffix_of(uri))
        for lang, value in row["names"].items():
            name(r, lang, value, "dataportal")
        if row.get("type") and "publisher_type" not in r:
            r["publisher_type"] = row["type"].rsplit("/", 1)[-1]
        if row.get("homepage"):
            r.setdefault("homepage", row["homepage"])
        r["identifiers"].setdefault("dataportal", canonical(number, suffix_of(uri)))
        add_same_as(r, uri, *row.get("same_as", []))
        r["sources"].append("data_europa")

    qid_to_id = {qid: org_id(row["orgnr"]) for qid, row in wd.items() if row.get("orgnr")}
    for qid, row in wd.items():
        links_wd[qid] = qid_to_id.get(qid)
        if not row.get("orgnr"):
            continue
        r = rec(row["orgnr"])
        name(r, "sv", row["label"], "wikidata")
        if row.get("label_en"):
            name(r, "en", row["label_en"], "wikidata")
        r["identifiers"]["wikidata"] = qid
        if row.get("riksarkivet"):
            r["identifiers"]["riksarkivet"] = row["riksarkivet"]
        if row.get("kommunkod"):
            r.setdefault("codes", {})["kommun"] = row["kommunkod"]
            r["codes"]["lan"] = row["kommunkod"][:2]
        if row.get("department"):
            r["department"] = row["department"]
        if row.get("inception"):
            r.setdefault("established", row["inception"][:10])
        if row.get("dissolved"):
            r["dissolved"] = row["dissolved"][:10]
            if r["status"] == "unknown":
                r["status"] = "deregistered"
        succ = [qid_to_id[q] for q in row["replaced_by"] if q in qid_to_id]
        if succ:
            r["succeeded_by"] = sorted(set(r.get("succeeded_by", [])) | set(succ))
        r["sources"].append("wikidata")

    for key, patch in manual.items():
        r = orgs.setdefault(key, {"id": key, "names": {}, "status": "unknown", "identifiers": {}, "sources": []})
        for field, value in patch.items():
            if field == "names":
                for lang, v in value.items():
                    name(r, lang, v, "manual")
            elif field == "identifiers":
                r["identifiers"].update(value)
            elif field == "same_as":
                add_same_as(r, *value)
                for uri in value:
                    links_europa[uri] = key
                    links_portal.setdefault(uri, key)
            elif isinstance(value, dict):
                r.setdefault(field, {}).update(value)
            else:
                r[field] = value
        r["sources"].append("manual")

    for r in orgs.values():
        r["sources"] = sorted(set(r["sources"]))
        for lang, candidates in names.get(r["id"], {}).items():
            r["names"].setdefault(lang, min(candidates)[1])
        if not r["names"]:
            r["names"]["sv"] = r.get("registered_name") or r["id"]
        if r["id"].count("-") and "part_of" not in r:
            r["part_of"] = r["id"].split("-")[0]

    missing = {k: v for k, v in {**slugs, **{k: v for k, v in aliases.items() if v}}.items() if v not in orgs}
    if missing:
        print(f"WARNING {len(missing)} slug/alias targets are not in the registry, e.g. {list(missing.items())[:5]}", file=sys.stderr)

    dump(ROOT / "organisations.json", {"generated": date.today().isoformat(), "count": len(orgs),
                                                 "organisations": dict(sorted(orgs.items()))})
    dump(ROOT / "links" / "dataportal.json", dict(sorted(links_portal.items())))
    dump(ROOT / "links" / "data-europa.json", dict(sorted(links_europa.items())))
    dump(ROOT / "links" / "wikidata.json", dict(sorted(links_wd.items())))
    counts = Counter(r.get("legal_form", {}).get("code", "none") for r in orgs.values())
    print(f"{len(orgs)} organisations; legal forms: {dict(counts.most_common(12))}", file=sys.stderr)


if __name__ == "__main__":
    main()
