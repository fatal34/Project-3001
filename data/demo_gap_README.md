# Recorded-data reconstruction demonstration

These demonstration files were created for this project from the prepared
Dataset 2 environmental observations. They are **not** files taken from the
supplied `Example Data` folder.

- Sensor: `6012002000869`, the uniquely mapped primary sensor.
- Partition: final chronological test block, beginning at full-series index
  11,040 (the last 20% of 13,800 observations).
- Window: the **first eligible six-reading gap** returned by the frozen
  `eligible_windows` procedure, starting at index 4 within that partition.
  The illustration was selected by timestamp eligibility, before inspecting its
  reconstruction errors.
- First withheld measurement: `2024-05-24T06:55:37+00:00` (UTC).
- Coordinates: original embedded measurement timestamps in Unix seconds.
- Withheld first-to-last span: 2,999 seconds. The interval between the retained
  anchor observations on either side is 4,199 seconds. Six missing readings
  at approximately ten-minute cadence are different from a 60-minute interval
  between those anchors.

`demo_gap_input.csv` contains four observed readings on each side and six blank
CO2 cells in the middle. `demo_gap_truth.csv` stores only the six original
withheld readings for separate scoring. The reconstruction command does **not**
read this truth file. `../results/demo_reconstruction.csv` contains the selected
linear interpolation and a status for every row. Observed cell text is retained.

From the repository root, create a new output file with:

```sh
python scripts/reconstruct_csv.py --input data/demo_gap_input.csv --output results/my_demo_reconstruction.csv
```

The default method is read from `results/selection_frozen.json`. Add
`--method previous`, `--method linear`, or `--method pchip` to select a method
explicitly. Existing output files require `--overwrite`; the input can never be
overwritten. The two input columns must be exactly `time_s,co2_ppm`, with seconds
and ppm as their units. A blank CO2 cell requests a reconstruction; `NaN`,
infinite values, negative CO2, duplicate times and unordered times are rejected.

The tool fills only groups of one to six consecutive blank rows with four
originally observed rows immediately before and after. Every timestamp step
through the full context and gap must be at most 900 seconds. It preserves
unsupported gaps as blank with status `unfilled_outside_validated_scope`.
The numerical study directly evaluated missing counts 1, 3 and 6; intermediate
counts are within this configured envelope and were not separately evaluated.
This tool uses observations after a gap and therefore performs offline
reconstruction rather than forecasting.

For this one demonstration, selected linear interpolation gives MAE
12.333333 ppm, RMSE 12.554663 ppm, maximum absolute error 13.857347 ppm, and
bias +3.333333 ppm against the six withheld recorded values. These are the
illustration's scores, not the pooled final-test scores and not errors against
independently calibrated physical ground truth.
