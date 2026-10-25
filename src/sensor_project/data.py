"""Prepare and validate the supplied Dataset 2 environmental observations.

Measurement timestamps come from the JSON ``values[].time`` field, expressed as
Unix seconds. Database processing timestamps are audited but never substituted
for measurement time. Repeated, agreeing observations are deduplicated.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import openpyxl
import pandas as pd

PRIMARY_SENSOR_ID = "6012002000869"
ENVIRONMENT_ZIP = "5EnvSensor_MayToDec2024_180kRows.zip"
OCCUPANCY_ZIP = "5occupancySensor_MayToDec2024_9MRows.zip"
LOCATION_WORKBOOK = "Sensor ID and Locations.xlsx"
VARIABLES = {
    "Carbon dioxide": ("co2_ppm", "ppm"),
    "Temperature": ("temperature_c", "°C"),
    "Humidity": ("humidity_rh_percent", "HR%"),
}


def _utc(seconds: float) -> str:
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat()


def _hash(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def _workbook(path: Path) -> tuple[dict, dict[str, list[dict]], dict[str, list[dict]]]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=False)
    content = {}
    env_locations = defaultdict(list)
    occupancy_locations = defaultdict(list)
    for sheet in workbook:
        rows = list(sheet.values)
        header = list(rows[0])
        content[sheet.title] = {"columns": header, "rows": [list(row) for row in rows[1:]]}
        for row in rows[1:]:
            item = dict(zip(header, row))
            if sheet.title == "ENV":
                identifier = str(int(item["ID"]))
                env_locations[identifier].append(item)
            else:
                occupancy_locations[str(item.get("SpaceId"))].append(item)
    workbook.close()
    return content, dict(env_locations), dict(occupancy_locations)


def _environment(path: Path, locations: dict, output: Path) -> dict:
    observations = {}
    record_counts, units, statuses, errors = Counter(), Counter(), Counter(), Counter()
    row_ids = set()
    duplicate_row_ids = 0
    mismatched_processing_times = 0
    creation_start = creation_end = None
    rows = 0
    with ZipFile(path) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
        if len(names) != 1:
            raise ValueError("Environmental ZIP must contain exactly one CSV.")
        with archive.open(names[0]) as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig"))
            required = {"id", "sensorid", "jsondata", "createdate", "status", "processing_errors"}
            if not required.issubset(reader.fieldnames or []):
                raise ValueError("Environmental CSV is missing required columns.")
            for row in reader:
                rows += 1
                sid = row["sensorid"].strip()
                record_counts[sid] += 1
                statuses[row["status"]] += 1
                errors[row["processing_errors"]] += 1
                if row["id"] in row_ids:
                    duplicate_row_ids += 1
                row_ids.add(row["id"])
                creation_start = min(creation_start, row["createdate"]) if creation_start else row["createdate"]
                creation_end = max(creation_end, row["createdate"]) if creation_end else row["createdate"]
                try:
                    payload = json.loads(row["jsondata"])
                except (ValueError, TypeError) as error:
                    raise ValueError(f"Invalid JSON at environmental CSV record {rows}.") from error
                by_time = defaultdict(dict)
                for field in payload:
                    name = field["variable"]["name"]
                    unit = field["variable"]["unit"]
                    units[(name, unit)] += 1
                    if name not in VARIABLES:
                        continue
                    column, expected_unit = VARIABLES[name]
                    if unit != expected_unit:
                        raise ValueError(f"Unexpected {name} unit {unit!r}; expected {expected_unit!r}.")
                    for value in field["values"]:
                        timestamp = float(value["time"])
                        number = float(value["value"])
                        if not np.isfinite(timestamp) or not np.isfinite(number):
                            raise ValueError(f"Nonfinite selected observation at record {rows}.")
                        if column in by_time[timestamp] and by_time[timestamp][column] != number:
                            raise ValueError(f"Conflicting repeated variable within record {rows}.")
                        by_time[timestamp][column] = number
                if len(by_time) != 1:
                    raise ValueError(f"Selected variables do not share one measurement time at record {rows}.")
                timestamp, values = next(iter(by_time.items()))
                if set(values) != {v[0] for v in VARIABLES.values()}:
                    raise ValueError(f"Incomplete selected variables at environmental record {rows}.")
                if values["co2_ppm"] < 0 or not 0 <= values["humidity_rh_percent"] <= 100:
                    raise ValueError(f"Invalid selected physical value at record {rows}.")
                created_s = datetime.fromisoformat(row["createdate"]).timestamp()
                if abs(created_s - timestamp) > 3600:
                    mismatched_processing_times += 1
                key = (sid, timestamp)
                if key in observations:
                    existing = observations[key]
                    if any(existing[column] != number for column, number in values.items()):
                        raise ValueError(f"Conflicting selected values at sensor/time {key}.")
                    existing["ingest_count"] += 1
                else:
                    observations[key] = {**values, "ingest_count": 1}
    fields = ["sensor_id", "time_s", "time_utc", "co2_ppm", "temperature_c", "humidity_rh_percent", "ingest_count", "location_status", "building", "room", "area", "physical_label"]
    per_sensor = {}
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for (sid, timestamp), values in sorted(observations.items()):
            matches = locations.get(sid, [])
            status = "unique" if len(matches) == 1 else "unmapped" if not matches else "ambiguous"
            location = matches[0] if status == "unique" else {}
            writer.writerow({"sensor_id": sid, "time_s": int(timestamp) if timestamp.is_integer() else timestamp, "time_utc": _utc(timestamp), **values,
                             "location_status": status, "building": location.get("Building", ""), "room": location.get("Floor/Room", ""), "area": location.get("Area", ""), "physical_label": location.get("Physical Label", "")})
        for sid in sorted(record_counts):
            selected = sorted((t, v) for (s, t), v in observations.items() if s == sid)
            times = np.array([t for t, _ in selected])
            co2 = np.array([v["co2_ppm"] for _, v in selected])
            gaps = np.diff(times)
            per_sensor[sid] = {
                "export_rows": record_counts[sid], "unique_observations": len(times),
                "duplicate_rows_removed": record_counts[sid] - len(times),
                "measurement_start_utc": _utc(times[0]), "measurement_end_utc": _utc(times[-1]),
                "co2_min_ppm": float(co2.min()), "co2_max_ppm": float(co2.max()),
                "median_positive_interval_s": float(np.median(gaps)) if len(gaps) else None,
                "max_interval_s": float(gaps.max()) if len(gaps) else None,
                "location_matches": locations.get(sid, []),
            }
    return {"csv_member": names[0], "csv_rows": rows, "unique_observations": len(observations), "duplicate_rows_removed": rows - len(observations),
            "duplicate_database_row_ids": duplicate_row_ids, "conflicting_selected_duplicates": 0, "sensor_count": len(per_sensor), "sensor_summaries": per_sensor,
            "status_counts": dict(statuses), "processing_error_counts": dict(errors),
            "variable_units": [{"name": k[0], "unit": k[1], "record_entries": v} for k, v in units.items()],
            "records_with_createdate_over_1h_after_or_before_measurement": mismatched_processing_times,
            "createdate_start": creation_start, "createdate_end": creation_end,
            "time_policy": "Embedded Unix measurement time; createdate/processdate never used as observation time.",
            "duplicate_policy": "Require agreement of CO2, temperature and humidity; merge equal sensor/time observations and retain ingest_count; reject conflicts."}


def _occupancy(path: Path, locations: dict, output: Path) -> dict:
    rows = 0
    device_counts, status_counts, month_counts = Counter(), Counter(), Counter()
    spaces = defaultdict(lambda: {"csv_rows": 0, "collected_start": None, "collected_end": None, "headcount_min": None, "headcount_max": None, "missing_or_nonfinite_headcounts": 0, "negative_headcounts": 0})
    with ZipFile(path) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
        if len(names) != 1:
            raise ValueError("Occupancy ZIP must contain exactly one CSV.")
        with archive.open(names[0]) as raw:
            for chunk in pd.read_csv(raw, chunksize=250000, dtype=str, keep_default_na=False):
                required = {"deviceid", "floorspaceid", "collecteddate", "headcount", "occupancystatus"}
                if not required.issubset(chunk.columns):
                    raise ValueError("Occupancy CSV is missing required columns.")
                rows += len(chunk)
                device_counts.update(chunk["deviceid"].value_counts().to_dict())
                status_counts.update(chunk["occupancystatus"].value_counts().to_dict())
                month_counts.update(chunk["collecteddate"].str.slice(0, 7).value_counts().to_dict())
                for sid, group in chunk.groupby("floorspaceid"):
                    item = spaces[sid]
                    item["csv_rows"] += len(group)
                    low, high = group["collecteddate"].min(), group["collecteddate"].max()
                    item["collected_start"] = min(item["collected_start"], low) if item["collected_start"] else low
                    item["collected_end"] = max(item["collected_end"], high) if item["collected_end"] else high
                    counts = pd.to_numeric(group["headcount"], errors="coerce").to_numpy(dtype=float)
                    valid = counts[np.isfinite(counts)]
                    item["missing_or_nonfinite_headcounts"] += int(np.sum(~np.isfinite(counts)))
                    item["negative_headcounts"] += int(np.sum(valid < 0))
                    if len(valid):
                        low, high = float(valid.min()), float(valid.max())
                        item["headcount_min"] = min(item["headcount_min"], low) if item["headcount_min"] is not None else low
                        item["headcount_max"] = max(item["headcount_max"], high) if item["headcount_max"] is not None else high
    fields = ["floorspace_id", "csv_rows", "collected_start", "collected_end", "headcount_min", "headcount_max", "missing_or_nonfinite_headcounts", "negative_headcounts", "workbook_match_count", "mapping_status", "used_for_modelling"]
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for sid, values in sorted(spaces.items()):
            writer.writerow({"floorspace_id": sid, **values, "workbook_match_count": len(locations.get(sid, [])), "mapping_status": "workbook_explicitly_incorrect", "used_for_modelling": False})
    return {"csv_member": names[0], "csv_rows": rows, "space_count": len(spaces), "device_counts": dict(device_counts), "status_counts": dict(status_counts), "month_counts_local": dict(sorted(month_counts.items())),
            "spaces_matching_workbook": sorted(set(spaces) & set(locations)),
            "rows_with_unmapped_space": sum(v["csv_rows"] for k, v in spaces.items() if k not in locations),
            "excluded_from_modelling": True, "exclusion_reason": "Workbook occupancy sheet is labelled Incorrect Data; selected environmental room lacks verified occupancy co-location."}


def prepare_sources(source_dir: Path, output_dir: Path) -> dict:
    """Stream both supplied ZIPs and produce compact, auditable prepared data.

    Parameters
    ----------
    source_dir : pathlib.Path
        Folder containing both original ZIPs and the sensor-location workbook.
    output_dir : pathlib.Path
        Folder for ``environment.csv``, ``occupancy_summary.csv`` and
        ``source_audit.json``. Existing files with those names are regenerated.

    Returns
    -------
    dict
        Source hashes, workbook contents, cleaning decisions and stream counts.

    Raises
    ------
    FileNotFoundError
        If any required supplied source is missing.
    ValueError
        If the source schema, units, finite values or duplicate consistency fail.

    Notes
    -----
    The excluded example folder is inventoried without analysis. Individual
    occupancy records are never exported. No room mapping is guessed.
    """
    source_dir, output_dir = Path(source_dir), Path(output_dir)
    required = [source_dir / name for name in [ENVIRONMENT_ZIP, OCCUPANCY_ZIP, LOCATION_WORKBOOK]]
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(path)
    output_dir.mkdir(parents=True, exist_ok=True)
    inventory = [{"name": p.name, "bytes": p.stat().st_size, "sha256": _hash(p)} for p in required]
    example_inventory = []
    example_dir = source_dir / "Example Data (Do not use)"
    if example_dir.is_dir():
        for path in sorted(example_dir.rglob("*")):
            if not path.is_file():
                continue
            item = {"name": str(path.relative_to(source_dir)), "bytes": path.stat().st_size, "excluded_from_analysis": True}
            if path.suffix.lower() == ".csv":
                with path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
                    first = next(csv.reader(stream), [])
                item["first_row_only"] = first
                item["first_row_columns"] = len(first)
                item["row_count"] = "not read: excluded example"
            elif path.suffix.lower() == ".png":
                from PIL import Image
                with Image.open(path) as image:
                    item["image_dimensions_px"] = list(image.size)
            example_inventory.append(item)
    workbook, env_locations, occ_locations = _workbook(source_dir / LOCATION_WORKBOOK)
    environmental = _environment(source_dir / ENVIRONMENT_ZIP, env_locations, output_dir / "environment.csv")
    occupancy = _occupancy(source_dir / OCCUPANCY_ZIP, occ_locations, output_dir / "occupancy_summary.csv")
    audit = {"sources": inventory, "excluded_examples": example_inventory, "workbook": workbook,
             "environment": environmental, "occupancy": occupancy, "primary_sensor_id": PRIMARY_SENSOR_ID,
             "analysis_scope": "Retrospective artificial-gap CO2 reconstruction; not real-time forecasting, physical ventilation validation or occupancy inference."}
    (output_dir / "source_audit.json").write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    return audit


def load_environment(path: Path, sensor_id: str = PRIMARY_SENSOR_ID) -> tuple[np.ndarray, np.ndarray]:
    """Load one prepared sensor without resampling or silent deduplication.

    Parameters
    ----------
    path : pathlib.Path or str
        Prepared CSV with sensor_id, time_s (Unix seconds) and co2_ppm columns.
    sensor_id : str, default PRIMARY_SENSOR_ID
        Exact sensor identifier, preserved as text rather than inferred location.

    Returns
    -------
    times_s : numpy.ndarray, shape (n,)
        At least two finite, unique Unix times sorted in increasing order.
    co2_ppm : numpy.ndarray, shape (n,)
        Matching finite nonnegative recorded carbon-dioxide concentrations.

    Raises
    ------
    FileNotFoundError
        If the prepared CSV is absent.
    ValueError
        If schema, numerical values, unique times or sensor coverage is invalid.

    Examples
    --------
    >>> times_s, co2_ppm = load_environment("data/prepared/environment.csv")
    """
    frame = pd.read_csv(Path(path), dtype={"sensor_id": str})
    required = {"sensor_id", "time_s", "co2_ppm"}
    if not required.issubset(frame.columns):
        raise ValueError("Prepared environmental CSV lacks required columns.")
    frame = frame.loc[frame["sensor_id"] == str(sensor_id)].sort_values("time_s")
    if len(frame) < 2:
        raise ValueError(f"Sensor {sensor_id} has fewer than two prepared observations.")
    times = frame["time_s"].to_numpy(dtype=float)
    values = frame["co2_ppm"].to_numpy(dtype=float)
    if not np.all(np.isfinite(times)) or not np.all(np.isfinite(values)):
        raise ValueError("Prepared times and CO2 must be finite.")
    if np.any(np.diff(times) <= 0):
        raise ValueError("Prepared times must be unique and strictly increasing.")
    if np.any(values < 0):
        raise ValueError("Prepared CO2 values must be nonnegative.")
    return times, values
