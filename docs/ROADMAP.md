# PartHarbor roadmap

## Implemented in the MVP

- Search the current anonymous JLCPCB catalogue
- Default to Basic/Preferred parts
- Normalize common shorthand such as `100n 0402 16v`
- Resolve MOSFET aliases and strictly filter explicit package terms
- Import one or many C-numbers
- Import symbol, footprint and 3D model by default
- Independently disable each asset and opt into overwrite
- Enrich newly imported symbols with searchable JLCPCB metadata
- Search the local generated KiCad symbol library
- Build a self-contained KiCad PCM archive

## Recommended next steps

1. **Structured parametric filters.** Parse value, package, voltage, tolerance,
   dielectric, power and pin count instead of relying only on free-text search.
2. **Part-quality view.** Preview symbol, footprint and pin mapping before import;
   show a prominent warning when EasyEDA data is missing or inconsistent.
3. **Availability cache.** Keep a small local SQLite index with last-seen stock,
   Basic/Extended status and timestamp, with a manual refresh action.
4. **Alternatives.** Suggest pin-compatible or value-compatible Basic parts when
   a chosen component is Extended, out of stock or close to end of life.
5. **Library maintenance.** Detect duplicates, compare remote revisions, update a
   selected part, and show which projects currently reference it.
6. **Project mode.** Optionally import into a project-local library using
   `${KIPRJMOD}` rather than the global shared library.
7. **BOM workflow.** Paste/import a BOM column of C-numbers and produce an import
   report with successes, missing CAD data and skipped duplicates.
8. **Trust and reproducibility.** Store source URL, fetch time and a hash of the
   downloaded source data beside each imported part.

## KiCad integration constraint

As of KiCad 10.0.3, supported Python Action Plugins are hosted by PCB Editor.
Schematic Editor has no equivalent public toolbar-plugin API. PartHarbor should
add a Schematic Editor action only when KiCad exposes a supported API; modifying
KiCad's process or UI at runtime would be brittle and unsuitable for PCM.

## Official PCM publication

The package layout is ready for PCM. Publishing in KiCad's official repository
still requires:

- a public source repository and release ZIP with stable URL and SHA-256 hash;
- a merge request to KiCad's addon metadata repository;
- discussion with the KiCad team because PartHarbor connects to the commercial
  JLCPCB/LCSC service (the current KiCad addon policy calls this out explicitly).

A third-party PCM repository or manual **Install from File** distribution does
not require acceptance into the official KiCad repository.
