# organisations

Registry of the organisations and data sources behind Nordic statistical data,
keyed by Swedish organisationsnummer. Rebuilt weekly from free official
registers. No API keys, standard library only.

## Files

| file | kept by | what |
|---|---|---|
| `data/organisations.json` | build | one object per organisation ([schema](schema/organisation.schema.json)) |
| `links/*.json` | build | external URI or id → organisation id, for dataportal.se, data.europa.eu and Wikidata; `null` when the URI carries no organisationsnummer |
| `slugs.json` | hand | our short codes → organisation id. Slugs may change, ids never |
| `aliases.json` | hand | strings seen in source metadata → organisation id, or `null` for a string that is not an organisation ([schema](schema/aliases.schema.json)) |
| `data_sources.json` | hand | surveys, registers, databases, products and units that metadata cites as the origin of data, each with `owner` and the raw strings that denote it ([schema](schema/data_source.schema.json)) |
| `manual.json` | hand | per-organisation overrides and organisations the registers lack, merged last |

## Ids

- `SE` + 10-digit organisationsnummer, e.g. `SE2021000837` for SCB.
- dataportal.se's agreed suffix form is its own id, e.g. `SE2021002361-LST` for
  the county administrative boards jointly, with `part_of` to the base number.
- `wikidata:Q…` for bodies without a Swedish number (Eurostat, OECD, IMF, ECB…).

Legal form (`legal_form.code`, Skatteverket's two-digit code reported by SCB)
is the authority for what an organisation is; `publisher_type` is the ADMS
vocabulary both data portals use. Organisationsnummer prefixes (2021 state,
2120 municipality, 2220 kommunalförbund, 2321 region) are an allocation
convention, not a rule, and are only used as a sanity check.

## Resolving a source string

1. Organisation names resolve through `aliases.json`; "SCB:s Räkenskapssammandrag"
   gives SCB.
2. What remains resolves through `data_sources.json`; "Räkenskapssammandraget"
   is a product owned by SCB. A string may cite several data sources.
3. "Egen undersökning i kommunen" means the publishing municipality itself and
   is the data source `egen-undersokning` with no owner.

## Sources

| register | gives |
|---|---|
| [SCB bulk file](https://vardefulla-datamangder.bolagsverket.se/scb/scb_bulkfil.zip), hosted by Bolagsverket, weekly | every legal unit: organisationsnummer, registered name, legal form, status. Public bodies (codes 81–89) are kept whole; other units only when another source or a hand file mentions them |
| [Myndighetsregistret](https://myndighetsregistret.scb.se/) | state bodies by group (förvaltningsmyndighet, riksdag, affärsverk, AP-fond, domstol), SFS, email, web. Courts share Domstolsverket's number |
| [dataportal.se](https://admin.dataportal.se/) registry context 827 and SPARQL | canonical portal URIs, publisher type, homepage, email, `owl:sameAs` |
| [data.europa.eu SPARQL](https://data.europa.eu/sparql) | publisher and creator URIs of the Swedish catalogue, identifiers, types |
| [Wikidata](https://query.wikidata.org/) | kommun and län codes, department, dates, succession, Riksarkivet ids |

## Build and check

```sh
python scripts/build.py      # downloads into .cache/, rewrites data/ and links/
python scripts/validate.py   # ids, enums, references between all files
```

The workflow in `.github/workflows/refresh.yml` runs both weekly and commits
when anything changed. Builds are deterministic; a diff means a source changed.

## Maintaining

- **New slug**: add `"slug": "SE…"` to `slugs.json`. Find the id by name in
  `data/organisations.json`, never type a number from memory.
- **New alias**: add the raw string to `aliases.json` with the organisation id,
  or `null` if the string is not an organisation.
- **New data source**: add an object to `data_sources.json` with the raw strings
  under `aliases` and the owner's organisation id, or `null` when unknown.
- **Organisation missing from the registers**: add its id to `manual.json`.
  For a Swedish number an empty object `{}` is enough; the next build pulls
  name and legal form from the SCB file. For others give `names`,
  `publisher_type` and `status`.
- **Wrong value from a register**: override the field in `manual.json`;
  manual values win.
- Run `python scripts/validate.py` before committing. It fails on any id that
  does not exist.
