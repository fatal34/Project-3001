# MMA3001 Dataset 2: retrospective CO2 gap reconstruction

This project audits the supplied Monash building-sensor extracts and compares previous-value, linear and PCHIP interpolation for missing environmental readings. It answers a focused engineering data-quality question: **how accurately can a bounded gap be reconstructed using observations before and after it?** It supports retrospective monitoring review. It does not estimate occupancy, ventilation rate, health compliance or energy savings.

## Results and important limits

The full audit read **179,447 environmental** and **9,091,732 occupancy** records. Repeated environmental exports reduce to **42,843 unique sensor-time observations**. Sensor `6012002000869`, uniquely mapped to Building 60 room G.38, provides **13,800 readings** from February to June 2024. Use the embedded measurement timestamp, not the archive name or database creation date. Three sensor streams are effectively frozen. Occupancy cannot be joined defensibly to this room with the supplied mapping and is retained as audited context only.

The frozen chronological validation rule selects **linear interpolation**, with macro RMSE **10.4676 ppm** versus **12.0809** for previous-value and **10.8996** for PCHIP. On the later primary test period, linear RMSE is **9.6117, 9.1730 and 8.8062 ppm** for 1, 3 and 6 hidden readings. Those experiments use 102, 70 and 22 windows, respectively. The six-reading validation case has only **six windows**, and eligibility differs across gap sizes: lower error at a longer gap does not prove longer gaps are easier.

The separate, unmapped secondary sensor exposes a limit: at six hidden readings, linear RMSE **16.7105 ppm** is worse than previous-value **15.7849 ppm**, and its maximum absolute error is **312.8571 ppm**. The frozen policy is retained without retuning. Mean error and worst-case error tell different stories. The errors are against withheld recorded readings; calibration and real-outage accuracy are unknown.

## Files

| Deliverable | Location |
|---|---|
| Nine-page main report plus references | [reports/MMA3001_Dataset2_technical_report.pdf](reports/MMA3001_Dataset2_technical_report.pdf) |
| Editable report | [reports/MMA3001_Dataset2_technical_report.md](reports/MMA3001_Dataset2_technical_report.md) |
| Guarded implementation and generated API | [src/sensor_project](src/sensor_project), [HTML documentation](docs/html/index.html) |
| Tests and generated report | [tests](tests), [reports/test_report.html](reports/test_report.html) |
| Prepared data and complete source audit | [data/prepared](data/prepared), [data_audit](data_audit) |
| Frozen choice, metrics and scientific figures | [results](results), [study protocol](notes/study_protocol.md) |

## Install and reproduce

Use **Python 3.12**. The recorded macOS ARM64 environment has NumPy 2.3.5, SciPy 1.18.1, pandas 2.2.3, Matplotlib 3.11.2 and openpyxl 3.1.5. All runtime, reporting and test dependencies are pinned in `requirements.txt`; no GPU, cloud account or original source archive is needed for the normal reproduction.

From the extracted repository folder on macOS/Linux:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/reproduce.py
```

On Windows use `py -3.12 -m venv .venv`, then replace `.venv/bin/python` with `.venv\Scripts\python.exe`. Installation needs internet access; the analysis then runs offline. Tests, fresh numerical comparisons and the example run execute before figures, API HTML and the technical report regenerate. Fresh timings go to `tmp/reproduced_results`; the submitted study, profile, report numbers and slide values preserve the recorded run. Numerical checks require agreement within `1e-9`; timings vary with machine/load. Inspect `tmp/reproduction_status.json` and the generated test report.

The bundled prepared data make the full comparison reproducible without the 1.6 GB decompressed occupancy export. To independently repeat raw preparation as well, keep the original supplied ZIPs and workbook together, then use:

```sh
.venv/bin/python scripts/reproduce.py --source-dir "/path/to/folder/containing/both/ZIPs/and/workbook"
```

The original source folder supplied for this project is the nested `drive-download-20261024T123024Z-1-001` directory within `project data`, rather than its outer folder. Optional preparation streams both full CSVs, inventories the excluded examples and compares the resulting data with the bundled version. It takes longer than the default workflow. Source SHA-256 values, unit metadata, workbook contents and count checks are in `data/prepared/source_audit.json`. `data_audit/check_prepared_samples.py --source-dir FOLDER` independently checks five deterministic primary samples.

## Reconstruct the supplied demonstration

```sh
.venv/bin/python scripts/reconstruct_csv.py --input data/demo_gap_input.csv --output tmp/my_gap_output.csv
```

The demo hides six readings from the first eligible final-test window, chosen without inspecting errors. It is distinct from the supplied folder labelled **Example Data (Do not use)**, which is excluded from analysis. Eight observed readings remain unchanged and six are reconstructed. Separate truth is supplied only for scoring. Existing outputs are protected; use `--overwrite` deliberately when repeating a generated output.

For your own input, use CSV columns `time_s` (finite Unix/elapsed seconds) and `co2_ppm` (finite nonnegative ppm). Blank CO2 cells identify query rows. Times must be strictly increasing and unique. The tool fills groups of up to six missing readings only with four observed context readings on each side and timestamp steps no larger than 900 seconds throughout the context. Unsupported gaps remain blank with an explicit `unfilled_outside_validated_scope` status. There is no extrapolation. Counts 1, 3 and 6 were evaluated; intermediate counts are within the configured envelope but lack separate empirical results.

## Method, validation and input contract

`reconstruct` takes matching finite 1-D known-time/value arrays (at least two increasing, unique times), finite in-domain query times and one of `previous`, `linear`, `pchip`. It returns predicted values in query order with the original value unit. Invalid arrays, unknown methods and extrapolation raise `ValueError`. `mask_block` removes truth before constructing known knots; `error_metrics` returns MAE, RMSE, largest absolute error and signed bias. Public docstrings define dimensions, units, return meanings and exceptions. Prepared CSV loading explicitly filters sensor IDs and rejects repeated times and nonfinite/negative CO2.

The primary series is split by chronological observation count: development 8,280; validation 2,760; final test 2,760. No context crosses a boundary. Candidates start every 12 observations and hide 1, 3 or 6 consecutive readings; only otherwise well-observed windows qualify. Selection uses the mean of three gap-specific pooled validation RMSEs. Within a declared 1% equivalence band, the simpler method wins. The selected policy is written before final primary or secondary evaluation. Interpolation has no statistical training phase, so development data are not misrepresented as a fitted model.

At the approximate ten-minute cadence, 1/3/6 hidden readings correspond to nominal missing durations of 10/30/60 minutes, but their retained endpoints bracket approximately **20/40/70 minutes**. The hidden first-to-last spans are 0/20/50 minutes. Exact elapsed intervals are used. Overlapping windows across gap sizes are not independent replicates. No unsupported physical acceptance threshold is manufactured.

PCHIP's smooth shape preservation does not guarantee smaller reconstruction error. The supplied Romberg notebook informs the decision to avoid forcing high-order quadrature onto noisy irregular samples. The small trapezoidal integration helper verifies integration of a defined piecewise-linear representation, without claiming unknown physical truth.

## Performance and review

The genuine scalar/vectorised linear comparison uses the same 1,657 known points and 8,280 development queries. Recorded medians are 2.6775 ms and 0.04529 ms (59.12 times), with maximum numerical difference `1.14e-13 ppm`. This implementation workload includes known knots and is separate from the gap-window workload. The 158-window validation batch takes 1.429 ms for linear and 12.382 ms for PCHIP in the recorded run. Each measurement uses warm-up and seven repeats; plotting, references and file I/O are excluded. `results/profile.txt` contains actual profiling. Array storage of 225,232 bytes is not peak process memory; chunked parsing avoids loading all occupancy records simultaneously.

Code verification includes manufactured affine cases, a manually calculated irregular interpolation, independent PCHIP Hermite arithmetic, mask exclusion, input guards, source deduplication/unit tests and end-to-end CSV checks. Source/data consistency does not establish sensor calibration. The rubric, limitations, AI responsibility and student practice are documented in `docs` and `notes`.

Original code/documentation use the MIT licence. The university dataset and course materials have separate ownership and no public redistribution permission is established here. Raw ZIPs, the original workbook and course PDFs are excluded from Git. Use the documented course-data route for a full raw audit, and review prepared data sharing before publishing. The manual guide explains access for a private repository.

## Package and submit

The supplied clone has `main`, genuine local Git history and no remote. Publish it yourself following the guide, then give the assessor access. After any genuine personal-review changes, publish the final commit and create a fresh matching clone ZIP for Moodle. `python scripts/package_submission.py` can package a clean committed local project; it does not upload anything and removes a local clone's remote. The external manifest records its exact commit and checksum.

Submit the report, matching final repository-clone ZIP and accessible real GitHub URL through Moodle. The confirmed extension ends **midnight at the end of Sunday 25 October 2026, Melbourne**. Personally review and understand the work and add only truthful reflection before submitting. Book and attend the five-minute presentation plus three-minute questions, and upload slides at least 24 hours beforehand if used. Artifact creation does not complete those external responsibilities.
