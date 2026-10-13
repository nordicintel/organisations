"""Statskontoret's yearly list of all state bodies (myndighetsförteckningen), read from
the one Excel file kept in this repository: ``files/myndighetsforteckning.xlsx``.

statskontoret.se does not answer GitHub runners or cloud sessions, so the file is
downloaded by hand from
https://www.statskontoret.se/analys-och-statistik/oppna-data/myndighetsforteckning/
and replaced in place once a year. The build reads whatever edition is there.

The file has a sheet per edition ("Förteckning 2026") and one with every year since
2007 ("Förteckning 2007-2026"). Each row is a body in that year: organisationsnummer,
name, abbreviation or former name, instruction (SFS), department, and, for a nämnd
hosted by another body, the host. Courts appear only as groups (48 tingsrätter) under
Domstolsverket's number and are left to Myndighetsregistret. The reduced result:

    {"year": 2026,
     "list": {"2021005448": {"name": "Skatteverket", "alias": ["SKV"], "sfs": "2017:154",
                             "department": "Finansdepartementet"}},
     "history": {"2021005448": {"name": {"2007": "Skatteverket", ...}, "first": 2007, "last": 2026}}}

``list`` is the current edition for bodies that are their own legal unit; a number
used by several rows (none today once the court groups are skipped) keeps the
further rows under ``unit``. ``history`` gives every name a number has carried since
2007, so renamed bodies keep their earlier names as aliases.
"""
import re
from pathlib import Path

import openpyxl

from .common import orgnr

FILE = Path(__file__).resolve().parents[2] / "files" / "myndighetsforteckning.xlsx"


def sheets(path: Path):
    """(sheet name, rows as dicts keyed by the header row) for every sheet, cells as stripped text."""
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    for sheet in book.worksheets:
        rows = [["" if v is None else str(v).strip() for v in row] for row in sheet.iter_rows(values_only=True)]
        header = rows[0] if rows else []
        yield sheet.title, [dict(zip(header, r)) for r in rows[1:] if any(r)]


def luhn(number):
    digits = [int(d) for d in number]
    total = sum(d if i % 2 else (d * 2 - 9 if d * 2 > 9 else d * 2) for i, d in enumerate(digits))
    return total % 10 == 0


def valid_orgnr(value):
    """The list carries group placeholders such as 2021002745 for all tingsrätter; keep only checksum-valid numbers."""
    number = orgnr(value)
    return number if number and luhn(number) else None


def _row(r):
    aliases = [a.strip() for a in re.sub(r"\s*\(gammalt namn\)", "", r.get("alternativt_namn", "")).split("/")]
    return {"name": r.get("myndighet", "").strip(),
            "alias": sorted(a for a in aliases if a and a != r.get("myndighet", "").strip()),
            "sfs": r.get("sfs", "").strip(), "department": r.get("departement", "").strip()}


def fetch(path: Path = FILE):
    tables = dict(sheets(path))
    editions = sorted(int(n[-4:]) for n in tables if re.fullmatch(r"Förteckning \d{4}", n))
    if not editions:
        raise ValueError(f"{path.name}: no 'Förteckning <year>' sheet")
    year = editions[-1]
    out = {"year": year, "list": {}, "history": {}}
    for r in tables[f"Förteckning {year}"]:
        number = valid_orgnr(r.get("orgnr"))
        if not number or r.get("värdmyndighet") or r.get("antal", "1") != "1":
            continue
        row = _row(r)
        if number in out["list"]:
            out["list"][number].setdefault("unit", []).append(row)
        else:
            out["list"][number] = row
    span = next((n for n in tables if re.fullmatch(r"Förteckning \d{4}-\d{4}", n)), "")
    rows = [r for r in tables.get(span, []) if valid_orgnr(r.get("orgnr")) and not r.get("värdmyndighet")
            and r.get("antal", "1") == "1" and r.get("år", "").isdigit()]
    # A number several bodies carry in one year (Domstolsverket's) has no history of its own.
    seen, shared = set(), set()
    for r in rows:
        key = (valid_orgnr(r["orgnr"]), r["år"])
        (shared if key in seen else seen).add(key[0] if key in seen else key)
    for r in rows:
        number = valid_orgnr(r.get("orgnr"))
        if number in shared:
            continue
        entry = out["history"].setdefault(number, {"name": {}, "first": int(r["år"]), "last": int(r["år"])})
        entry["name"][r["år"]] = r.get("myndighet", "").strip()
        entry["first"], entry["last"] = min(entry["first"], int(r["år"])), max(entry["last"], int(r["år"]))
    for entry in out["history"].values():
        entry["name"] = dict(sorted(entry["name"].items()))
    out["list"] = dict(sorted(out["list"].items()))
    out["history"] = dict(sorted(out["history"].items()))
    return out
