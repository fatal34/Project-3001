"""Reconstruct eligible short CO2 gaps in a CSV without changing observations.

Run from the repository root::

    python scripts/reconstruct_csv.py --input data/demo_gap_input.csv \
        --output results/demo_reconstruction.csv

The exact input columns are ``time_s,co2_ppm``. Times are measurement seconds
(Unix seconds or elapsed seconds), never row numbers. A blank CO2 cell requests
offline reconstruction. The default method is read from the frozen validation
selection. This tool does not overwrite its input or feed reconstructed values
back into later gaps.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sensor_project import reconstruct

METHODS = ("previous", "linear", "pchip")
CONTEXT_POINTS = 4
MAX_MISSING_COUNT = 6
MAXIMUM_STEP_S = 900.0
UNFILLED = "unfilled_outside_validated_scope"


def read_input_csv(path: Path | str) -> tuple[list[dict[str, str]], np.ndarray, np.ndarray]:
    """Read a strictly ordered CO2 CSV while retaining observed cell text.

    Parameters
    ----------
    path : pathlib.Path or str
        CSV with exactly ``time_s`` and ``co2_ppm`` columns. Every time must be
        finite and strictly increasing. Nonblank CO2 must be finite and >= 0 ppm.

    Returns
    -------
    records : list of dict
        Original cell text, so observed values can be written without rounding.
    time_s : numpy.ndarray
        Measurement times as float64 seconds.
    co2_ppm : numpy.ndarray
        Numeric CO2 values, with NaN used internally only for blank query cells.

    Raises
    ------
    ValueError
        If columns, row lengths, numbers or ordering are invalid, or fewer than
        two measurement times are supplied. Text such as ``NaN`` is invalid;
        missing query values must be genuinely blank cells.
    OSError
        If the input cannot be read.

    Examples
    --------
    See ``data/demo_gap_input.csv`` for a measured-data example with six blanks.
    """
    records: list[dict[str, str]] = []
    times: list[float] = []
    values: list[float] = []
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["time_s", "co2_ppm"]:
            raise ValueError("input columns must be exactly time_s,co2_ppm in that order; units are seconds and ppm")
        for line, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"CSV line {line} must have exactly two cells")
            try:
                current_time = float(row["time_s"])
            except (TypeError, ValueError) as error:
                raise ValueError(f"CSV line {line}: time_s must be numeric seconds") from error
            if not np.isfinite(current_time):
                raise ValueError(f"CSV line {line}: time_s must be finite")
            if times and current_time <= times[-1]:
                raise ValueError(f"CSV line {line}: time_s must be strictly increasing without duplicates")
            text = row["co2_ppm"].strip()
            if not text:
                current_value = np.nan
            else:
                try:
                    current_value = float(text)
                except ValueError as error:
                    raise ValueError(f"CSV line {line}: nonblank co2_ppm must be numeric") from error
                if not np.isfinite(current_value) or current_value < 0:
                    raise ValueError(f"CSV line {line}: nonblank co2_ppm must be finite and nonnegative")
            records.append(row)
            times.append(current_time)
            values.append(current_value)
    if len(times) < 2:
        raise ValueError("input must contain at least two measurement times")
    return records, np.asarray(times, dtype=np.float64), np.asarray(values, dtype=np.float64)


def reconstruct_csv(
    input_path: Path | str,
    output_path: Path | str,
    method: str | None = None,
    *,
    selection_path: Path | str = ROOT / "results" / "selection_frozen.json",
    overwrite: bool = False,
) -> dict[str, int | str]:
    """Write guarded offline reconstructions and a status for every input row.

    Parameters
    ----------
    input_path : pathlib.Path or str
        Input CSV described by :func:`read_input_csv`.
    output_path : pathlib.Path or str
        Separate output CSV. Its parent directories are created if necessary.
    method : {"previous", "linear", "pchip"} or None, default None
        An explicit method, or the selected method from ``selection_path``.
    selection_path : pathlib.Path or str, keyword-only
        Frozen validation selection containing a valid ``selected_method``.
    overwrite : bool, default False, keyword-only
        Permit replacing an existing output file. Replacing input is prohibited
        regardless of this flag, including a symlink or hardlink to input.

    Returns
    -------
    dict
        Selected method and counts for observed, reconstructed and unfilled rows.

    Raises
    ------
    ValueError
        If data or method is invalid, selection cannot identify a supported
        method, or input and output designate the same file.
    FileExistsError
        If the output exists and ``overwrite`` is false.
    OSError
        If a file cannot be read or written.

    Notes
    -----
    Only 1--6 consecutive blanks are eligible, with four originally observed
    rows immediately before and after, and every timestamp step through that
    context and gap at most 900 seconds. The study directly tested gap sizes
    1, 3 and 6; intermediate counts are within the configured operating envelope
    rather than separately evaluated sizes. Unsupported gaps remain blank with
    status ``unfilled_outside_validated_scope``. Eligible rows get status
    ``reconstructed``; original nonblank cells get ``observed`` and retain their
    exact original text. All gap decisions use the original missingness mask.
    """
    source = Path(input_path).resolve()
    destination = Path(output_path).resolve()
    if source == destination or (source.exists() and destination.exists() and source.samefile(destination)):
        raise ValueError("output must be a separate file; overwriting the input is prohibited")
    if destination.exists() and not overwrite:
        raise FileExistsError(f"output already exists: {destination}; pass --overwrite to replace it")
    if method is None:
        try:
            selection = json.loads(Path(selection_path).read_text(encoding="utf-8"))
            method = selection["selected_method"]
        except (ValueError, KeyError, TypeError) as error:
            raise ValueError("frozen selection must contain a valid selected_method") from error
    if not isinstance(method, str) or method not in METHODS:
        raise ValueError("method must be previous, linear, or pchip")
    records, time_s, values = read_input_csv(source)
    missing = np.isnan(values)
    prediction_text = ["" if missing[index] else row["co2_ppm"] for index, row in enumerate(records)]
    statuses = [UNFILLED if is_missing else "observed" for is_missing in missing]
    start = 0
    while start < len(values):
        if not missing[start]:
            start += 1
            continue
        stop = start + 1
        while stop < len(values) and missing[stop]:
            stop += 1
        left = start - CONTEXT_POINTS
        right = stop + CONTEXT_POINTS
        eligible = 1 <= stop - start <= MAX_MISSING_COUNT and left >= 0 and right <= len(values)
        if eligible:
            eligible = not (np.any(missing[left:start]) or np.any(missing[stop:right]))
        if eligible:
            eligible = bool(np.all(np.diff(time_s[left:right]) <= MAXIMUM_STEP_S))
        if eligible:
            # The right context is observed, so this is offline reconstruction.
            # Neither withheld truth nor a previous reconstruction enters inputs.
            known_t = np.concatenate((time_s[left:start], time_s[stop:right]))
            known_y = np.concatenate((values[left:start], values[stop:right]))
            origin = known_t[0]
            reconstructed = reconstruct(known_t - origin, known_y, time_s[start:stop] - origin, method)
            for index, prediction in zip(range(start, stop), reconstructed):
                prediction_text[index] = repr(float(prediction))
                statuses[index] = "reconstructed"
        start = stop
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Replace only after a full valid file has been written; errors do not leave
    # a half-written output that could be mistaken for a completed result.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8", dir=destination.parent, delete=False) as stream:
            temporary = Path(stream.name)
            writer = csv.DictWriter(stream, fieldnames=["time_s", "co2_ppm", "status"])
            writer.writeheader()
            for row, value_text, status in zip(records, prediction_text, statuses):
                writer.writerow({"time_s": row["time_s"], "co2_ppm": value_text, "status": status})
        temporary.replace(destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return {
        "method": method,
        "observed": statuses.count("observed"),
        "reconstructed": statuses.count("reconstructed"),
        "unfilled": statuses.count(UNFILLED),
    }


def main() -> None:
    """Parse command-line paths, run reconstruction, and print row counts.

    Invalid input produces a readable error and a nonzero exit status. See
    ``python scripts/reconstruct_csv.py --help`` for usage and method choices.
    """
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", required=True, type=Path, help="CSV columns: time_s,co2_ppm; blank CO2 cells are queries")
    parser.add_argument("--output", required=True, type=Path, help="Separate output CSV with row status")
    parser.add_argument("--method", choices=METHODS, default=None, help="Override the frozen validation method")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing output; input can never be overwritten")
    arguments = parser.parse_args()
    try:
        summary = reconstruct_csv(arguments.input, arguments.output, arguments.method, overwrite=arguments.overwrite)
    except (OSError, ValueError) as error:
        parser.exit(2, f"error: {error}\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
