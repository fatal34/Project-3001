"""Run the frozen chronological gap-reconstruction study from prepared data."""
from __future__ import annotations
import argparse
import cProfile
import csv
import hashlib
import json
from pathlib import Path
import platform
import pstats
import sys
import time
import importlib.metadata
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from sensor_project.data import load_environment
from sensor_project.interpolation import reconstruct,scalar_linear,mask_block
from sensor_project.metrics import error_metrics

def write_csv(path, rows):
    """Save homogeneous dictionaries without reducing numerical precision."""
    if not rows: raise RuntimeError(f'No eligible evidence for {path}')
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)

def iso(seconds):
    """Format an embedded measurement time explicitly in UTC."""
    from datetime import datetime, timezone
    return datetime.fromtimestamp(float(seconds),timezone.utc).isoformat()

def eligible_windows(t,y,config):
    """Create artificial gaps using timestamp eligibility only, never errors."""
    context=config['context_points_each_side']; stride=config['start_stride_observations']
    windows=[];counts=[]
    for count in config['missing_counts']:
        candidates=0;accepted=0
        for start in range(context,len(t)-count-context+1,stride):
            candidates+=1
            left=start-context;right=start+count+context
            if np.any(np.diff(t[left:right])>config['maximum_observed_step_s']):continue
            kt,ky,qt,truth=mask_block(t,y,start,count,context)
            windows.append({'count':count,'start':start,'known_t':kt,'known_y':ky,
                            'query_t':qt,'truth':truth,'start_utc':iso(qt[0]),
                            'bracket_s':float(kt[context]-kt[context-1]),
                            'hidden_sample_span_s':float(qt[-1]-qt[0])})
            accepted+=1
        if not accepted:raise RuntimeError(f'No eligible windows for {count} missing observations')
        counts.append({'missing_count':count,'candidate_windows':candidates,'eligible_windows':accepted,
                       'excluded_windows':candidates-accepted})
    return windows,counts

def evaluate(partition,t,y,config):
    """Score identical hidden readings for all methods, retaining window data."""
    windows,counts=eligible_windows(t,y,config); rows=[];aggregates=[]
    for count in config['missing_counts']:
        matching=[window for window in windows if window['count']==count]
        for method in config['methods']:
            targets=[];predictions=[]
            for number,w in enumerate(matching):
                # Subtract a local origin before interpolation for readable,
                # well-scaled coordinates; elapsed intervals are unchanged.
                origin=w['known_t'][0]
                prediction=reconstruct(w['known_t']-origin,w['known_y'],w['query_t']-origin,method)
                targets.extend(w['truth']);predictions.extend(prediction)
                metrics=error_metrics(w['truth'],prediction)
                rows.append({'partition':partition,'method':method,'missing_count':count,
                             'window':number,'start_utc':w['start_utc'],
                             'bracket_duration_s':w['bracket_s'],
                             'hidden_first_to_last_span_s':w['hidden_sample_span_s'],**metrics})
            aggregates.append({'partition':partition,'method':method,'missing_count':count,
                               'windows':len(matching),'hidden_readings':len(targets),
                               **error_metrics(targets,predictions)})
    for row in counts:row['partition']=partition
    return aggregates,rows,counts,windows

def timed(function,repeats=7):
    """Measure repeated whole calls after warm-up, excluding I/O and plotting."""
    function(); samples=[]
    for _ in range(repeats):
        begin=time.perf_counter();function();samples.append(time.perf_counter()-begin)
    return {'median_runtime_s':float(np.median(samples)),
            'min_runtime_s':min(samples),'max_runtime_s':max(samples),'repeats':repeats}

def main():
    """Freeze method selection before final and secondary evaluation."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'results')
    args=parser.parse_args();out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    config=json.loads((ROOT/'configs/study.json').read_text())
    source=ROOT/'data/prepared/environment.csv'
    t,y=load_environment(source,config['primary_sensor_id']); n=len(t)
    first=int(n*config['development_fraction']);second=first+int(n*config['validation_fraction'])
    boundaries={'development':(0,first),'validation':(first,second),'test':(second,n)}
    partitions={name:{'observations':b-a,'start_utc':iso(t[a]),'end_utc':iso(t[b-1])}
                for name,(a,b) in boundaries.items()}
    a,b=boundaries['validation']; print('Method selection on the chronological validation block',flush=True)
    val,rows,counts,_=evaluate('validation',t[a:b],y[a:b],config)
    scores={method:float(np.mean([r['rmse'] for r in val if r['method']==method]))
            for method in config['methods']}
    minimum=min(scores.values());eligible=[method for method in config['simplicity_order']
        if scores[method]<=minimum*(1+config['relative_tie_tolerance'])+1e-14]
    selected=eligible[0]
    frozen={'selected_method':selected,'validation_macro_rmse_ppm':scores,'config':config,
            'prepared_data_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'evaluation_not_yet_performed':['test','secondary'],'retuning_permitted':False}
    (out/'selection_frozen.json').write_text(json.dumps(frozen,indent=2)+'\n')
    aggregate=val
    print(f'Frozen selected method: {selected}; validation scores {scores}',flush=True)
    examples=[]
    for name in ['test','secondary']:
        if name=='test':
            a,b=boundaries['test'];tx,yx=t[a:b],y[a:b]
        else:
            tx,yx=load_environment(source,config['secondary_sensor_id'])
            keep=tx>=config['secondary_min_unix_time_s'];tx,yx=tx[keep],yx[keep]
            partitions[name]={'observations':len(tx),'start_utc':iso(tx[0]),'end_utc':iso(tx[-1]),
                              'location_status':'unmapped; separate sensor, no room inference'}
        print(f'Final evaluation: {name}',flush=True)
        current,detail,eligible_counts,windows=evaluate(name,tx,yx,config)
        aggregate.extend(current);rows.extend(detail);counts.extend(eligible_counts)
        # Fixed first eligible six-reading test window, selected independently
        # of its reconstruction errors. Never choose a favourable illustration.
        if name=='test':
            w=next(w for w in windows if w['count']==max(config['missing_counts']))
            origin=w['known_t'][config['context_points_each_side']-1]
            for qt,truth in zip(w['query_t'],w['truth']):
                record={'time_from_left_anchor_min':float((qt-origin)/60),'truth_ppm':float(truth)}
                for method in config['methods']:
                    record[method]=float(reconstruct(w['known_t']-origin,w['known_y'],[qt-origin],method)[0])
                examples.append(record)
    print('Controlled scalar/vectorised implementation comparison',flush=True)
    td,yd=t[:first],y[:first];knots=np.arange(0,len(td),5)
    if knots[-1]!=len(td)-1:knots=np.append(knots,len(td)-1)
    kt,ky=td[knots]-td[0],yd[knots];query=td-td[0]
    scalar=scalar_linear(kt,ky,query);vector=reconstruct(kt,ky,query,'linear')
    difference=float(np.max(np.abs(scalar-vector)))
    timings=[]
    for name,function in [('scalar',lambda:scalar_linear(kt,ky,query)),
                          ('vectorized',lambda:reconstruct(kt,ky,query,'linear'))]:
        timings.append({'implementation':name,'known_points':len(kt),'query_points':len(query),
                        'max_output_difference_ppm':difference,**timed(function)})
    profiler=cProfile.Profile();profiler.runcall(scalar_linear,kt,ky,query)
    with (out/'profile.txt').open('w') as stream:
        pstats.Stats(profiler,stream=stream).strip_dirs().sort_stats('cumulative').print_stats(20)
    method_timings=[]
    va,vb=boundaries['validation'];bench, _=eligible_windows(t[va:vb],y[va:vb],config)
    for method in config['methods']:
        def operation():
            for w in bench:
                origin=w['known_t'][0]
                reconstruct(w['known_t']-origin,w['known_y'],w['query_t']-origin,method)
        method_timings.append({'method':method,'windows':len(bench),**timed(operation)})
    write_csv(out/'tables/metrics.csv',aggregate);write_csv(out/'tables/window_metrics.csv',rows)
    write_csv(out/'tables/window_eligibility.csv',counts);write_csv(out/'tables/example_gap.csv',examples)
    write_csv(out/'tables/optimisation.csv',timings);write_csv(out/'tables/method_runtime.csv',method_timings)
    summary={'selected_method':selected,'validation_macro_rmse_ppm':scores,'partitions':partitions,
             'config':config,'prepared_data_sha256':frozen['prepared_data_sha256'],
             'metrics':aggregate,'eligibility':counts,'optimisation':timings,'method_runtime':method_timings,
             'vectorization_speedup':timings[0]['median_runtime_s']/timings[1]['median_runtime_s'],
             'retained_benchmark_array_bytes':sum(v.nbytes for v in [kt,ky,query,scalar,vector]),
             'environment':{'python':platform.python_version(),'platform':platform.platform(),
                **{p:importlib.metadata.version(p) for p in ['numpy','scipy','pandas','matplotlib','pytest']}},
             'interpretation':'Errors against withheld readings, not independently calibrated physical truth.',
             'test_used_for_selection':False,'retuned_after_test':False}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({'selected':selected,'validation_scores':scores,
                      'test_metrics':[r for r in aggregate if r['partition']=='test'],
                      'vectorization_speedup':summary['vectorization_speedup']},indent=2))

if __name__=='__main__':main()
