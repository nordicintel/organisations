"""SCB Myndighetsregistret TSV exports (state bodies in five groups with organisationsnummer).

Several bodies can share one number: the 80 courts are listed under Domstolsverket's. The
first row for a number is kept as its entry and every further row goes under ``unit``.
"""
import csv
import io
import json
import urllib.parse
from pathlib import Path

from .common import cached, http, orgnr

BASE = "https://myndighetsregistret.scb.se"
GROUPS = {
    "forvaltningsmyndighet": "Statliga förvaltningsmyndigheter",
    "riksdag": "Myndigheter under riksdagen",
    "affarsverk": "Statliga affärsverk",
    "ap_fond": "AP-fonder",
    "domstol": "Sveriges domstolar samt Domstolsverket",
}


def _download(label):
    q = urllib.parse.urlencode({"format": "false", "myndgrupp": label})
    path = json.loads(http(f"{BASE}/Myndighet/PrepareDownload?{q}"))
    return http(BASE + urllib.parse.quote(path, safe="/?=&"))


def fetch(cache: Path):
    out = {}
    for group, label in GROUPS.items():
        path = cached(cache, f"myndighetsregistret_{group}.tsv", lambda label=label: _download(label))
        text = path.read_bytes().decode("utf-8-sig")
        for r in csv.DictReader(io.StringIO(text), delimiter="\t"):
            number = orgnr(r.get("Organisationsnr"))
            if not number:
                continue
            row = {
                "name": (r.get("Namn") or "").strip(),
                "group": group,
                "sfs": (r.get("SFS") or "").strip(),
                "email": (r.get("Epost") or "").strip(),
                "web": (r.get("Webbadress") or "").strip(),
            }
            if number in out:
                out[number].setdefault("unit", []).append(row)
            else:
                out[number] = row
    return out
