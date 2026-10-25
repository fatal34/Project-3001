"""Independent examples for time, duplicate, unit and loader data contracts."""
import csv
import io
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pytest

from sensor_project.data import _environment, load_environment


def _record(row_id=1, timestamp=1709251200, co2=500, unit="ppm", created="2024-03-01 12:00:00+00"):
    fields = [
        {"variable": {"name": "Carbon dioxide", "unit": unit}, "values": [{"time": timestamp, "value": co2}]},
        {"variable": {"name": "Temperature", "unit": "°C"}, "values": [{"time": timestamp, "value": 20.0}]},
        {"variable": {"name": "Humidity", "unit": "HR%"}, "values": [{"time": timestamp, "value": 50}]},
    ]
    return {"id": row_id, "sensorid": "test", "jsondata": json.dumps(fields), "createdate": created, "status": "Processed", "processing_errors": "NULL"}


def _zip(tmp_path, rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    path = tmp_path / "source.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr("observations.csv", stream.getvalue())
    return path


def test_embedded_time_and_agreeing_repeated_export_are_preserved(tmp_path):
    """Processing an old payload later must not create a new measurement."""
    rows = [_record(), _record(row_id=2, created="2025-01-01 12:00:00+00"), _record(row_id=3, timestamp=1709251800, co2=510)]
    destination = tmp_path / "prepared.csv"
    audit = _environment(_zip(tmp_path, rows), {}, destination)
    with destination.open(newline="") as stream:
        prepared = list(csv.DictReader(stream))
    assert [int(r["time_s"]) for r in prepared] == [1709251200, 1709251800]
    assert [int(r["ingest_count"]) for r in prepared] == [2, 1]
    assert [float(r["co2_ppm"]) for r in prepared] == [500, 510]
    assert audit["csv_rows"] == 3
    assert audit["unique_observations"] == 2
    assert audit["duplicate_rows_removed"] == 1
    assert audit["records_with_createdate_over_1h_after_or_before_measurement"] == 3
    assert all(r["location_status"] == "unmapped" for r in prepared)


def test_conflicting_duplicate_measurement_rejected(tmp_path):
    rows = [_record(), _record(row_id=2, co2=501)]
    with pytest.raises(ValueError, match="Conflicting selected values"):
        _environment(_zip(tmp_path, rows), {}, tmp_path / "out.csv")


def test_unit_mismatch_rejected_without_guessing_conversion(tmp_path):
    with pytest.raises(ValueError, match="Unexpected Carbon dioxide unit"):
        _environment(_zip(tmp_path, [_record(unit="percent")]), {}, tmp_path / "out.csv")


def test_incomplete_or_unsynchronised_payload_rejected(tmp_path):
    row = _record()
    fields = json.loads(row["jsondata"])
    fields[1]["values"][0]["time"] += 1
    row["jsondata"] = json.dumps(fields)
    with pytest.raises(ValueError, match="do not share one measurement time"):
        _environment(_zip(tmp_path, [row]), {}, tmp_path / "out.csv")


def test_missing_selected_variable_rejected(tmp_path):
    row = _record()
    row["jsondata"] = json.dumps(json.loads(row["jsondata"])[:2])
    with pytest.raises(ValueError, match="Incomplete selected variables"):
        _environment(_zip(tmp_path, [row]), {}, tmp_path / "out.csv")


def test_ambiguous_room_mapping_is_not_resolved_arbitrarily(tmp_path):
    locations = {"test": [{"Building": 1, "Floor/Room": "A"}, {"Building": 1, "Floor/Room": "B"}]}
    destination = tmp_path / "out.csv"
    _environment(_zip(tmp_path, [_record()]), locations, destination)
    with destination.open(newline="") as stream:
        row = next(csv.DictReader(stream))
    assert row["location_status"] == "ambiguous"
    assert row["room"] == ""


def test_loader_selects_sensor_and_sorts_without_resampling(tmp_path):
    path = tmp_path / "environment.csv"
    path.write_text("sensor_id,time_s,co2_ppm\na,1200,510\nb,500,900\na,600,500\n", encoding="utf-8")
    times, values = load_environment(path, "a")
    np.testing.assert_array_equal(times, [600, 1200])
    np.testing.assert_array_equal(values, [500, 510])


@pytest.mark.parametrize("body,message", [
    ("a,600,500\na,600,500\n", "unique and strictly increasing"),
    ("a,600,500\na,1200,nan\n", "finite"),
    ("a,600,500\na,1200,-1\n", "nonnegative"),
    ("a,600,500\n", "fewer than two"),
])
def test_loader_rejects_invalid_data(tmp_path, body, message):
    path = tmp_path / "environment.csv"
    path.write_text("sensor_id,time_s,co2_ppm\n" + body, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_environment(path, "a")


def test_loader_rejects_missing_schema(tmp_path):
    path = tmp_path / "environment.csv"
    path.write_text("sensor_id,time_s\na,600\na,1200\n", encoding="utf-8")
    with pytest.raises(ValueError, match="required columns"):
        load_environment(path, "a")
