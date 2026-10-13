# organisations

Registry of the organisations and data sources behind Nordic statistical data,
keyed by Swedish organisationsnummer. Rebuilt weekly from free official
registers. No API keys, standard library only.

- `organisations.json` is the registry: 877 organisations with official names,
  legal type, publisher type, status, history and their identities on
  dataportal.se, data.europa.eu and Wikidata.
- `data_sources.json` is the companion list of surveys, registers, databases
  and products that metadata cites as the origin of data, tied to the
  organisation that runs them.
- `edits/organisations.json` is the one file you edit.

[GUIDE.md](GUIDE.md) explains every file and field and how to edit. Schemas are
in `schema/`.

## Sources

| register | gives |
|---|---|
| [SCB bulk file](https://vardefulla-datamangder.bolagsverket.se/scb/scb_bulkfil.zip), hosted by Bolagsverket, weekly | every legal unit: organisationsnummer, registered name, legal type, status. Public bodies are kept whole; other units when another source or an edit mentions them |
| [Myndighetsregistret](https://myndighetsregistret.scb.se/) | state bodies by group, SFS, email, web. Courts share Domstolsverket's number |
| [dataportal.se](https://admin.dataportal.se/) registry and SPARQL | canonical portal URIs, publisher type, homepage, email, `owl:sameAs` |
| [data.europa.eu SPARQL](https://data.europa.eu/sparql) | publisher and creator URIs of the Swedish catalogue, identifiers, types |
| [Wikidata](https://query.wikidata.org/) | English names, kommun and län codes, department, dates, succession |

Legal type is the authority for what an organisation is. Organisationsnummer
prefixes (2021 state, 2120 municipality, 2220 kommunalförbund, 2321 region) are
an allocation convention and only a sanity check.

## Build

```sh
python scripts/build.py && python scripts/validate.py
```

The workflow in `.github/workflows/refresh.yml` does the same weekly and
commits when anything changed, with a short report in `reports/`.
