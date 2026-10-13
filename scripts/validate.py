"""Check organisations.json, data_sources.json and edits/organisations.json against the schemas and each other.

Standard library only: ids, required keys, enums, patterns and references.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
errors = []


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def check(obj, schema, where):
    props = schema["properties"]
    for key in schema.get("required", []):
        if key not in obj:
            errors.append(f"{where}: missing {key}")
    for key, value in obj.items():
        if key not in props:
            errors.append(f"{where}: unknown field {key}")
            continue
        spec = props[key]
        if "enum" in spec and value not in spec["enum"]:
            errors.append(f"{where}: {key} {value!r} not in enum")
        if "pattern" in spec and isinstance(value, str) and not re.fullmatch(spec["pattern"], value):
            errors.append(f"{where}: {key} {value!r} does not match pattern")
        if spec.get("type") == "array" and spec.get("minItems") and not value:
            errors.append(f"{where}: {key} is empty")


org_schema, ds_schema, edits_schema = read("schema/organisation.schema.json"), read("schema/data_source.schema.json"), read("schema/edits.schema.json")
orgs = read("organisations.json")["organisation"]
sources = read("data_sources.json")
edits = read("edits/organisations.json")

slugs = {}
for key, org in orgs.items():
    if key != org.get("id"):
        errors.append(f"organisations.json: key {key} != id {org.get('id')}")
    check(org, org_schema, f"organisations.json {key}")
    if not org.get("label"):
        errors.append(f"{key}: no label")
    if "slug" in org:
        if org["slug"] in slugs:
            errors.append(f"{key}: slug {org['slug']} also used by {slugs[org['slug']]}")
        slugs[org["slug"]] = key
    for ref in org.get("succeeded_by", []) + ([org["part_of"]] if "part_of" in org else []):
        if ref not in orgs:
            errors.append(f"{key}: reference {ref} not in registry")

for key, ds in sources.items():
    if key != ds.get("id"):
        errors.append(f"data_sources.json: key {key} != id {ds.get('id')}")
    check(ds, ds_schema, f"data_sources.json {key}")
    for ref in ([ds["owner"]] if ds.get("owner") else []) + ds.get("cited_by", []):
        if ref not in orgs:
            errors.append(f"data_sources.json {key}: organisation {ref} not in registry")

check(edits, edits_schema, "edits/organisations.json")
for key, patch in edits.get("organisation", {}).items():
    if not re.fullmatch(org_schema["properties"]["id"]["pattern"], key):
        errors.append(f"edits: bad id {key}")
    if key not in orgs:
        errors.append(f"edits: {key} did not make it into organisations.json")
    for field in patch:
        if field not in org_schema["properties"] or field in ("id", "source", "registered_label"):
            errors.append(f"edits {key}: field {field} not allowed")

for line in errors:
    print(line, file=sys.stderr)
print(f"{len(orgs)} organisations, {len(slugs)} slugs, {len(sources)} data sources, {len(errors)} errors", file=sys.stderr)
sys.exit(1 if errors else 0)
