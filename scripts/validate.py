"""Check the generated and hand-maintained files against each other and the schemas.

Standard library only: validates the few constraints that matter (id pattern,
required keys, enum values, referential integrity) without a jsonschema dependency.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
schema = json.loads((ROOT / "schema" / "organisation.schema.json").read_text(encoding="utf-8"))
ID = re.compile(schema["properties"]["id"]["pattern"])
TYPES = set(schema["properties"]["publisher_type"]["enum"])
GROUPS = set(schema["properties"]["state_body_group"]["enum"])
STATUS = set(schema["properties"]["status"]["enum"])
FIELDS = set(schema["properties"])

orgs = json.loads((ROOT / "data" / "organisations.json").read_text(encoding="utf-8"))["organisations"]
errors = []
for key, org in orgs.items():
    if key != org["id"] or not ID.match(key):
        errors.append(f"bad id {key}")
    if not org.get("names"):
        errors.append(f"{key}: no names")
    if org.get("status") not in STATUS:
        errors.append(f"{key}: status {org.get('status')}")
    if "publisher_type" in org and org["publisher_type"] not in TYPES:
        errors.append(f"{key}: publisher_type {org['publisher_type']}")
    if "state_body_group" in org and org["state_body_group"] not in GROUPS:
        errors.append(f"{key}: state_body_group {org['state_body_group']}")
    if extra := set(org) - FIELDS:
        errors.append(f"{key}: unknown fields {sorted(extra)}")
    for ref in org.get("succeeded_by", []) + ([org["part_of"]] if "part_of" in org else []):
        if ref not in orgs:
            errors.append(f"{key}: dangling reference {ref}")

for name in ("slugs.json", "aliases.json", "manual.json"):
    data = json.loads((ROOT / name).read_text(encoding="utf-8"))
    for k, v in (data.items() if name != "manual.json" else ((k, k) for k in data)):
        if v is not None and v not in orgs:
            errors.append(f"{name}: {k!r} -> {v} not in registry")
slugs = json.loads((ROOT / "slugs.json").read_text(encoding="utf-8"))
for slug in slugs:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", slug):
        errors.append(f"slugs.json: bad slug {slug!r}")

for line in errors:
    print(line, file=sys.stderr)
print(f"{len(orgs)} organisations, {len(slugs)} slugs, {len(errors)} errors", file=sys.stderr)
sys.exit(1 if errors else 0)
