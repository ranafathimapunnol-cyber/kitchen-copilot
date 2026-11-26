# Third-Party Notices

Third-party software and assets added for supplier report exports (PUR04,
AT08), with their licences. Each was approved before it was added
(18 November 2026). Versions are pinned exactly in
`services/api/requirements.txt`.

This file lists only the components added for exports. The project's other
dependencies are pinned in `services/api/requirements.txt` and
`apps/web/package.json`, and their licences ship with each package.

## Python packages (backend)

| Package | Version | Licence | Purpose |
|---|---|---|---|
| [XlsxWriter](https://pypi.org/project/XlsxWriter/3.3.1/) | 3.3.1 | BSD-2-Clause | Writes the Excel (.xlsx) export |
| [reportlab](https://pypi.org/project/reportlab/5.1.0/) | 5.1.0 | BSD-style (ReportLab open-source licence; see the package's `LICENSE.txt`) | Writes the PDF export |
| [pillow](https://pypi.org/project/pillow/13.0.0/) | 13.0.0 | MIT-CMU | Required by ReportLab |
| [charset-normalizer](https://pypi.org/project/charset-normalizer/3.5.2/) | 3.5.2 | MIT | Required by ReportLab |
| [pypdf](https://pypi.org/project/pypdf/6.21.4/) | 6.21.4 | BSD-3-Clause | Tests only: reads exported PDFs to check their text |

When approved, each version was at least two weeks old, supported Python
3.14, and had no known vulnerabilities in the OSV database. Pillow 12.3.0
was rejected because it has published vulnerabilities.

## Fonts

| Asset | Version | Licence | Location |
|---|---|---|---|
| Noto Sans Regular and Bold (static, hinted) | 2.015 | SIL Open Font License 1.1, © 2022 The Noto Project Authors | `services/api/app/assets/fonts/` |

Source, checksums and licence details: `services/api/app/assets/fonts/README.md`.
The licence text (`OFL.txt`) is kept next to the font files, as the licence
requires.
