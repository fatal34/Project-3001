# Dataset 2: independent source audit

The audit read both compressed CSVs in full without changing the supplied files. The environmental CSV was parsed record by record; the 9.1-million-row occupancy CSV was read in 250,000-row chunks. Both workbook worksheets were read completely. Files in **Example Data (Do not use)** were inventoried and hashed only, with at most the first CSV row recorded for identification. They are excluded from all analysis, fitting and validation.

## Recommendation

Use **offline reconstruction of missing CO₂ observations** as the project. Compare a previous-value baseline, piecewise linear interpolation, and shape-preserving piecewise cubic Hermite interpolation (PCHIP). Test contiguous artificial gaps in otherwise observed stretches, using chronological development and final evaluation blocks. Use actual elapsed seconds, and only evaluate inside observed bounds. This is an engineering data-quality study relevant to environmental monitoring, rather than a ventilation-rate or occupancy-estimation claim.

The defensible primary series is environmental sensor **6012002000869**, uniquely mapped by the workbook to **Building 60, room G.38, Compactus_upper, label EMS107**. It has **13,800 distinct embedded measurement times**, covering **29 February–13 June 2024 UTC**. Typical cadence is 600 seconds, with genuine irregular timing and gaps of up to 1,799 seconds. CO₂ observations span **403–646 ppm**. Repeated exports do not constitute additional independent observations.

Sensor **6012002000326** provides a possible external check after excluding its isolated 2023 measurement: it has a substantial 2025–2026 series, but its room is not mapped in the supplied workbook. Any use must be described as a separate sensor with unknown location. Three other sensors have only one or two unique measurement times and are unsuitable for reconstruction experiments.

## Environmental findings

- The ZIP has one CSV, **179,447 records**, eight columns, five sensor IDs, and no repeated database row IDs. Every status is `Processed`; every processing-error string is `NULL`.
- Each JSON payload is an array of variables, each with a `variable` dictionary and `values` list. Embedded `values[].time` is a Unix timestamp in seconds. All present measurements in a record share the same timestamp.
- **Use the embedded measurement time.** `createdate` and `processdate` are record processing times and can repeat old observations months or years later. The file name's May–December 2024 period is not a trustworthy description of the measurement dates.
- There are only **42,843 distinct (sensor, measurement-time) observations** across all five sensors. **136,604 rows repeat a sensor measurement time**. CO₂ and temperature values agree at every repeated measurement time, so deterministic deduplication is supported for those variables.
- CO₂ (`Carbon dioxide`, `ppm`) and temperature (`Temperature`, `°C`) occur and contain finite numeric values in all records. This does not imply every other variable is complete: formaldehyde has 113,380 null values; some payloads omit variable entries or have an empty values list.
- A natural gap is an absence of a timestamp from an irregular series. Missing CO₂ cannot be inferred solely from empty CSV cells: this export mostly repeats stale, nonempty payloads instead.
- Workbook `ENV` has 78 rows. Its ID **6012003000691** appears twice with conflicting rooms/labels (G.52/Workshop/ES2G14 and G.61/East Entrance/ES2G01). Do not arbitrarily choose one. Four of the five environmental IDs in the supplied CSV are absent from the workbook; the recommended primary series is the sole uniquely mapped observed ID.

| Environmental sensor | Export rows | Unique measurement times | Measurement interval UTC | Location status |
|---|---:|---:|---|---|
| 6012002000241 | 58,908 | 2 | Dec 2023 and May 2025 | Unmapped; frozen |
| 6012002000326 | 58,909 | 29,039 | Dec 2023; Sep 2025–Apr 2026 | Unmapped; optional secondary |
| 6012002000777 | 10,926 | 1 | May 2023 | Unmapped; frozen |
| 6012002000869 | 29,341 | 13,800 | Feb–Jun 2024 | Uniquely mapped; primary |
| 6012002000227 | 21,363 | 1 | Dec 2023 | Unmapped; frozen |

For the primary series, 15,541 records duplicate an earlier measurement time. Positive intervals have median 600 seconds, minimum 574 seconds, maximum 1,799 seconds. The most common intervals are 600 seconds (9,191), 601 (1,309), 599 (1,256) and 1,200 (899). There are no primary-series gaps exceeding one hour.

## Occupancy findings and exclusion

The occupancy CSV has **9,091,732 records**, eight columns, **one device UUID**, and **five distinct floor-space UUIDs**. `collecteddate` spans November 2023–April 2026, again extending far outside the file name. Headcounts are numeric integers from 0 to 72, with no missing or negative counts found. Status counts are 8,405,894 `CurrentlyOccupied`, 420,133 `RecentlyOccupied`, and 265,705 `NotOccupied`.

The workbook's second worksheet is explicitly named **`OCC (Incorrect Data - SpaceFloo`**. It has 89 mapping rows, a missing ID, questionable IDs with `(?)`, and a formula containing `#REF!`. Its sensor ID column uses MAC-like strings, which do not match the occupancy CSV's device UUID. Two supplied floor-space UUIDs match workbook rows (G.20 and G.25), but neither is the primary environmental room G.38. Three floor-space UUIDs are absent entirely, accounting for **5,696,467 records**. A time overlap therefore does not establish a valid spatial pairing. Occupancy is audited as supplied context and **excluded from model inputs and targets**.

## Reproducibility and limitations

`audit_sources.py` generates the adjacent JSON files, including source sizes and SHA-256 hashes, complete workbook contents, per-sensor variable ranges, embedded date ranges, cadence counts, and full-stream occupancy counts. Run `python data_audit/audit_sources.py --source-dir "/path/to/the/supplied/folder"` from the project root to repeat this independent audit elsewhere. An optional `--output-dir` redirects the JSON summaries. It requires NumPy, pandas and openpyxl. The main preparation workflow is `python scripts/prepare_data.py --source-dir "/path/to/the/supplied/folder"`; it produces the compact data used by the analysis.

The audit establishes export consistency, not sensor calibration, a room's true occupancy, an official ventilation requirement, or physical ground truth. Later artificial-gap errors compare reconstructed values to withheld sensor readings and must be described accordingly. Interpolation uses observations after the gap, so it supports retrospective recovery rather than real-time forecasting.

`independent_sample_check.json` records five deterministically sampled primary measurement times, each independently matched back to raw JSON without importing the preparation code. CO₂, temperature, humidity and ingestion counts all agree. Repeat this check with `python data_audit/check_prepared_samples.py --source-dir "/path/to/the/supplied/folder"`.
