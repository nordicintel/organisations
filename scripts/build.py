"""Build organisations.json, links/ and a report from the registers and edits/.

Usage: python scripts/build.py [--cache DIR]

Each register is fetched into the cache and reduced to a small snapshot in
snapshots/<register>.json, which is committed. When a register cannot be
fetched, the committed snapshot is used instead and the report says so. One
register failing never stops the build.
"""
import argparse
import difflib
import unicodedata
import json
import re
import sys
import traceback
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import export  # noqa: E402
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
        rows = sum(len(v) for v in data.values() if isinstance(v, dict)) if name in ("dataportal", "statskontoret") else len(data)
        report[name] = {"status": "fetched", "rows": rows}
        if "year" in data:
            report[name]["edition"] = data["year"]
        return data
    except Exception as error:  # noqa: BLE001 - any failure must not stop the build
        print(f"{name}: {error}", file=sys.stderr)
        traceback.print_exc()
        data = load(path, {})
        rows = sum(len(v) for v in data.values() if isinstance(v, dict)) if name in ("dataportal", "statskontoret") else len(data)
        report[name] = {"status": "stale" if data else "failed", "rows": rows, "error": str(error)[:200]}
        return data


def canonical(number, suffix=""):
    return f"http://dataportal.se/organisation/SE{number}{suffix}"


def suffix_of(uri):
    m = re.search(r"organisation/(?:SE)?\d{10}(-[A-Z0-9]+)", uri or "")
    return m.group(1) if m else ""


SMALL_WORDS = {"i", "och", "för", "över", "o", "av", "med", "till", "under", "på"}


def title(value):
    """Registered names come in capitals; title-case them, keeping Swedish particles lower."""
    if not value.isupper():
        return value
    words = value.title().split(" ")
    return " ".join(w.lower() if i and w.lower() in SMALL_WORDS else w for i, w in enumerate(words))


def suffix_for(body):
    """An id suffix for a body listed under another body's number: from its own mailbox when it has
    one (alingsas.tingsratt@dom.se → -ALINGSAS-TINGSRATT), else from its name, in ASCII capitals."""
    source = body["email"].split("@")[0] if body.get("email") else body["name"]
    folded = unicodedata.normalize("NFKD", source).encode("ascii", "ignore").decode().upper()
    return "-" + "-".join(re.findall(r"[A-Z0-9]+", folded))


def same_body(a, b):
    """Whether two register names denote one body: equal, or one is the start of the other
    (Myndighetsregistret cuts names at 48 characters)."""
    a, b = a.casefold().strip(), b.casefold().strip()
    return bool(a and b) and (a == b or a.startswith(b) or b.startswith(a))


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
    statskontoret_data = fetch("statskontoret", statskontoret.fetch, registers)
    history, listing = statskontoret_data.get("history", {}), statskontoret_data.get("list", {})

    wanted = set(state) | set(listing) | set(history)
    for uri, row in list(portal.get("registry", {}).items()) + list(portal.get("publishers", {}).items()) + list(europa.items()):
        for value in (uri, row.get("identifier")):
            if (n := orgnr(value)):
                wanted.add(n)
    wanted |= {row["orgnr"] for row in wd.values() if row.get("orgnr")}
    wanted |= {orgnr(key) for key in edits["organisation"] if orgnr(key)}
    scb = fetch("scb_bulk", lambda: scb_bulk.fetch(cache, wanted=frozenset(wanted)), registers)

    orgs, labels = {}, {}
    skipped = Counter()

    def skip(register, key, error):
        skipped[register] += 1
        print(f"{register} {key}: skipped, {type(error).__name__}: {error}", file=sys.stderr)

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
        try:
            r = rec(number)
            r["registered_label"] = row["name"]
            label(r, "sv", title(row["name"]), "scb_bulk")
            r["status"] = "active" if row["jestat"] in ("1", "2") and row["ftgstat"] != "9" else "deregistered"
            r["legal_type"] = {"code": row["legal_form"], "label": scb_bulk.LEGAL_FORMS.get(row["legal_form"], "")}
            if row["legal_form"] in LEGAL_TYPE_TO_TYPE:
                r["organisation_type"] = LEGAL_TYPE_TO_TYPE[row["legal_form"]]
            if row["registered"]:
                r["established"] = row["registered"]
            r["source"].append("scb_bulk")
        except Exception as error:  # noqa: BLE001 - one bad row must not cost the register
            skip("scb_bulk", number, error)

    # Bodies sharing one number (the courts, all under Domstolsverket's) are each their own
    # organisation with a suffixed id and the legal unit as parent. The legal unit is the row
    # named as SCB registers the number, else the register's first row. Statskontoret's rows
    # for the same number are matched to Myndighetsregistret's by name and share the id.
    units = {}

    def unit_id(number, body):
        for suffix, known in units.get(number, {}).items():
            if same_body(known, body["name"]):
                return suffix
        suffix = suffix_for(body)
        units.setdefault(number, {})[suffix] = body["name"]
        return suffix

    legal_name = {}  # the legal unit's name per shared number, as Myndighetsregistret lists it first

    for number, row in state.items():
        try:
            bodies = [row] + row.get("unit", [])
            registered = scb.get(number, {}).get("name", "").casefold()
            legal = next((b for b in bodies if b["name"].casefold() == registered), bodies[0])
            legal_name[number] = legal["name"].casefold()
            for body in bodies:
                r = rec(number, "" if body is legal else unit_id(number, body))
                label(r, "sv", title(body["name"]), "myndighetsregistret")
                r["state_body_group"] = body["group"]
                if body is not legal:
                    r["organisation_type"] = "NationalAuthority"
                    r["status"] = orgs[org_id(number)]["status"] if org_id(number) in orgs else "unknown"
                if body["sfs"]:
                    r["sfs"] = body["sfs"]
                if body["web"]:
                    r.setdefault("homepage", body["web"] if body["web"].startswith("http") else "https://" + body["web"])
                if body["email"]:
                    r.setdefault("email", body["email"])
                r["source"].append("myndighetsregistret")
        except Exception as error:  # noqa: BLE001 - one bad row must not cost the register
            skip("myndighetsregistret", number, error)

    # Statskontoret's history sheet: every name a number has carried since 2007; earlier
    # names become aliases of the body that carries the number today.
    for number, entry in history.items():
        try:
            names = list(entry["name"].values())
            r = rec(number)
            if number not in listing:  # a body wound up since 2007: its last name and its earlier ones
                label(r, "sv", names[-1], "statskontoret")
                if "statskontoret" not in r["source"]:
                    r["source"].append("statskontoret")
            alias(r, *(n for n in names[:-1] if n != names[-1]))
        except Exception as error:  # noqa: BLE001 - one bad row must not cost the register
            skip("statskontoret", number, error)

    # Statskontoret's yearly list: abbreviation or former name, instruction and department
    # for every current state body that is its own legal unit.
    for number, row in listing.items():
        try:
            bodies = [row] + row.get("unit", [])
            known = {scb.get(number, {}).get("name", "").casefold(), legal_name.get(number, "")} - {""}
            legal = next((b for b in bodies if b["name"].casefold() in known), bodies[0]) if len(bodies) > 1 else row
            for body in bodies:
                r = rec(number, "" if body is legal else unit_id(number, body))
                label(r, "sv", body["name"], "statskontoret")
                alias(r, *body["alias"])
                if body is not legal:
                    r.setdefault("organisation_type", "NationalAuthority")
                    r.setdefault("state_body_group", state.get(number, {}).get("group", ""))
                    if r["status"] == "unknown" and org_id(number) in orgs:
                        r["status"] = orgs[org_id(number)]["status"]
                if body["sfs"]:
                    if body is legal:
                        r.setdefault("sfs", body["sfs"])
                    else:
                        r["sfs"] = body["sfs"]  # Myndighetsregistret gives every court its legal unit's instruction
                if body["department"]:
                    r.setdefault("department", body["department"])
                if "statskontoret" not in r["source"]:
                    r["source"].append("statskontoret")
        except Exception as error:  # noqa: BLE001 - one bad row must not cost the register
            skip("statskontoret", number, error)

    links_portal, links_europa, links_wd = {}, {}, {}
    for uri, row in portal.get("registry", {}).items():
        try:
            number = orgnr(uri) or orgnr(row.get("identifier"))
            if not number:
                links_portal[uri] = None
                continue
            r = rec(number, suffix_of(uri))
            for lang, value in row["names"].items():
                label(r, lang, value, "dataportal")
            if row.get("type"):
                r.setdefault("organisation_type", row["type"])
            if row.get("homepage"):
                r.setdefault("homepage", row["homepage"])
            if row.get("email"):
                r.setdefault("email", row["email"])
            r["identifier"]["dataportal"] = canonical(number, suffix_of(uri))
            same_as(r, uri, *row.get("same_as", []))
            r["source"].append("dataportal")
            links_portal[uri] = r["id"]
        except Exception as error:  # noqa: BLE001 - one bad row must not cost the register
            skip("dataportal", uri, error)
    for uri, row in portal.get("publishers", {}).items():
        try:
            number = orgnr(uri) or orgnr(row.get("identifier"))
            links_portal.setdefault(uri, (org_id(number) + suffix_of(uri)) if number else None)
            if number:
                r = rec(number, suffix_of(uri))
                r["identifier"].setdefault("dataportal", canonical(number, suffix_of(uri)))
                same_as(r, uri)
                if "dataportal" not in r["source"]:
                    r["source"].append("dataportal")
        except Exception as error:  # noqa: BLE001 - one bad row must not cost the register
            skip("dataportal", uri, error)

    for uri, row in europa.items():
        try:
            number = orgnr(uri) or orgnr(row.get("identifier"))
            links_europa[uri] = (org_id(number) + suffix_of(uri)) if number else None
            if not number:
                continue
            r = rec(number, suffix_of(uri))
            for lang, value in row["names"].items():
                label(r, lang, value, "data_europa")
            if row.get("type"):
                r.setdefault("organisation_type", row["type"].rsplit("/", 1)[-1])
            if row.get("homepage"):
                r.setdefault("homepage", row["homepage"])
            r["identifier"].setdefault("dataportal", canonical(number, suffix_of(uri)))
            same_as(r, uri, *row.get("same_as", []))
            r["source"].append("data_europa")
        except Exception as error:  # noqa: BLE001 - one bad row must not cost the register
            skip("data_europa", uri, error)

    qid_to_id = {qid: org_id(row["orgnr"]) for qid, row in wd.items() if row.get("orgnr")}

    # The courts share Domstolsverket's number, so Wikidata's court items are matched to the
    # suffixed records by name: equal, or one the start of the other, since Myndighetsregistret
    # cuts at 48 characters and appends the divisions ("Svea Hovrätt o Mark o Miljö och Patent").
    courts = {k: {v.casefold() for _, v in labels.get(k, {}).get("sv", [])}
              for k, r in orgs.items() if "-" in k and r.get("state_body_group") == "domstol"}

    def court_for(row):
        # The label first; the other names only when it finds nothing (Nacka tingsrätt lists
        # "Södertörns tingsrätt" among its alternative names and would otherwise hit both).
        for names in ({row["label"].casefold()}, {n.casefold() for n in row.get("names", [])}):
            hits = {k for k, known in courts.items() for a in known for b in names
                    if a == b or a.startswith(b + " ") or b.startswith(a + " ")}
            if hits:
                return next(iter(hits)) if len(hits) == 1 else None
        return None

    for qid, row in wd.items():
        try:
            links_wd[qid] = qid_to_id.get(qid)
            if not row.get("orgnr"):
                court = court_for(row) if row["kind"] == "domstol" else None
                if not court:
                    continue
                links_wd[qid] = court
                r = orgs[court]
                label(r, "sv", row["label"], "wikidata", LABEL_PRIORITY["statskontoret"])  # the one full, cased name
                if row.get("label_en"):
                    label(r, "en", row["label_en"], "wikidata")
                r["identifier"]["wikidata"] = qid
                # An alternative name that is another court's name (Nacka lists "Södertörns tingsrätt") stays out.
                alias(r, *(n for n in row.get("names", []) if court_for({"label": n}) in (court, None)))
                r["source"].append("wikidata")
                continue
            r = rec(row["orgnr"])
            label(r, "sv", row["label"], "wikidata")
            if row.get("label_en"):
                label(r, "en", row["label_en"], "wikidata")
            r["identifier"]["wikidata"] = qid
            alias(r, *row.get("names", []))  # former official names and alternative names, e.g. Stockholms läns landsting
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
        except Exception as error:  # noqa: BLE001 - one bad row must not cost the register
            skip("wikidata", qid, error)

    for key, patch in edits["organisation"].items():
        try:
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
        except Exception as error:  # noqa: BLE001 - one bad row must not cost the register
            skip("edits", key, error)

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
    try:
        export.export(OUTPUT, ROOT / "data_sources.json")
    except Exception as error:  # noqa: BLE001 - dist/ is derived; the product is already written
        print(f"export: {error}", file=sys.stderr)
        report["export"] = f"failed: {str(error)[:200]}"
    dump(ROOT / "links" / "dataportal.json", dict(sorted(links_portal.items())))
    dump(ROOT / "links" / "data-europa.json", dict(sorted(links_europa.items())))
    dump(ROOT / "links" / "wikidata.json", dict(sorted(links_wd.items())))

    added = sorted(set(orgs) - set(previous))
    removed = sorted(set(previous) - set(orgs))
    changed = sorted(k for k in set(orgs) & set(previous) if orgs[k] != previous[k])
    for register, n in skipped.items():
        registers.setdefault(register, {})["skipped"] = n
    report.update({"count": len(orgs), "added": added, "removed": removed, "changed": len(changed),
                   "legal_type": dict(Counter(r.get("legal_type", {}).get("code", "none") for r in orgs.values()))})
    # A stale register is normal operation (statskontoret.se never answers the runner); only a
    # content change or a register with no snapshot at all is worth a report commit.
    trouble = any(v.get("status") == "failed" or v.get("skipped") for v in registers.values()) or "export" in report
    if added or removed or changed or trouble:
        dump(ROOT / "reports" / f"{report['date']}.json", report)
    print(f"{len(orgs)} organisations: +{len(added)} -{len(removed)} ~{len(changed)}; "
          + ", ".join(f"{k} {v['status']}" for k, v in registers.items()), file=sys.stderr)
    sys.exit(2 if all(v.get("status") == "failed" for v in registers.values() if "status" in v) else 0)


if __name__ == "__main__":
    main()
