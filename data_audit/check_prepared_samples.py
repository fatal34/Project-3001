"""Independently compare five reproducible prepared samples with raw JSON."""
import argparse
import csv
import io
import json
import random
from pathlib import Path
from zipfile import ZipFile


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--prepared", type=Path, default=root / "data/prepared/environment.csv")
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("independent_sample_check.json"))
    args = parser.parse_args()
    with args.prepared.open(newline="", encoding="utf-8") as stream:
        primary = [r for r in csv.DictReader(stream) if r["sensor_id"] == "6012002000869"]
    wanted = {int(r["time_s"]): r for r in random.Random(3001).sample(primary, 5)}
    found = {t: [] for t in wanted}
    with ZipFile(args.source_dir / "5EnvSensor_MayToDec2024_180kRows.zip") as archive:
        with archive.open(next(n for n in archive.namelist() if n.endswith(".csv"))) as raw:
            for row in csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig")):
                if row["sensorid"] != "6012002000869":
                    continue
                by_name = {x["variable"]["name"]: x for x in json.loads(row["jsondata"])}
                point = by_name["Carbon dioxide"]["values"][0]
                timestamp = int(point["time"])
                if timestamp not in wanted:
                    continue
                for name, column in [("Carbon dioxide", "co2_ppm"), ("Temperature", "temperature_c"), ("Humidity", "humidity_rh_percent")]:
                    raw_point = by_name[name]["values"][0]
                    if int(raw_point["time"]) != timestamp or float(raw_point["value"]) != float(wanted[timestamp][column]):
                        raise ValueError(f"Sample mismatch: {timestamp}, {name}")
                found[timestamp].append(row["id"])
    checks = []
    for timestamp, row in sorted(wanted.items()):
        if not found[timestamp] or len(found[timestamp]) != int(row["ingest_count"]):
            raise ValueError(f"Missing raw sample or incorrect ingest_count at {timestamp}")
        checks.append({"sensor_id": row["sensor_id"], "time_s": timestamp, "time_utc": row["time_utc"],
                       **{column: float(row[column]) for column in ["co2_ppm", "temperature_c", "humidity_rh_percent"]},
                       "matching_raw_database_row_ids": found[timestamp], "ingest_count_verified": True, "all_three_variables_match": True})
    result = {"selection": "Five primary sensor unique measurement times sampled by random.Random(3001), independently read through csv/json without importing preparation code. All matching raw rows were checked.", "checks": checks, "all_passed": True}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("All five independent prepared-to-raw checks passed.")


if __name__ == "__main__":
    main()
