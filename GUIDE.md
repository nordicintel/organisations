# Guide to the files

Two files are the product. Everything else either feeds them or is derived from them.

## The product

### `organisations.json`

Generated. Never edit by hand; the next build overwrites it.

```json
{"generated": "2026-10-13", "count": 1029, "organisation": {"SE2021000837": {…}, …}}
```

One object per organisation, keyed by id, following `schema/organisation.schema.json`.
The fields, in the order you will use them:

| field | meaning | from |
|---|---|---|
| `id` | `SE` + organisationsnummer; `SE…-LST` style for dataportal.se's agreed suffixes; `wikidata:Q…` for bodies with no Swedish number | registers, edits |
| `label` | official name by language, `sv` always, `en` where published | Statskontoret, dataportal, Myndighetsregistret, Wikidata, edits |
| `registered_label` | the name exactly as registered with SCB | SCB bulk file |
| `slug` | our short code; one per organisation | edits |
| `alias` | strings seen in source metadata that mean this organisation, every earlier name and abbreviation of a state body, and register names that lost to the label | Statskontoret, dataportal, Myndighetsregistret, edits |
| `status` | `active`, `deregistered`, `unknown` | SCB, Wikidata |
| `type` | ADMS publisher type, the vocabulary both data portals use | legal type, dataportal, edits |
| `legal_type` | Skatteverket's two-digit juridisk form with label; the authority for what a body is | SCB |
| `state_body_group`, `sfs`, `department` | state bodies only | Myndighetsregistret, Statskontoret, Wikidata |
| `code` | `kommun` and `lan` codes for municipalities | Wikidata |
| `homepage`, `email` | | dataportal, Myndighetsregistret, Statskontoret |
| `established`, `dissolved`, `succeeded_by` | history; `succeeded_by` lists organisation ids | SCB, Wikidata, Statskontoret |
| `part_of` | parent id, e.g. the base number behind a suffixed id | derived |
| `identifier` | one canonical value per external system: `orgnr`, `dataportal`, `wikidata`, `ror`, `riksarkivet` | registers |
| `same_as` | every other URI the portals use for the same organisation | portals, edits |
| `source` | which registers and edits contributed | build |
| `note` | free text | edits |

Resolve a name to an organisation by `alias` first, then `label` and
`registered_label`. For state bodies Statskontoret's name wins the Swedish label:
it is the current name as the body writes it ("Kungl. biblioteket",
"Integritetsskyddsmyndigheten"), where dataportal.se is often stale and
Myndighetsregistret is upper case. English names come from Wikidata first and
Statskontoret only fills gaps, since its English column is old and uneven.
Statskontoret also writes which earlier
number a body had (`succeeded_by` from the old number to the new one) and which
body a wound-up one went into, read from the register's comment. Resolve a portal URI through `identifier.dataportal`,
`same_as`, or the `links/` files.

### `data_sources.json`

Hand-maintained, and also final: it has no generated part. One object per
survey, register, database, statistical product, publication or unit that
source metadata names as the origin of data, following `schema/data_source.schema.json`.

| field | meaning |
|---|---|
| `id` | lower-case slug, stable |
| `label` | name by language |
| `type` | `survey`, `register`, `database`, `statistical_product`, `publication`, `unit`, `other` |
| `owner` | organisation id that runs it, or `null` |
| `alias` | raw strings that denote it; one string may denote several data sources |
| `seen_in`, `cited_by` | which adapters mention it and which organisations' datasets cite it |

A source string is resolved in two steps: organisation names through
`organisations.json` aliases, and what remains through `data_sources.json`.
"SCB:s Räkenskapssammandrag" gives SCB as the organisation and
`scb-rakenskapssammandraget` as the data source.

## The input you edit

### `edits/organisations.json`

The only hand file for organisations. Merged last, so it wins over every register.

```json
{
  "organisation": {
    "SE2021000837": {"slug": "scb", "alias": ["SCB", "Statistics Sweden"]},
    "SE8460010161": {},
    "wikidata:Q41550": {"label": {"en": "OECD"}, "type": "SupraNationalAuthority", "status": "active"}
  },
  "ignore": ["Svensk Fågeltaxering"]
}
```

- Any organisation field may be set except `id`, `source` and `registered_label`.
  `label` and `identifier` merge per key, `alias` and `same_as` are unions,
  everything else overrides.
- An id the registers lack is created. For a Swedish number `{}` is enough; the
  next build pulls name, legal type and status from the SCB file. For a
  `wikidata:` id give `label`, `type` and `status`.
- Find ids by name in `organisations.json`. Never type an organisationsnummer
  from memory; two of the first slugs were wrong that way.
- `ignore` lists strings that are neither an organisation nor a data source, so
  nobody re-investigates them.

## Derived

| path | what |
|---|---|
| `links/dataportal.json` | dataportal.se agent URI → organisation id, `null` when no number can be read from it |
| `links/data-europa.json` | data.europa.eu publisher and creator URI → organisation id |
| `links/wikidata.json` | Wikidata item → organisation id |
| `snapshots/<register>.json` | the reduced result of the last successful fetch of each register. Committed so a build still runs when a register is down |
| `reports/<date>.json` | written by a build that changed something or had a register problem: per register `fetched`, `stale` or `failed`, counts, added and removed ids |

## Build and check

```sh
python scripts/build.py     # fetch registers, rewrite organisations.json, links/, snapshots/, reports/
python scripts/validate.py  # schemas and references across all files; run before committing
```

A register that cannot be fetched is replaced by its snapshot and reported as
`stale`; only when every register fails does the build exit non-zero. Builds are
deterministic, so a diff means a register or an edit changed.

statskontoret.se cannot be reached from GitHub-hosted runners or cloud sessions,
so that register is always `stale` in the workflow and lives on its committed
snapshot; its snapshot only changes when Statskontoret publishes a new year, so
run `python scripts/build.py` from a machine in Sweden once a year, or whenever
the report has said `stale` for a long time, and commit the result.
