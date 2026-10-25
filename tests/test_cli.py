"""End-to-end checks for the user-facing CSV reconstruction tool."""

import csv
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "reconstruct_csv.py"


def _write_input(path, times, values, *, header=("time_s", "co2_ppm")):
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(zip(times, values))


def _run(source, destination, *options):
    return subprocess.run([sys.executable, str(SCRIPT), "--input", str(source), "--output", str(destination), *options], capture_output=True, text=True)


@pytest.mark.parametrize("method", ["linear", "pchip"])
def test_cli_reconstructs_six_missing_affine_values_and_preserves_observed_text(tmp_path, method):
    source, destination = tmp_path / "input.csv", tmp_path / "output.csv"
    time_s = np.arange(14) * 600
    expected = 400 + np.arange(14) * 3
    values = [f"{value:.4f}" if index < 4 or index >= 10 else "" for index, value in enumerate(expected)]
    _write_input(source, time_s, values)
    before = source.read_bytes()
    result = _run(source, destination, "--method", method)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"method": method, "observed": 8, "reconstructed": 6, "unfilled": 0}
    rows = list(csv.DictReader(destination.open()))
    np.testing.assert_allclose([float(row["co2_ppm"]) for row in rows], expected, atol=1e-12)
    assert [row["status"] for row in rows] == ["observed"] * 4 + ["reconstructed"] * 6 + ["observed"] * 4
    assert rows[0]["co2_ppm"] == "400.0000"
    assert source.read_bytes() == before


def test_cli_default_method_uses_frozen_selection(tmp_path):
    source, destination = tmp_path / "input.csv", tmp_path / "output.csv"
    _write_input(source, np.arange(9) * 600, [400, 401, 402, 403, "", 405, 406, 407, 408])
    result = _run(source, destination)
    assert result.returncode == 0, result.stderr
    frozen = json.loads((ROOT / "results" / "selection_frozen.json").read_text())
    assert json.loads(result.stdout)["method"] == frozen["selected_method"]


@pytest.mark.parametrize("case", ["edge", "seven_missing", "natural_long_step", "insufficient_original_context"])
def test_cli_keeps_out_of_scope_gaps_blank_with_status(tmp_path, case):
    source, destination = tmp_path / "input.csv", tmp_path / "output.csv"
    times = np.arange(16, dtype=float) * 600
    values = [str(400 + index) for index in range(16)]
    if case == "edge":
        values[:2] = [""] * 2
        blank_indices = [0, 1]
    elif case == "seven_missing":
        values[4:11] = [""] * 7
        blank_indices = list(range(4, 11))
    elif case == "natural_long_step":
        values[4:10] = [""] * 6
        times[8:] += 400  # One 1,000 s step is outside the <= 900 s envelope.
        blank_indices = list(range(4, 10))
    else:
        values[4] = ""
        values[7] = ""  # Each four-row context includes an original blank.
        blank_indices = [4, 7]
    _write_input(source, times, values)
    result = _run(source, destination, "--method", "linear")
    assert result.returncode == 0, result.stderr
    rows = list(csv.DictReader(destination.open()))
    for index in blank_indices:
        assert rows[index]["co2_ppm"] == ""
        assert rows[index]["status"] == "unfilled_outside_validated_scope"
    assert json.loads(result.stdout)["reconstructed"] == 0


@pytest.mark.parametrize(
    "times,values,header",
    [
        ([0, 0, 600], [400, "", 410], ("time_s", "co2_ppm")),
        ([0, 1200, 600], [400, "", 410], ("time_s", "co2_ppm")),
        ([0, "NaN", 1200], [400, "", 410], ("time_s", "co2_ppm")),
        ([0, 600, 1200], [400, "NaN", 410], ("time_s", "co2_ppm")),
        ([0, 600, 1200], [400, "inf", 410], ("time_s", "co2_ppm")),
        ([0, 600, 1200], [400, -1, 410], ("time_s", "co2_ppm")),
        ([0, 600, 1200], [400, "", 410], ("time_min", "co2_percent")),
    ],
)
def test_cli_rejects_invalid_input_without_writing_output(tmp_path, times, values, header):
    source, destination = tmp_path / "input.csv", tmp_path / "output.csv"
    _write_input(source, times, values, header=header)
    result = _run(source, destination, "--method", "linear")
    assert result.returncode != 0
    assert "error:" in result.stderr
    assert not destination.exists()


def test_cli_rejects_input_overwrite_and_requires_explicit_output_replacement(tmp_path):
    source, destination = tmp_path / "input.csv", tmp_path / "output.csv"
    _write_input(source, [0, 600], [400, 410])
    before = source.read_bytes()
    assert _run(source, source, "--method", "linear", "--overwrite").returncode != 0
    assert source.read_bytes() == before
    destination.write_text("preserve me")
    assert _run(source, destination, "--method", "linear").returncode != 0
    assert destination.read_text() == "preserve me"
    assert _run(source, destination, "--method", "linear", "--overwrite").returncode == 0


def test_cli_previous_override_uses_last_observed_value(tmp_path):
    source, destination = tmp_path / "input.csv", tmp_path / "output.csv"
    _write_input(source, np.arange(9) * 600, [400, 401, 402, 403, "", 405, 406, 407, 408])
    result = _run(source, destination, "--method", "previous")
    assert result.returncode == 0, result.stderr
    rows = list(csv.DictReader(destination.open()))
    assert float(rows[4]["co2_ppm"]) == 403.0
