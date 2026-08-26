"""The reporting foundation: one kernel, one report definition per report.

`registry` says what a report IS, `engine` runs it, `xlsx_renderer` writes the workbook and
`views_service` owns saved views. Report definitions (the sponsorship report is #1, S3) live
in `definitions/` and are imported here so the registry is populated wherever it is read.
"""
