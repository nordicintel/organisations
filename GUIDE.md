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
| `id` | `SE` + organisationsnummer; `SE…-LST` style for dataportal.se's agreed suffixes; `SE…-ALINGSAS-TINGSRATT` style for a state body listed under another body's number (the courts under Domstolsverket), suffix from its own mailbox, else its name; `wikidata:Q…` for bodies with no Swedish number | registers, edits |
| `label` | official name by language, `sv` always, `en` where published | Statskontoret (sv), dataportal, Myndighetsregistret, Wikidata, edits |
| `registered_label` | the name exactly as registered with SCB | SCB bulk file |
| `slug` | our short code; one per organisation | edits |
| `alias` | other names for this organisation as source metadata writes them (abbreviations, English names, spelling variants), every earlier name of a state body, former official and alternative names from Wikidata, and register names that lost to the label. Never a citation that names a data source ("SCB, AKU"): that string belongs in `data_sources.json`, whose `owner` gives the organisation | Statskontoret, Wikidata, dataportal, Myndighetsregistret, edits |
| `status` | `active`, `deregistered`, `unknown` | SCB, Wikidata |
| `organisation_type` | ADMS publisher type, the vocabulary both data portals use | legal type, dataportal, edits |
| `legal_type` | Skatteverket's two-digit juridisk form with label; the authority for what a body is | SCB |
| `state_body_group`, `sfs`, `department` | state bodies only | Myndighetsregistret, Statskontoret, Wikidata |
| `code` | `kommun` and `lan` codes for municipalities | Wikidata |
| `homepage`, `email` | | dataportal, Myndighetsregistret, Statskontoret |
| `established`, `dissolved`, `succeeded_by` | history; `succeeded_by` lists organisation ids | SCB, Wikidata |
| `part_of` | parent id: the legal unit behind a suffixed id | derived |
| `identifier` | one canonical value per external system: `orgnr`, `dataportal`, `wikidata`, `ror`, `riksarkivet` | registers |
| `same_as` | every other URI the portals use for the same organisation | portals, edits |
| `source` | which registers and edits contributed | build |
| `note` | free text | edits |

Resolve a name to an organisation by `alias` first, then `label` and
`registered_label`. When a name matches several (a body and its wound-up
predecessor of the same name, like Skogsstyrelsen before and after 2006), take the
one without `succeeded_by`. For state bodies Statskontoret's name wins the Swedish label:
it is the current name as the body writes it ("Kungl. biblioteket",
"Integritetsskyddsmyndigheten"), where dataportal.se is often stale and
Myndighetsregistret is upper case. English names come from Wikidata. Every name a
number has carried since 2007 in Statskontoret's list is an alias, as are the
abbreviations and former names its own column gives. Succession (`succeeded_by`)
comes from Wikidata. Resolve a portal URI through `identifier.dataportal`,
`same_as`, or the `links/` files.

### `data_sources.json`

Hand-maintained, and also final: it has no generated part. One object per
survey, register, database, statistical product, publication or unit that
source metadata names as the origin of data, following `schema/data_source.schema.json`.

| field | meaning |
|---|---|
| `id` | lower-case slug, stable |
| `label` | name by language |
| `data_source_type` | `survey`, `register`, `database`, `statistical_product`, `publication`, `unit`, `other` |
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
    "wikidata:Q41550": {"label": {"en": "OECD"}, "organisation_type": "SupraNationalAuthority", "status": "active"}
  },
  "ignore": ["Svensk Fågeltaxering"]
}
```

- Any organisation field may be set except `id`, `source` and `registered_label`.
  `label` and `identifier` merge per key, `alias` and `same_as` are unions,
  everything else overrides.
- An id the registers lack is created. For a Swedish number `{}` is enough; the
  next build pulls name, legal type and status from the SCB file. For a
  `wikidata:` id give `label`, `organisation_type` and `status`.
- Find ids by name in `organisations.json`. Never type an organisationsnummer
  from memory; two of the first slugs were wrong that way.
- `ignore` lists strings that are neither an organisation nor a data source, so
  nobody re-investigates them.

## Derived

| path | what |
|---|---|
| `links/dataportal.json` | dataportal.se agent URI → organisation id, `null` when no number can be read from it |
| `links/data-europa.json` | data.europa.eu publisher, creator and rights-holder URI → organisation id, `null` when no number can be read from it; Geodataportalen's contacts appear as `mailto:` keys |
| `links/wikidata.json` | Wikidata item → organisation id |
| `snapshots/<register>.json` | the reduced result of the last successful fetch of each register. Committed so a build still runs when a register is down |
| `dist/<product>.json`, `dist/<product>.csv` | the two product files in every published format: a copy of the JSON and a CSV with one row per record, same name, only the extension differs. Nested fields are dotted columns (`label.sv`), lists are `\|`-joined, and a list of objects gives one column per field with the items aligned by position. Derived from the JSON, so it changes exactly when the product does |
| `reports/<date>.json` | written by a build that changed an organisation or found a register with no snapshot: per register `fetched`, `stale` or `failed`, counts, added and removed ids. `generated` in `organisations.json` is the date of the last content change |

## Build and check

```sh
python scripts/build.py     # fetch registers, rewrite organisations.json, dist/, links/, snapshots/, reports/
python scripts/export.py organisations.json data_sources.json  # rewrite dist/ alone
python scripts/validate.py  # schemas and references across all files; run before committing
```

Failures are contained at three levels. A request that gets a rate limit, a gateway
error or a network failure is retried a few times with a growing pause. A row a
register cannot read, or that the build cannot apply, is skipped and logged, counted
as `skipped` under that register in the report, and the other rows go through. A
register that still cannot be fetched is replaced by its snapshot and reported as
`stale`; only when every register fails does the build exit non-zero. The `dist/`
export failing never fails the build; the report says so. Builds are deterministic,
so a diff means a register or an edit changed.

Statskontoret is not fetched at all: statskontoret.se does not answer GitHub
runners or cloud sessions. Its yearly list lives in the repository as
`files/myndighetsforteckning.xlsx` and the build reads whatever edition is there
(the report says which). Once a year, download the new file from
<https://www.statskontoret.se/analys-och-statistik/oppna-data/myndighetsforteckning/>,
replace it under the same name and commit. Nothing breaks if a year is skipped.
