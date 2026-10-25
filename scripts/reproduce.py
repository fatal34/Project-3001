"""Reproduce tests, numerical comparisons, demo, figures, API HTML and report."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]

def main():
    """Verify fresh results separately while preserving submitted timing data."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir',type=Path,help='Optional folder containing both original ZIPs and location workbook')
    args=parser.parse_args()
    env=dict(os.environ,PYTHONPATH=str(ROOT/'src'),MPLBACKEND='Agg',MPLCONFIGDIR=str(ROOT/'.mplconfig'))
    def run(*command):
        subprocess.run([sys.executable,*command],cwd=ROOT,env=env,check=True)
    temp=ROOT/'tmp';temp.mkdir(exist_ok=True)
    if args.source_dir:
        run('scripts/prepare_data.py','--source-dir',str(args.source_dir.resolve()),
            '--output-dir',str(temp/'reprepared_data'))
        for name in ['environment.csv','occupancy_summary.csv']:
            if (temp/'reprepared_data'/name).read_bytes()!=(ROOT/'data/prepared'/name).read_bytes():
                raise RuntimeError(f'Fresh raw-source preparation differs: {name}')
        print('Raw-source preparation matches the bundled prepared data.',flush=True)
    run('-m','pytest','-q','--html=reports/test_report.html','--self-contained-html','--junitxml=reports/test_results.xml')
    fresh=temp/'reproduced_results'
    run('scripts/run_study.py','--output-dir',str(fresh))
    saved=json.loads((ROOT/'results/summary.json').read_text())
    new=json.loads((fresh/'summary.json').read_text())
    if saved['selected_method']!=new['selected_method'] or saved['prepared_data_sha256']!=new['prepared_data_sha256']:
        raise RuntimeError('Frozen method or prepared input hash did not reproduce')
    key=lambda row:(row['partition'],row['method'],row['missing_count'])
    old_rows={key(row):row for row in saved['metrics']};new_rows={key(row):row for row in new['metrics']}
    if old_rows.keys()!=new_rows.keys():raise RuntimeError('Metric coverage changed')
    largest=0.0
    for identity,old in old_rows.items():
        current=new_rows[identity]
        if any(old[k]!=current[k] for k in ['windows','hidden_readings']):raise RuntimeError('Evaluation counts changed')
        for metric in ['mae','rmse','max_abs_error','bias']:
            difference=abs(old[metric]-current[metric]);largest=max(largest,difference)
            if difference>1e-9:raise RuntimeError(f'Numerical reproduction failed: {identity} {metric}')
    run('scripts/reconstruct_csv.py','--input','data/demo_gap_input.csv',
        '--output','tmp/reproduced_demo.csv','--overwrite')
    if (temp/'reproduced_demo.csv').read_bytes()!=(ROOT/'results/demo_reconstruction.csv').read_bytes():
        raise RuntimeError('Demo reconstruction did not reproduce exactly')
    run('scripts/make_figures.py');run('scripts/generate_docs.py');run('scripts/build_report.py')
    record={'workflow_exit_code':0,'selected_method':saved['selected_method'],
            'metric_rows_checked':len(old_rows),'maximum_numerical_difference':largest,
            'numerical_tolerance':1e-9,'demo_byte_identical':True,
            'fresh_timings_location':'tmp/reproduced_results','submitted_timings_preserved':True,
            'raw_source_reaudit_performed':args.source_dir is not None}
    (temp/'reproduction_status.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record,indent=2));print('Full workflow complete. Submitted timing evidence is preserved.')

if __name__=='__main__':main()
