import gzip
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

UA = "nordicintel-organisations/0.1 (+https://github.com/nordicintel/organisations)"


def http(url, *, data=None, headers=None, timeout=600):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        return gzip.decompress(body) if resp.headers.get("Content-Encoding") == "gzip" else body


def cached(cache: Path, name: str, producer):
    path = cache / name
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"fetching {name}", file=sys.stderr)
        path.write_bytes(producer())
    return path


def sparql(endpoint, query, *, timeout=600):
    body = urllib.parse.urlencode({"query": query}).encode()
    raw = http(endpoint, data=body, headers={"Accept": "application/sparql-results+json",
                                             "Content-Type": "application/x-www-form-urlencoded"}, timeout=timeout)
    return json.loads(raw)["results"]["bindings"]


def orgnr(value):
    """Return the 10 digits of a Swedish organisationsnummer found in ``value``, or None."""
    if not value:
        return None
    m = re.search(r"(?<!\d)(?:16)?(\d{6})-?(\d{4})(?!\d)", str(value))
    return m.group(1) + m.group(2) if m else None


def org_id(number):
    return f"SE{number}" if number else None
