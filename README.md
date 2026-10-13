# organisations

Registry of organisations that publish, produce or host Nordic statistical data,
keyed by Swedish organisationsnummer. Regenerated weekly from free official
sources; no API keys, no accounts.

## Files

| file | maintained by | contents |
|---|---|---|
| `data/organisations.json` | generated | one object per organisation, see `schema/organisation.schema.json` |
| `slugs.json` | hand | our short codes, slug → organisation id. Slugs may change; ids never do |
| `aliases.json` | hand (seeded) | free-text strings seen in source metadata → organisation id, or `null` for strings that are not organisations |
| `manual.json` | hand | per-organisation overrides and additions merged last |
| `data_sources.json` | hand (seeded) | surveys, registers, databases, statistical products and units that source metadata names as the origin of data, with `owner` set to an organisation id where known and `cited_by` listing the organisations whose datasets cite them; see `schema/data_source.schema.json` |
| `links/dataportal.json` | generated | dataportal.se agent URI → organisation id (`null` when the URI carries no organisationsnummer) |
| `links/data-europa.json` | generated | data.europa.eu publisher and creator URI → organisation id |
| `links/wikidata.json` | generated | Wikidata Q-id → organisation id |

A data source is not an organisation: Kolada's "Källa" is organisation plus
survey or register name, PxWeb sources name databases and departments. The
organisation part resolves through `aliases.json`; the remainder resolves through
`data_sources.json`, which ties the product to the organisation that runs it. The
seeded owners came from the organisation named in the same source string, which
is right for "SKR:s personalstatistik" and wrong for "Patientregistret,
Socialstyrelsen"-style citations where the named organisation is the user, not
the keeper; those need hand correction.

Organisation ids are `SE` + the 10-digit organisationsnummer. dataportal.se's
agreed suffix form is kept as its own id, e.g. `SE2021002361-LST` for the county
administrative boards jointly, with `part_of` pointing at the base number.

## Sources

| source | gives | cadence |
|---|---|---|
| [SCB bulk file](https://vardefulla-datamangder.bolagsverket.se/scb/scb_bulkfil.zip) (hosted by Bolagsverket, EU high-value dataset) | every legal unit with organisationsnummer, registered name and Skatteverket legal-form code; all public bodies are kept (codes 81–89) plus any number another source mentions | weekly |
| [SCB Myndighetsregistret](https://myndighetsregistret.scb.se/) | state bodies by group (förvaltningsmyndighet, riksdag, affärsverk, AP-fond, domstol) with SFS, email, web | weekly |
| [dataportal.se](https://admin.dataportal.se/) registry context 827 and SPARQL | canonical portal URIs, ADMS publisher type, homepage, email, `owl:sameAs` to source catalogues | continuous |
| [data.europa.eu SPARQL](https://data.europa.eu/sparql) | publisher and creator URIs of the Swedish catalogue, identifiers, types | continuous |
| [Wikidata](https://query.wikidata.org/) | municipality and county codes, department, inception and dissolution dates, succession, Riksarkivet ids | continuous |

Legal form is the authority for type; organisationsnummer prefixes (2021 state,
2120 municipality, 2220 kommunalförbund, 2321 region) are an allocation
convention and only used as a sanity check. Publisher type uses the ADMS
vocabulary `http://purl.org/adms/publishertype/`.

## Build

```sh
python scripts/build.py            # downloads into .cache/ and rewrites data/ and links/
python scripts/build.py --cache X  # reuse an existing cache directory
```

Standard library only. The weekly workflow runs the build and commits when
anything changed.
