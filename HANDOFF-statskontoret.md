# Handoff: finish the Statskontoret register in `nordicintel/organisations`

For an agent running on a machine in Sweden (or anywhere statskontoret.se
answers). Cloud sessions and GitHub-hosted runners cannot reach
statskontoret.se at all: TCP connect times out from GitHub Actions and the
TLS handshake is closed from Anthropic's containers, regardless of user
agent. Verified on 2026-10-13 with a probe workflow (since removed). A
browser in Sweden loads the site normally.

Read `GUIDE.md` first. It describes every file. Work directly on `main`; there
are no feature branches in this repo. Commit messages are plain, no AI
attribution lines.

## State of the repo (main at 987cbfa)

- 899 organisations, `python scripts/validate.py` reports 0 errors, builds
  are deterministic.
- `scripts/sources/statskontoret.py` is written and integrated in
  `scripts/build.py`, but `snapshots/statskontoret.json` does not exist yet
  because no build has been able to fetch the file. Every report so far
  lists `"statskontoret": {"status": "failed", ...}`.
- The build tolerates this: a register that fails falls back to its committed
  snapshot, and with no snapshot it contributes nothing.

## What the source does today

`statskontoret.fetch(cache)` downloads the all-years export

    https://www.statskontoret.se/kunskapsstod-och-regler/rapportering/myndighetsregistret/exportexcelallaarmyndigheter

and reads it with a standard-library xlsx reader (`sheets()` in the same
module; no openpyxl, the build is stdlib only). Expected layout, which is
known only second hand and must be verified against the real file:

- one sheet per year, sheet name is the year, since 1999
- header row with at least `LöpNr`, `Myndighet`, `OrgNr`, `Kommentar`
- `LöpNr` is a running number that survives renames
- `Kommentar` is free text that says where a wound-up body went

Reduced snapshot shape, keyed by running number:

```json
{"123": {"name": {"1999": "Datainspektionen", "2021": "Integritetsskyddsmyndigheten"},
         "orgnr": ["2021000050"], "successor": "", "last_year": 2026}}
```

`build.py` then, per running number with a known organisationsnummer:

- adds every earlier name as `alias`
- offers the latest name as a label candidate at priority 3 in
  `LABEL_PRIORITY` (after dataportal 1 and Myndighetsregistret 2)
- parses `successor` from the comment (`statskontoret.successor()`, regex on
  "uppgår i", "inordnas i", "överförs till" and similar; "delar av" is
  skipped), matches it to another running number by name (exact, then
  difflib at 0.88) and writes `succeeded_by` on the predecessor

This was tested on a synthetic workbook in that layout, never on the real
file.

## Tasks, in order

1. Fetch and inspect the real export. Run `python scripts/build.py` from the
   machine. If the fetch succeeds, open `.cache/statskontoret.xlsx` and check
   the sheet names and header row against the expectations above. Fix
   `fetch()` if column names or sheet names differ (for instance a trailing
   info sheet, `OrgNr` formatted as number, year sheets named differently).
   If the download itself fails even locally, say so and stop.

2. Check what the register changed. After a successful build, inspect
   `reports/<date>.json` and the diff of `organisations.json`:
   - how many organisations gained `alias`, `succeeded_by`, or a changed
     `label.sv`
   - sample ten `succeeded_by` pairs and confirm each is right (the comment
     text is in the cache file; `statskontoret.successor()` can be run on it)
   - look for wrong matches from the 0.88 fuzzy threshold; tighten or add an
     explicit map in `edits/organisations.json` if needed
   - a known case to confirm: old Statskontoret `SE2021000852` was wound up
     2025-12-31 and the Ekonomistyrningsverket number `SE2021005026` carries
     the name Statskontoret from 2026 (SFS 2025:681). The edits file already
     records this; make sure the register does not contradict it.

3. Decide the label priority. dataportal.se names are often stale
   (`SE2021000050` is still "Datainspektionen" there, the current name is
   Integritetsskyddsmyndigheten). Statskontoret writes names the way the
   bodies do ("Kungl. biblioteket"), Myndighetsregistret writes them in
   capitals which the build title-cases. Count how many `label.sv` values
   change if `statskontoret` is moved to priority 1 (ahead of dataportal) and
   look at a sample. Pick the order that gives current, correctly cased
   names and record the reason in `GUIDE.md` in one line.

4. Optionally add the yearly list. Statskontoret also publishes a
   one-year file on
   `https://www.statskontoret.se/analys-och-statistik/oppna-data/myndighetsforteckning/`,
   currently linked as
   `/contentassets/<hex>/statskontorets-myndighetsforteckning-2026.xlsx?v=…`.
   The hex folder and the year change, so never hard-code the link: fetch the
   page, regex `contentassets/[0-9a-f]+/statskontorets-myndighetsforteckning-(\d{4})\.xlsx`,
   take the highest year. Only add it if it carries something the all-years
   export lacks (department, SFS, web address, former names). If it does,
   same pattern: reduce to a snapshot, merge in `build.py`, one source name.
   If it is a subset of the export, leave it out and note why in `GUIDE.md`.

5. Commit and push to main: `scripts/`, `GUIDE.md` if changed,
   `snapshots/statskontoret.json`, `organisations.json`, `links/`,
   `reports/`. Run `python scripts/validate.py` before every commit. Then
   trigger the workflow (Actions → Refresh registry → Run workflow) and
   confirm it is green: on the runner the register will report `stale` and
   use the committed snapshot, which is the intended behaviour. The runner
   commit, if any, should carry no content changes beyond the report.

6. Refresh policy. The snapshot only changes when Statskontoret publishes a
   new year, so a local `python scripts/build.py` once a year, or whenever
   the report has said `stale` for a long time, is enough. Write that one
   sentence into the Build and check section of `GUIDE.md`.

## Rules that caused trouble before

- Never type an organisationsnummer from memory. Look the name up in the SCB
  bulk file (`.cache/scb_bulkfil.zip`, cp1252 TSV, column `Namn`,
  `PeOrgNr` with a leading `16`) and assert exactly one hit. Two of the
  first slugs were wrong because of this.
- Field names are `label`, `type`, `note`, `alias`, singular and multilingual
  where documented. Identifiers are single strings. `type` values are the
  ADMS terms listed in `schema/organisation.schema.json`.
- `edits/organisations.json` is the only hand file. Anything derived belongs
  in a source module and a snapshot.
- Keep the number of files minimal. No new folders, no second hand file.
- Builds must be deterministic and byte-identical between consecutive runs.
  Sort every set before writing; pick `min()` on multi-valued inputs.
- Do not cite or vendor code from other people's repositories.

## Scratch material from the cloud session, not in the repo

If useful, the previous session left a pull of the 529 Swedish catalogs from
datenoio/dataportals-registry and a worklist of catalog owners that did not
resolve to our registry. After this session's edits, 506 of 529 owners
resolve; the remaining 23 have no Swedish legal unit (hobby sites, informal
consortia, foreign bodies) and were left out on purpose. That registry was a
completeness check only. Nothing from it is to be imported or referenced.
