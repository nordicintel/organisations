import gzip
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = "nordicintel-organisations/0.1 (+https://github.com/nordicintel/organisations)"


RETRY_STATUS = {429, 500, 502, 503, 504}
BACKOFF = (10, 30, 60)  # seconds between attempts; a Retry-After header wins when it is longer


def http(url, *, data=None, headers=None, timeout=600, attempts=4):
    """GET or POST, retrying rate limits, gateway errors and network failures a few times."""
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
                return gzip.decompress(body) if resp.headers.get("Content-Encoding") == "gzip" else body
        except urllib.error.HTTPError as error:
            if error.code not in RETRY_STATUS or attempt == attempts - 1:
                raise
            wait = max(BACKOFF[min(attempt, len(BACKOFF) - 1)], int(error.headers.get("Retry-After") or 0))
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == attempts - 1:
                raise
            wait = BACKOFF[min(attempt, len(BACKOFF) - 1)]
        print(f"retrying {url[:80]} in {wait}s", file=sys.stderr)
        time.sleep(wait)


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


def skip(name, row, error):
    """Log a row a source could not read; the caller carries on with the next one."""
    print(f"{name}: row skipped, {type(error).__name__}: {error}; {str(row)[:120]}", file=sys.stderr)


def orgnr(value):
    """Return the 10 digits of a Swedish organisationsnummer found in ``value``, or None."""
    if not value:
        return None
    m = re.search(r"(?<!\d)(?:16)?(\d{6})-?(\d{4})(?!\d)", str(value))
    return m.group(1) + m.group(2) if m else None


def org_id(number):
    return f"SE{number}" if number else None
