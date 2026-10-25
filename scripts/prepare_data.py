"""Prepare Dataset 2 without extracting or modifying its original source ZIPs."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sensor_project.data import prepare_sources


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path, help="Folder holding both supplied ZIPs and Sensor ID and Locations.xlsx")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "prepared")
    args = parser.parse_args()
    result = prepare_sources(args.source_dir, args.output_dir)
    print(json.dumps({"prepared_directory": str(args.output_dir.resolve()), "environment_rows": result["environment"]["csv_rows"], "environment_unique_observations": result["environment"]["unique_observations"], "occupancy_rows_audited": result["occupancy"]["csv_rows"], "primary_sensor_id": result["primary_sensor_id"]}, indent=2))


if __name__ == "__main__":
    main()
