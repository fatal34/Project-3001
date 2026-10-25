"""Read-only audit of the supplied Dataset 2 workbook and compressed CSVs.

This script creates summaries, never changes the supplied data, and does not use
the examples explicitly labelled 'Do not use' as analysis observations.
"""
from __future__ import annotations

import argparse
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

OUT = Path(__file__).resolve().parent


def write(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding='utf-8')


def utc(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat()


def audit_workbook(source_dir):
    wb = openpyxl.load_workbook(source_dir/'Sensor ID and Locations.xlsx', read_only=True, data_only=False)
    result = {}
    for sheet in wb:
        rows = list(sheet.values)
        result[sheet.title] = {'columns': list(rows[0]), 'rows': [list(r) for r in rows[1:]]}
    write('workbook_contents.json', result)
    return result


def audit_environment(source_dir, workbook):
    path = source_dir/'5EnvSensor_MayToDec2024_180kRows.zip'
    units, statuses, errors, lengths, formats = Counter(), Counter(), Counter(), Counter(), Counter()
    rows = 0
    row_ids, duplicate_row_ids = set(), 0
    sensors = defaultdict(lambda: {'count': 0, 'times': [], 'values': defaultdict(list), 'creation_dates': [], 'duplicate_payloads': 0, 'payload_keys':set(), 'bad_payloads': 0})
    variable_counts = Counter()
    missing_values = Counter()
    multi_times = 0
    entry_lengths = Counter()
    with ZipFile(path) as z:
        filename = next(n for n in z.namelist() if n.endswith('.csv'))
        with z.open(filename) as b:
            reader = csv.DictReader(io.TextIOWrapper(b, encoding='utf-8-sig'))
            header = reader.fieldnames
            for row in reader:
                rows += 1
                sid = row['sensorid']
                obj = sensors[sid]
                obj['count'] += 1
                obj['creation_dates'].append(row['createdate'])
                statuses[row['status']] += 1
                errors[row['processing_errors']] += 1
                if row['id'] in row_ids:
                    duplicate_row_ids += 1
                row_ids.add(row['id'])
                key = row['jsondata']
                if key in obj['payload_keys']:
                    obj['duplicate_payloads'] += 1
                obj['payload_keys'].add(key)
                try:
                    payload = json.loads(row['jsondata'])
                except (ValueError, TypeError):
                    obj['bad_payloads'] += 1
                    continue
                lengths[len(payload)] += 1
                times_this = set()
                for field in payload:
                    var = field['variable']
                    name = var['name']
                    units[(name,var['unit'])] += 1
                    variable_counts[name] += 1
                    entry_lengths[len(field['values'])] += 1
                    for point in field['values']:
                        t, value = point.get('time'), point.get('value')
                        if t is None or value is None:
                            missing_values[name] += 1
                            continue
                        times_this.add(t)
                        obj['values'][name].append((t,value))
                if len(times_this)>1:
                    multi_times += 1
                if times_this:
                    obj['times'].append(min(times_this))
                if rows % 50000 == 0:
                    print('Environmental rows:', rows, flush=True)
    env_rows = workbook['ENV']['rows']
    labels = defaultdict(list)
    for row in env_rows:
        labels[str(int(row[5]))].append(dict(zip(workbook['ENV']['columns'], row)))
    summary_sensors = {}
    all_months = Counter()
    for sid,obj in sensors.items():
        unique = sorted(set(obj['times']))
        diffs = np.diff(unique)
        months=Counter(utc(t)[:7] for t in obj['times'])
        all_months.update(months)
        variables={}
        for name,pairs in obj['values'].items():
            nums=np.array([p[1] for p in pairs], dtype=float)
            by_time=defaultdict(set)
            for t,v in pairs:
                by_time[t].add(v)
            variables[name] = {
                'count':len(nums),'nonfinite':int(np.sum(~np.isfinite(nums))),
                'min':float(np.nanmin(nums)), 'max':float(np.nanmax(nums)),
                'quantiles':dict(zip(['q01','q25','q50','q75','q99'],map(float,np.nanquantile(nums,[.01,.25,.5,.75,.99])))),
                'unique_measurement_times':len(by_time),
                'conflicting_duplicate_timestamps':sum(len(v)>1 for v in by_time.values()),
            }
        summary_sensors[sid]={
            'records':obj['count'],'unique_measurement_times':len(unique),
            'duplicate_measurement_times':len(obj['times'])-len(unique),
            'duplicate_payloads':obj['duplicate_payloads'],
            'bad_payloads':obj['bad_payloads'],
            'measurement_start_utc':utc(unique[0]) if unique else None,
            'measurement_end_utc':utc(unique[-1]) if unique else None,
            'record_created_start':min(obj['creation_dates']), 'record_created_end':max(obj['creation_dates']),
            'measurement_month_counts_utc':dict(sorted(months.items())),
            'cadence_seconds': {'min':int(diffs.min()),'median':float(np.median(diffs)), 'max':int(diffs.max()),'most_common':Counter(diffs.tolist()).most_common(12),
                'gaps_over_1h':int(sum(diffs>3600)), 'gaps_over_6h':int(sum(diffs>21600)), 'gaps_over_24h':int(sum(diffs>86400))} if len(diffs) else None,
            'location_matches':labels.get(sid, []), 'variables':variables,
        }
    result={
        'source_zip':path.name, 'csv':filename,'csv_header':header,'records':rows,
        'unique_row_ids':len(row_ids),'duplicate_row_ids':duplicate_row_ids,
        'sensor_count':len(sensors),'status_counts':dict(statuses),'processing_error_counts':dict(errors),
        'variables':[{'name':k[0],'unit':k[1],'records':v} for k,v in units.items()],
        'variable_entry_counts':dict(variable_counts),'missing_measurement_values':dict(missing_values),
        'variables_per_payload':dict(lengths),'values_per_variable_entry':dict(entry_lengths),'payloads_with_multiple_measurement_times':multi_times,
        'measurement_month_counts_utc':dict(sorted(all_months.items())),
        'duplicate_workbook_environmental_ids':{k:v for k,v in labels.items() if len(v)>1},
        'data_ids_absent_from_workbook':sorted(set(sensors)-set(labels)),
        'workbook_ids_absent_from_data':sorted(set(labels)-set(sensors)),
        'sensors':summary_sensors,
    }
    write('environment_audit.json',result)
    print('Environmental audit complete', rows, len(sensors), flush=True)
    return result


def audit_occupancy(source_dir, workbook):
    path=source_dir/'5occupancySensor_MayToDec2024_9MRows.zip'
    rows=0
    devices,spaces,statuses,heads,month=Counter(),Counter(),Counter(),Counter(),Counter()
    per_space=defaultdict(lambda:{'count':0,'start':None,'end':None,'headcount_min':None,'headcount_max':None,'negative_headcounts':0,'missing_headcounts':0})
    minimum,maximum=None,None
    with ZipFile(path) as z:
        filename=next(n for n in z.namelist() if n.endswith('.csv'))
        with z.open(filename) as b:
            for chunk in pd.read_csv(b,chunksize=250000,dtype=str,keep_default_na=False):
                header=list(chunk.columns)
                rows+=len(chunk)
                devices.update(chunk['deviceid'].value_counts().to_dict())
                spaces.update(chunk['floorspaceid'].value_counts().to_dict())
                statuses.update(chunk['occupancystatus'].value_counts().to_dict())
                heads.update(chunk['headcount'].value_counts().to_dict())
                dates=chunk['collecteddate']
                month.update(dates.str.slice(0,7).value_counts().to_dict())
                lo,hi=dates.min(),dates.max()
                minimum=min(minimum,lo) if minimum else lo
                maximum=max(maximum,hi) if maximum else hi
                for sid,group in chunk.groupby('floorspaceid'):
                    item=per_space[sid]
                    item['count']+=len(group)
                    lo,hi=group['collecteddate'].min(),group['collecteddate'].max()
                    item['start']=min(item['start'],lo) if item['start'] else lo
                    item['end']=max(item['end'],hi) if item['end'] else hi
                    h=pd.to_numeric(group['headcount'],errors='coerce')
                    item['missing_headcounts']+=int(h.isna().sum())
                    item['negative_headcounts']+=int((h<0).sum())
                    if h.notna().any():
                        hmin,hmax=float(h.min()),float(h.max())
                        item['headcount_min']=min(item['headcount_min'],hmin) if item['headcount_min'] is not None else hmin
                        item['headcount_max']=max(item['headcount_max'],hmax) if item['headcount_max'] is not None else hmax
                if rows%1000000==0:
                    print('Occupancy rows:',rows,flush=True)
    sheet_name=next(k for k in workbook if k!='ENV')
    wrows=workbook[sheet_name]['rows']
    by_space=defaultdict(list)
    for row in wrows:
        by_space[row[6]].append(row)
    result={
        'source_zip':path.name,'csv':filename,'csv_header':header,'records':rows,
        'device_count':len(devices),'space_count':len(spaces),'device_counts':dict(devices),'space_counts':dict(spaces),
        'status_counts':dict(statuses),'headcount_counts':dict(heads),'record_month_counts_local':dict(sorted(month.items())),
        'collecteddate_start':minimum,'collecteddate_end':maximum,
        'workbook_sheet':sheet_name,'workbook_row_count':len(wrows),
        'space_ids_matching_workbook':sorted(set(spaces)&set(by_space)),
        'space_ids_not_in_workbook':sorted(set(spaces)-set(by_space)),
        'data_rows_with_unmatched_space_ids':sum(v for k,v in spaces.items() if k not in by_space),
        'device_ids_matching_workbook_ID':sorted(set(devices)&{r[3] for r in wrows}),
        'mapping_warning':'Workbook occupancy sheet explicitly states Incorrect Data. Space/Floor mapping is not treated as reliable.',
        'per_space':dict(per_space),
    }
    write('occupancy_audit.json',result)
    print('Occupancy audit complete',rows,len(spaces),flush=True)
    return result


def inventory(source_dir):
    result=[]
    for path in sorted(source_dir.rglob('*')):
        if not path.is_file():
            continue
        item={'path':str(path.relative_to(source_dir)), 'bytes':path.stat().st_size, 'excluded_example':'Example Data (Do not use)' in path.parts}
        sha=hashlib.sha256()
        with path.open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''):
                sha.update(chunk)
        item['sha256']=sha.hexdigest()
        if path.suffix.lower()=='.csv':
            with path.open('r',encoding='utf-8-sig',errors='replace',newline='') as f:
                reader=csv.reader(f)
                item['first_csv_row_only']=next(reader)
        result.append(item)
    write('source_inventory.json',result)


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, required=True, help='Folder with the two original ZIPs and location workbook')
    parser.add_argument('--output-dir', type=Path, default=OUT)
    args = parser.parse_args()
    OUT = args.output_dir
    OUT.mkdir(parents=True,exist_ok=True)
    inventory(args.source_dir)
    workbook=audit_workbook(args.source_dir)
    audit_environment(args.source_dir, workbook)
    audit_occupancy(args.source_dir, workbook)
