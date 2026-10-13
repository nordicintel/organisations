"""Statskontoret's register of state bodies in the state accounting organisation,
all years (one Excel sheet per year since 1999, plus a glossary sheet), and its
yearly list of all state bodies (myndighetsförteckningen).

Each row is a body in that year with a running number (LöpNr) that survives renames
and even organisationsnummer changes, a short register identity (MyndID), the
organisationsnummer, department, English name, contact details and a free-text
comment that says where a wound-up body went. The reduced result is keyed by
running number:

    {"1128": {"name": {"1999": "Riksskatteverket", "2004": "Skatteverket", ...},
              "en": "Swedish Tax Agency", "id": ["RSV", "SKV"], "department": "Finansdepartementet",
              "email": "...", "orgnr": {"2021000985": [1999, 2003], "2021005448": [2004, 2026]},
              "successor": "Ekonomistyrningsverket", "last_year": 2026}}

``orgnr`` maps every valid organisationsnummer the running number has carried to its
first and last year, ``id`` lists its register identities in order of first use, and
``successor`` is the body named in the last year's comment.

The yearly list adds, keyed by organisationsnummer, what the register lacks: the
abbreviation or former name, the SFS number of the instruction and the department,
for bodies that are their own legal unit (hosted nämnder carry the host's number
and are skipped). Only the current year is used; earlier years reuse numbers
unreliably. ``fetch`` returns ``{"register": ..., "list": ...}``.
"""
import difflib
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from .common import cached, http, orgnr

URL = ("https://www.statskontoret.se/kunskapsstod-och-regler/rapportering/"
       "myndighetsregistret/exportexcelallaarmyndigheter")
LIST_PAGE = "https://www.statskontoret.se/analys-och-statistik/oppna-data/myndighetsforteckning/"
# The folder hash and year change with every edition, so the link is read off the page.
LIST_LINK = re.compile(r"contentassets/[0-9a-f]+/statskontorets-myndighetsforteckning-(\d{4})\.xlsx[^\"']*")
HEADERS = {"Accept-Encoding": "gzip"}
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
# "the activity moves to X": every phrasing seen in the comments 1999-2026.
TRANSFER = (
    r"(?:överförs till och inordnas i|inordna(?:s|d)(?: from \d{4})? (?:i|under|inom)|"
    r"överför(?:s|ts|des) till|förs över till|uppg(?:år|ick) i|g(?:år|ick) in i|"
    r"överg(?:år|ick|\.?) (?:till|t\.?|tl)|överf\.? t\.?|övergår till|övertas av|"
    r"övertagits(?: i sin helhet)? av|ersätts av|finns nu(?: inordnad under| inom)|"
    r"ingår nu i|sammanslås med|slås samman med)"
)
FILLER = r"(?:den (?:nya|nystartade) myndighet(?:en)?|myndighet)\s+"
SUCCESSOR = re.compile(
    TRANSFER + r"\s+(?:" + FILLER + r")?(?P<name>.+?)"
    r"(?=\s+(?:per|fr\.?o\.?m\.?|from|från|den|med|som|i samband)\b|\s+\d{4}|\s*\(|\.\s|\.$|$)", re.I)
ABBREVIATION = re.compile(r"\((?P<abbr>[A-ZÅÄÖ]{2,8})\)")
SPLIT = re.compile(r"\s+(?:och|samt)\s+")
FIRST_YEAR = 1999


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


def luhn(number):
    digits = [int(d) for d in number]
    total = sum(d if i % 2 else (d * 2 - 9 if d * 2 > 9 else d * 2) for i, d in enumerate(digits))
    return total % 10 == 0


def valid_orgnr(value):
    """The register carries placeholders such as 210000-9999; keep only checksum-valid numbers."""
    number = orgnr(value)
    return number if number and luhn(number) else None


def successor(comment):
    """The body a comment says the activity moved to, with any bracketed abbreviation kept."""
    text = re.sub(r"\s+", " ", comment or "").strip()
    if not text or re.search(r"\bdelar av\b", text, re.I):
        return ""
    m = SUCCESSOR.search(text)
    if not m:
        return ""
    name = m.group("name").strip(" .")
    abbr = ABBREVIATION.match(text[m.end():].lstrip())
    return f"{name} ({abbr.group('abbr')})" if abbr else name


def resolve(phrase, by_name, by_id, cutoff=0.88):
    """Running numbers a successor phrase refers to.

    ``by_name`` and ``by_id`` map casefolded names and register identities (any year)
    to running numbers. Whole phrase first (exact name, bracketed or bare abbreviation, then the
    closest name or abbreviation above ``cutoff``), then "X och Y" split at each
    conjunction as soon as both halves resolve.
    """
    phrase = phrase.strip()
    if not phrase:
        return []
    m = ABBREVIATION.search(phrase)
    name = phrase[:m.start()].strip() if m else phrase
    key = name.casefold()
    if key in by_name:
        return [by_name[key]]
    for abbr in ([m.group("abbr")] if m else []) + [name.upper()]:
        if abbr in by_id:
            return [by_id[abbr]]
        if (close := difflib.get_close_matches(abbr, by_id, 1, cutoff)):
            return [by_id[close[0]]]
    if (close := difflib.get_close_matches(key, by_name, 1, cutoff)):
        return [by_name[close[0]]]
    for part in SPLIT.finditer(name):
        left = resolve(name[:part.start()], by_name, by_id, cutoff)
        right = resolve(name[part.end():], by_name, by_id, cutoff)
        if left and right:
            return left + right
    return []


def fetch(cache: Path):
    return {"register": register(cache), "list": listing(cache)}


def register(cache: Path):
    # The server answers 404 to any request that sends "Accept-Encoding: identity",
    # which urllib does by default; asking for gzip is what makes the export work.
    data = cached(cache, "statskontoret.xlsx", lambda: http(URL, headers=HEADERS)).read_bytes()
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
            entry = out.setdefault(lopnr, {"name": {}, "en": "", "id": [], "department": "", "email": "",
                                           "orgnr": {}, "successor": "", "last_year": 0})
            entry["name"][str(year)] = agency
            if r.get("MyndID") and r["MyndID"] not in entry["id"]:
                entry["id"].append(r["MyndID"])
            number = valid_orgnr(r.get("OrgNr"))
            if number:
                span = entry["orgnr"].setdefault(number, [year, year])
                span[0], span[1] = min(span[0], year), max(span[1], year)
            if year >= entry["last_year"]:
                entry["last_year"] = year
                entry["successor"] = successor(r.get("Kommentar", ""))
                entry["en"] = r.get("Engelskt namn", "")
                entry["department"] = r.get("Departement", "")
                entry["email"] = r.get("Epost", "").lower()
    for entry in out.values():
        entry["name"] = dict(sorted(entry["name"].items()))
        entry["orgnr"] = dict(sorted(entry["orgnr"].items(), key=lambda kv: kv[1]))
    return dict(sorted(out.items(), key=lambda kv: int(kv[0])))


def _list_url():
    page = http(LIST_PAGE, headers=HEADERS).decode("utf-8", "replace")
    links = list(LIST_LINK.finditer(page))
    if not links:
        raise ValueError("no myndighetsforteckning link on the page")
    return "https://www.statskontoret.se/" + max(links, key=lambda m: m.group(1)).group(0)


def listing(cache: Path):
    data = cached(cache, "myndighetsforteckning.xlsx", lambda: http(_list_url(), headers=HEADERS)).read_bytes()
    current = max((n for n, _ in sheets(data) if n.startswith("Förteckning ") and n[-4:].isdigit()), default="")
    rows = next((rows for name, rows in sheets(data) if name == current), [])
    # Courts all carry Domstolsverket's number; a number used by several rows names none of them.
    shared = {n for n in (valid_orgnr(r.get("orgnr")) for r in rows) if n}
    shared = {n for n in shared if sum(valid_orgnr(r.get("orgnr")) == n for r in rows) > 1}
    out = {}
    for r in rows:
        number = valid_orgnr(r.get("orgnr"))
        if not number or number in shared or r.get("värdmyndighet") or r.get("antal", "1") != "1":
            continue
        aliases = [a.strip() for a in re.sub(r"\s*\(gammalt namn\)", "", r.get("alternativt_namn", "")).split("/")]
        out[number] = {"name": r.get("myndighet", ""),
                       "alias": sorted(a for a in aliases if a and a != r.get("myndighet", "")),
                       "sfs": r.get("sfs", ""), "department": r.get("departement", "")}
    return dict(sorted(out.items()))
