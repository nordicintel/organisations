"""SCB:s allmänna företagsregister, bulk file hosted by Bolagsverket (weekly, no key).

Keeps every public-sector legal form plus any organisation number in ``wanted``.
"""
import csv
import io
import zipfile
from pathlib import Path

from .common import cached, http, skip

URL = "https://vardefulla-datamangder.bolagsverket.se/scb/scb_bulkfil.zip"
PUBLIC_FORMS = {"81", "82", "83", "84", "85", "87", "88", "89"}
LEGAL_FORMS = {
    "10": "Fysisk person", "21": "Enkelt bolag", "22": "Partrederi", "23": "Värdepappersfond",
    "31": "Handelsbolag/kommanditbolag", "32": "Gruvbolag", "41": "Bankaktiebolag", "42": "Försäkringsaktiebolag",
    "43": "Europabolag", "49": "Övriga aktiebolag", "51": "Ekonomisk förening", "53": "Bostadsrättsförening",
    "54": "Kooperativ hyresrättsförening", "55": "Europakooperativ", "61": "Ideell förening", "62": "Samfällighet",
    "63": "Registrerat trossamfund", "71": "Familjestiftelse", "72": "Övrig stiftelse", "81": "Statlig enhet",
    "82": "Kommun", "83": "Kommunalförbund", "84": "Region", "85": "Allmän försäkringskassa",
    "87": "Offentlig korporation eller anstalt", "88": "Hypoteksförening", "89": "Regional statlig myndighet",
    "91": "Oskiftat dödsbo", "92": "Ömsesidigt försäkringsbolag", "93": "Sparbank", "94": "Understödsförening",
    "95": "Arbetslöshetskassa", "96": "Utländsk juridisk person", "98": "Övriga svenska juridiska personer", "99": "Ej specificerad",
}


def fetch(cache: Path, wanted=frozenset()):
    path = cached(cache, "scb_bulkfil.zip", lambda: http(URL))
    rows = {}
    with zipfile.ZipFile(path) as z:
        name = next(n for n in z.namelist() if n.endswith(".txt"))
        with z.open(name) as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="cp1252", newline=""), delimiter="\t")
            for r in reader:
                try:
                    pe = (r.get("PeOrgNr") or "").strip()
                    if len(pe) != 12 or not pe.startswith("16"):
                        continue  # sole traders and other personal identities are out of scope
                    number = pe[2:]
                    form = (r.get("JurForm") or "").strip()
                    if form not in PUBLIC_FORMS and number not in wanted:
                        continue
                    rows[number] = {
                        "name": (r.get("Namn") or r.get("Foretagsnamn") or "").strip(),
                        "legal_form": form,
                        "ftgstat": (r.get("FtgStat") or "").strip(),
                        "jestat": (r.get("JEStat") or "").strip(),
                        "registered": _iso((r.get("RegDatKtid") or "").strip()),
                        "postort": (r.get("PostOrt") or "").strip(),
                    }
                except Exception as error:  # noqa: BLE001
                    skip("scb_bulk", r, error)
    return rows


def _iso(value):
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}" if len(value) == 8 and value.isdigit() else value
