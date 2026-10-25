## Source audit and prepared data

The environmental CSV was read completely: 179,447 records, five sensor IDs and 42,843 unique sensor-time observations after 136,604 agreeing repeats were removed. The occupancy CSV was also read completely: 9,091,732 records and five spaces. Both workbook sheets were inspected. Excluded examples were inventoried and not analysed. Source hashes, units, timestamp evidence and mapping problems are preserved in `data/prepared/source_audit.json` and `data_audit/`.

A second full preparation run using the fresh pinned environment reprocessed both raw ZIPs and the workbook. Both resulting CSV files matched the bundled `environment.csv` and `occupancy_summary.csv` byte-for-byte. Its terminal output is retained in `reports/raw_preparation_check.log`. An independently written parser checked five deterministic primary samples against raw JSON without importing the preparation code; all concentrations, temperatures, humidity values and ingestion counts matched. These sample checks supplement the full-stream structural checks and are not claimed to prove calibration.

## Tests and clean-clone reproduction

The pinned requirements were installed in a new isolated Python 3.12 environment. The complete suite passed **98 checks, zero failures/errors/skips**. The first fresh-environment terminal summary reports 17.98 seconds (XML suite time 17.968 seconds) and is preserved in `reports/test_report.html` and `reports/test_results.xml`.

A clean Git clone at implementation checkpoint **`6ea7615`** then ran the entire `scripts/reproduce.py` workflow with exit code 0. All 98 checks passed again: terminal summary **9.60 seconds**, XML suite time 9.587 seconds. The workflow regenerated scientific figures, package/module API HTML and the technical report. The clean-clone test reports and full workflow log are preserved separately in `reports/clean_clone_test_report.html`, `reports/clean_clone_test_results.xml` and `reports/clean_reproduction.log`. The two suite durations refer to different actual runs; neither is presented as the full workflow duration.

All **27 partition/method/gap-size metric rows** matched numerically, with maximum checked difference **0.0** and an allowed absolute tolerance of `1e-9`. The selected method remained linear. The demonstration CSV matched byte-for-byte. Fresh timings were written under the clean clone's `tmp/reproduced_results`; the submitted summary, profile and optimisation table stayed byte-for-byte unchanged. `reports/reproduction_checks.json` records these measured outcomes.

## Independent numerical and leakage review

An independent implementation reconstructed all linear evaluation windows directly from indices, without calling the study's masking or scoring pipeline. All saved linear validation, test and secondary metrics matched within `1e-11`. Known and hidden indices were disjoint. Partition slices were created before context windows, so context did not cross development/validation/test boundaries. Eligibility used timestamps, and the selection file was saved before final evaluation.

Manufactured affine/constant cases, hand-calculated irregular interpolation and a separate PCHIP Hermite calculation verify the numerical implementation. Tests also cover source duplicates, measurement versus ingestion time, units, invalid arrays, extrapolation, masking, metrics, integration and end-to-end CSV status handling. None is a substitute for measured physical truth.

The retained limitations are material: only six long-gap validation windows; different populations across missing counts; unknown sensor calibration; larger primary worst-case errors for linear in some comparisons; and secondary six-reading RMSE 16.7105 ppm versus the baseline's 15.7849 ppm. The 312.8571 ppm secondary maximum is an overprediction, while average bias is only +0.3443 ppm. No retuning followed final evaluation.

## Artifact QA

The report has **nine main pages and one references page**. All ten final pages were rendered with Poppler and visually inspected; figures, tables, formulas, footers, references and page boundaries were legible with no observed clipping or overlap. A separate horizontal-margin check found no violations. All five scientific figure pairs were inspected, and the report references the preserved numerical evidence.

Generated HTML includes the package and all three source modules, with all seven exported public functions. Documentation was regenerated after the final source-docstring changes. Examples, parameters, units, returns and exceptions remain available with the actual source.

The presentation contains six editable slides, four native tables, two native charts with embedded data workbooks and six speaker-note parts. Its artifact-tool package, layout, font and re-import validation passed, and final slide renders were visually reviewed. The six-page PDF is a static handout from those renders because the native PDF exporter lacked its font module. No native PowerPoint application test is claimed. The speaker script includes the repository walkthrough within five minutes.

## Release 
The clean-clone packager checks required files, every tracked file's bytes, ZIP integrity, the `main` commit and absence of a configured remote. It includes actual Git history. The delivered external `submission_manifest.json` records the exact final release commit, byte count and checksum, avoiding a circular archive checksum. Final archive checks are recorded there after the final commit. The delivery also supplies the original source inputs separately from the Git repository for a complete raw re-audit.

