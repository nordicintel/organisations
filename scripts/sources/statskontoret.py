"""Statskontoret's agency register, all years (one Excel sheet per year since 1999).

Each row is an agency in that year with a running number (LöpNr) that survives
renames, the organisationsnummer where known, and a free-text comment that says
where a wound-up agency went. The reduced result is keyed by running number.
"""
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from .common import cached, http, orgnr

URL = ("https://www.statskontoret.se/kunskapsstod-och-regler/rapportering/"
       "myndighetsregistret/exportexcelallaarmyndigheter")
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "p": "http://schemas.openxmlformats.org/package/2006/relationships"}
SUCCESSOR = re.compile(
    r"(?:överförs till och inordnas i|inordnas (?:i|under)|överför(?:s|ts|des) till|"
    r"uppg(?:år|ick) i(?: den nya myndigheten)?|gick in i(?: myndigheten)?|"
    r"övergår till|övertas av|sammanslås med|slås samman med)\s+(?P<name>.+?)"
    r"(?=\s+(?:per|fr\.?o\.?m\.?|från|den|med|i samband)\b|\s+\d{4}|\s*\(|\.\s|\.$|$)", re.I)


def _column(ref):
    return re.match(r"[A-Z]+", ref).group(0)


def sheets(data: bytes):
    """Yield (sheet name, rows as list of dicts keyed by the header row) for every sheet."""
    z = zipfile.ZipFile(io.BytesIO(data))
    shared = [("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
              for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS)] \
        if "xl/sharedStrings.xml" in z.namelist() else []
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    for sheet in ET.fromstring(z.read("xl/workbook.xml")).find("m:sheets", NS):
        target = rels[sheet.get(f"{{{NS['r']}}}id")].lstrip("/")
        path = target if target.startswith("xl/") else "xl/" + target
        rows = []
        for row in ET.fromstring(z.read(path)).iter(f"{{{NS['m']}}}row"):
            cells = {}
            for c in row.findall("m:c", NS):
                v = c.find("m:v", NS)
                if c.get("t") == "s" and v is not None:
                    value = shared[int(v.text)]
                elif c.get("t") == "inlineStr":
                    value = "".join(t.text or "" for t in c.iter(f"{{{NS['m']}}}t"))
                else:
                    value = v.text if v is not None else ""
                cells[_column(c.get("r"))] = (value or "").strip()
            rows.append(cells)
        if not rows:
            continue
        header = {col: name for col, name in rows[0].items() if name}
        yield sheet.get("name"), [{header[c]: v for c, v in r.items() if c in header}
                                  for r in rows[1:] if any(r.values())]


def successor(comment):
    text = re.sub(r"\s+", " ", comment or "").strip()
    if not text or re.search(r"\bdelar av\b", text, re.I):
        return ""
    m = SUCCESSOR.search(text)
    return m.group("name").strip(" .") if m else ""


def fetch(cache: Path):
    data = cached(cache, "statskontoret.xlsx", lambda: http(URL)).read_bytes()
    out = {}
    for name, rows in sheets(data):
        if not name.isdigit():
            continue
        year = int(name)
        for r in rows:
            lopnr, agency = r.get("LöpNr", ""), r.get("Myndighet", "")
            if not lopnr or not agency:
                continue
            lopnr = lopnr.split(".")[0]
            entry = out.setdefault(lopnr, {"name": {}, "orgnr": [], "successor": "", "last_year": 0})
            entry["name"][str(year)] = agency
            number = orgnr(r.get("OrgNr"))
            if number and number not in entry["orgnr"]:
                entry["orgnr"].append(number)
            if year >= entry["last_year"]:
                entry["last_year"] = year
                entry["successor"] = successor(r.get("Kommentar", ""))
    return dict(sorted(out.items(), key=lambda kv: int(kv[0])))
