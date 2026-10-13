"""Build organisations.json, links/ and a report from the registers and edits/.

Usage: python scripts/build.py [--cache DIR]

Each register is fetched into the cache and reduced to a small snapshot in
snapshots/<register>.json, which is committed. When a register cannot be
fetched, the committed snapshot is used instead and the report says so. One
register failing never stops the build.
"""
import argparse
import difflib
import json
import re
import sys
import traceback
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from sources import data_europa, dataportal, myndighetsregistret, scb_bulk, statskontoret, wikidata  # noqa: E402
from sources.common import org_id, orgnr  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOTS = ROOT / "snapshots"
OUTPUT = ROOT / "organisations.json"
LEGAL_TYPE_TO_TYPE = {
    "81": "NationalAuthority", "82": "LocalAuthority", "83": "LocalAuthority", "84": "RegionalAuthority",
    "85": "NationalAuthority", "87": "NonProfitOrganisation", "88": "Company", "89": "NationalAuthority",
    "31": "Company", "41": "Company", "42": "Company", "49": "Company", "51": "NonProfitOrganisation",
    "61": "NonProfitOrganisation", "63": "NonProfitOrganisation", "71": "NonProfitOrganisation",
    "72": "NonProfitOrganisation", "93": "Company", "95": "NonProfitOrganisation",
}
LABEL_PRIORITY = {"edits": 0, "statskontoret": 1, "dataportal": 2, "myndighetsregistret": 3, "wikidata": 4,
                  "data_europa": 5, "scb_bulk": 6}


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def fetch(name, producer, report):
    """Run one register's fetch; fall back to its committed snapshot on any error."""
    path = SNAPSHOTS / f"{name}.json"
    try:
        data = producer()
        dump(path, data)
        rows = sum(len(v) for v in data.values()) if name in ("dataportal", "statskontoret") else len(data)
        report[name] = {"status": "fetched", "rows": rows}
        return data
    except Exception as error:  # noqa: BLE001 - any failure must not stop the build
        print(f"{name}: {error}", file=sys.stderr)
        traceback.print_exc()
        data = load(path, {})
        rows = sum(len(v) for v in data.values()) if name in ("dataportal", "statskontoret") else len(data)
        report[name] = {"status": "stale" if data else "failed", "rows": rows, "error": str(error)[:200]}
        return data


def canonical(number, suffix=""):
    return f"http://dataportal.se/organisation/SE{number}{suffix}"


def suffix_of(uri):
    m = re.search(r"organisation/(?:SE)?\d{10}(-[A-Z0-9]+)", uri or "")
    return m.group(1) if m else ""


def title(value):
    return value.title() if value.isupper() else value


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=str(ROOT / ".cache"))
    cache = Path(ap.parse_args().cache)

    edits = load(ROOT / "edits" / "organisations.json", {"organisation": {}, "ignore": []})
    previous_output = load(OUTPUT, {})
    previous = previous_output.get("organisation", {})
    report = {"date": date.today().isoformat(), "register": {}}
    registers = report["register"]

    portal = fetch("dataportal", lambda: dataportal.fetch(cache), registers)
    europa = fetch("data_europa", lambda: data_europa.fetch(cache), registers)
    wd = fetch("wikidata", lambda: wikidata.fetch(cache), registers)
    state = fetch("myndighetsregistret", lambda: myndighetsregistret.fetch(cache), registers)
    statskontoret_data = fetch("statskontoret", lambda: statskontoret.fetch(cache), registers)
    history, listing = statskontoret_data.get("register", {}), statskontoret_data.get("list", {})

    wanted = set(state) | set(listing) | {n for entry in history.values() for n in entry["orgnr"]}
    for uri, row in list(portal.get("registry", {}).items()) + list(portal.get("publishers", {}).items()) + list(europa.items()):
        for value in (uri, row.get("identifier")):
            if (n := orgnr(value)):
                wanted.add(n)
    wanted |= {row["orgnr"] for row in wd.values() if row.get("orgnr")}
    wanted |= {orgnr(key) for key in edits["organisation"] if orgnr(key)}
    scb = fetch("scb_bulk", lambda: scb_bulk.fetch(cache, wanted=frozenset(wanted)), registers)

    orgs, labels = {}, {}

    def rec(number, suffix=""):
        key = org_id(number) + suffix
        return orgs.setdefault(key, {"id": key, "label": {}, "status": "unknown", "identifier": {"orgnr": number}, "source": []})

    def label(r, lang, value, source, priority=None):
        if value:
            labels.setdefault(r["id"], {}).setdefault(lang, []).append(
                (LABEL_PRIORITY[source] if priority is None else priority, value))

    def alias(r, *values):
        merged = set(r.get("alias", [])) | {v for v in values if v}
        if merged:
            r["alias"] = sorted(merged, key=lambda v: (v.casefold(), v))

    def same_as(r, *uris):
        own = canonical(r["identifier"]["orgnr"], r["id"][12:]) if "orgnr" in r["identifier"] else None
        extra = {u for u in uris if u and u != own}
        if extra:
            r["same_as"] = sorted(set(r.get("same_as", [])) | extra)

    for number, row in scb.items():
        r = rec(number)
        r["registered_label"] = row["name"]
        label(r, "sv", title(row["name"]), "scb_bulk")
        r["status"] = "active" if row["jestat"] in ("1", "2") and row["ftgstat"] != "9" else "deregistered"
        r["legal_type"] = {"code": row["legal_form"], "label": scb_bulk.LEGAL_FORMS.get(row["legal_form"], "")}
        if row["legal_form"] in LEGAL_TYPE_TO_TYPE:
            r["type"] = LEGAL_TYPE_TO_TYPE[row["legal_form"]]
        if row["registered"]:
            r["established"] = row["registered"]
        r["source"].append("scb_bulk")

    for number, row in state.items():
        r = rec(number)
        label(r, "sv", title(row["name"]), "myndighetsregistret")
        r["state_body_group"] = row["group"]
        if row["sfs"]:
            r["sfs"] = row["sfs"]
        if row["web"]:
            r.setdefault("homepage", row["web"] if row["web"].startswith("http") else "https://" + row["web"])
        if row["email"]:
            r.setdefault("email", row["email"])
        r["source"].append("myndighetsregistret")

    # Statskontoret: every name a state body has carried under each of its numbers,
    # the number that replaced an earlier one, and where a wound-up body went.
    current_year = max((entry["last_year"] for entry in history.values()), default=0)
    by_name, by_id, owner = {}, {}, {}
    for lopnr, entry in history.items():
        for name in entry["name"].values():
            by_name[name.casefold()] = lopnr
        for ident in entry["id"]:
            by_id[ident] = lopnr
        for number, (first, last) in entry["orgnr"].items():
            # A number used by several running numbers (Polisen and Säkerhetspolisen shared
            # one until 2005) belongs to the one that used it last; the others only add aliases.
            if last >= owner.get(number, (0, ""))[0]:
                owner[number] = (last, lopnr)

    def heir(target, year):
        """The target's number in use in ``year``, else its latest number."""
        spans = history[target]["orgnr"]
        return next((n for n, (first, last) in spans.items() if first <= year <= last), max(spans, key=spans.get))

    for lopnr, entry in history.items():
        numbers = list(entry["orgnr"])
        for position, (number, (first, last)) in enumerate(entry["orgnr"].items()):
            r = rec(number)
            names = [n for y, n in entry["name"].items() if first <= int(y) <= last]
            if owner[number][1] != lopnr:
                # Names from a borrowed number are aliases only when this body never
                # moved on to a number of its own (Säkerhetspolisen did; MIA did not).
                if number == numbers[-1]:
                    alias(r, *names)
                continue
            label(r, "sv", names[-1], "statskontoret")
            alias(r, *(n for n in names[:-1] if n != names[-1]))
            if position + 1 < len(numbers):
                r["succeeded_by"] = sorted(set(r.get("succeeded_by", [])) | {org_id(numbers[position + 1])})
            elif last == entry["last_year"]:
                if entry["en"] and entry["en"] != "?":
                    # Their English names are old and uneven; only fill where Wikidata has none.
                    label(r, "en", entry["en"], "statskontoret", priority=LABEL_PRIORITY["wikidata"] + 0.5)
                if entry["email"]:
                    r.setdefault("email", entry["email"])
                if entry["department"] and last == current_year:
                    r["department"] = entry["department"]
            r["source"].append("statskontoret")
        if not entry["successor"] or not numbers or owner[numbers[-1]][1] != lopnr:
            continue
        heirs = {heir(target, entry["last_year"]) for target in statskontoret.resolve(entry["successor"], by_name, by_id)}
        heirs -= set(numbers)
        if heirs:
            r = rec(numbers[-1])
            r["succeeded_by"] = sorted(set(r.get("succeeded_by", [])) | {org_id(n) for n in heirs})

    # Statskontoret's yearly list: abbreviation or former name, instruction and department
    # for every current state body that is its own legal unit.
    for number, row in listing.items():
        r = rec(number)
        label(r, "sv", row["name"], "statskontoret")
        alias(r, *row["alias"])
        if row["sfs"]:
            r.setdefault("sfs", row["sfs"])
        if row["department"]:
            r.setdefault("department", row["department"])
        if "statskontoret" not in r["source"]:
            r["source"].append("statskontoret")

    links_portal, links_europa, links_wd = {}, {}, {}
    for uri, row in portal.get("registry", {}).items():
        number = orgnr(uri) or orgnr(row.get("identifier"))
        if not number:
            links_portal[uri] = None
            continue
        r = rec(number, suffix_of(uri))
        for lang, value in row["names"].items():
            label(r, lang, value, "dataportal")
        if row.get("type"):
            r.setdefault("type", row["type"])
        if row.get("homepage"):
            r.setdefault("homepage", row["homepage"])
        if row.get("email"):
            r.setdefault("email", row["email"])
        r["identifier"]["dataportal"] = canonical(number, suffix_of(uri))
        same_as(r, uri, *row.get("same_as", []))
        r["source"].append("dataportal")
        links_portal[uri] = r["id"]
    for uri, row in portal.get("publishers", {}).items():
        number = orgnr(uri) or orgnr(row.get("identifier"))
        links_portal.setdefault(uri, (org_id(number) + suffix_of(uri)) if number else None)
        if number:
            r = rec(number, suffix_of(uri))
            r["identifier"].setdefault("dataportal", canonical(number, suffix_of(uri)))
            same_as(r, uri)
            if "dataportal" not in r["source"]:
                r["source"].append("dataportal")

    for uri, row in europa.items():
        number = orgnr(uri) or orgnr(row.get("identifier"))
        links_europa[uri] = (org_id(number) + suffix_of(uri)) if number else None
        if not number:
            continue
        r = rec(number, suffix_of(uri))
        for lang, value in row["names"].items():
            label(r, lang, value, "data_europa")
        if row.get("type"):
            r.setdefault("type", row["type"].rsplit("/", 1)[-1])
        if row.get("homepage"):
            r.setdefault("homepage", row["homepage"])
        r["identifier"].setdefault("dataportal", canonical(number, suffix_of(uri)))
        same_as(r, uri, *row.get("same_as", []))
        r["source"].append("data_europa")

    qid_to_id = {qid: org_id(row["orgnr"]) for qid, row in wd.items() if row.get("orgnr")}
    for qid, row in wd.items():
        links_wd[qid] = qid_to_id.get(qid)
        if not row.get("orgnr"):
            continue
        r = rec(row["orgnr"])
        label(r, "sv", row["label"], "wikidata")
        if row.get("label_en"):
            label(r, "en", row["label_en"], "wikidata")
        r["identifier"]["wikidata"] = qid
        if row.get("riksarkivet"):
            r["identifier"]["riksarkivet"] = row["riksarkivet"]
        if row.get("kommunkod"):
            r["code"] = {"kommun": row["kommunkod"], "lan": row["kommunkod"][:2]}
        if row.get("department"):
            r.setdefault("department", row["department"])
        if row.get("inception"):
            r.setdefault("established", row["inception"][:10])
        if row.get("dissolved"):
            r["dissolved"] = row["dissolved"][:10]
            if r["status"] == "unknown":
                r["status"] = "deregistered"
        # "replaced by" on a body that still exists records a split-off, not a successor.
        succ = [qid_to_id[q] for q in row["replaced_by"] if q in qid_to_id] if row.get("dissolved") or r["status"] == "deregistered" else []
        if succ:
            r["succeeded_by"] = sorted(set(r.get("succeeded_by", [])) | set(succ))
        r["source"].append("wikidata")

    for key, patch in edits["organisation"].items():
        r = orgs.setdefault(key, {"id": key, "label": {}, "status": "unknown", "identifier": {}, "source": []})
        for field, value in patch.items():
            if field == "label":
                for lang, v in value.items():
                    label(r, lang, v, "edits")
            elif field == "identifier":
                r["identifier"].update(value)
            elif field == "same_as":
                same_as(r, *value)
                for uri in value:
                    links_europa[uri] = key
                    links_portal.setdefault(uri, key)
            elif field == "alias":
                alias(r, *value)
            else:
                r[field] = value
        r["source"].append("edits")

    for r in orgs.values():
        r["source"] = sorted(set(r["source"]))
        for lang, candidates in labels.get(r["id"], {}).items():
            r["label"].setdefault(lang, min(candidates)[1])
        if not r["label"]:
            r["label"]["sv"] = r.get("registered_label") or r["id"]
        losers = {v.strip() for p, v in labels.get(r["id"], {}).get("sv", [])
                  if p <= LABEL_PRIORITY["myndighetsregistret"] and v.strip().casefold() != r["label"]["sv"].casefold()}
        if losers:
            alias(r, *losers)
        if "-" in r["id"] and "part_of" not in r:
            r["part_of"] = r["id"].split("-")[0]

    orgs = dict(sorted(orgs.items()))
    # "generated" is the date of the last content change, so an unchanged registry stays byte-identical.
    generated = previous_output.get("generated", report["date"]) if orgs == previous else report["date"]
    dump(OUTPUT, {"generated": generated, "count": len(orgs), "organisation": orgs})
    dump(ROOT / "links" / "dataportal.json", dict(sorted(links_portal.items())))
    dump(ROOT / "links" / "data-europa.json", dict(sorted(links_europa.items())))
    dump(ROOT / "links" / "wikidata.json", dict(sorted(links_wd.items())))

    added = sorted(set(orgs) - set(previous))
    removed = sorted(set(previous) - set(orgs))
    changed = sorted(k for k in set(orgs) & set(previous) if orgs[k] != previous[k])
    report.update({"count": len(orgs), "added": added, "removed": removed, "changed": len(changed),
                   "legal_type": dict(Counter(r.get("legal_type", {}).get("code", "none") for r in orgs.values()))})
    # A stale register is normal operation (statskontoret.se never answers the runner); only a
    # content change or a register with no snapshot at all is worth a report commit.
    trouble = any(v["status"] == "failed" for v in registers.values())
    if added or removed or changed or trouble:
        dump(ROOT / "reports" / f"{report['date']}.json", report)
    print(f"{len(orgs)} organisations: +{len(added)} -{len(removed)} ~{len(changed)}; "
          + ", ".join(f"{k} {v['status']}" for k, v in registers.items()), file=sys.stderr)
    sys.exit(2 if all(v["status"] == "failed" for v in registers.values()) else 0)


if __name__ == "__main__":
    main()
