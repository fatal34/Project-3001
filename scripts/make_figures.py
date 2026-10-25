"""Build scientific figures from preserved Dataset 2 evidence, without retuning."""
from pathlib import Path
import json
import os
import sys
os.environ.setdefault('MPLCONFIGDIR',str(Path(__file__).resolve().parents[1]/'.mplconfig'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from sensor_project.data import load_environment
COLORS={'previous':'#B86730','linear':'#087F8C','pchip':'#6B669A'}
LABELS={'previous':'Previous value','linear':'Linear','pchip':'PCHIP'}

def finish(fig,name):
    """Save identical PNG/vector-PDF views with explicit scientific labels."""
    out=ROOT/'results/figures';out.mkdir(parents=True,exist_ok=True)
    fig.tight_layout(pad=1.2)
    fig.savefig(out/f'{name}.png',dpi=190,bbox_inches='tight',facecolor='white')
    fig.savefig(out/f'{name}.pdf',bbox_inches='tight',facecolor='white')
    plt.close(fig)

def main():
    """Regenerate the five report figures from submitted tables and readings."""
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,
                         'axes.spines.right':False,'axes.labelcolor':'#233746',
                         'text.color':'#18364A','axes.titleweight':'normal'})
    summary=json.loads((ROOT/'results/summary.json').read_text())
    metrics=pd.read_csv(ROOT/'results/tables/metrics.csv')
    t,y=load_environment(ROOT/'data/prepared/environment.csv',summary['config']['primary_sensor_id'])
    dates=pd.to_datetime(t,unit='s',utc=True)
    fig,ax=plt.subplots(figsize=(9.0,3.25))
    for name,color in [('development','#E8EDF1'),('validation','#DAEEED'),('test','#F9E8D9')]:
        part=summary['partitions'][name]
        ax.axvspan(pd.Timestamp(part['start_utc']),pd.Timestamp(part['end_utc']),color=color,label=name.title())
    ax.plot(dates,y,color='#18364A',lw=.55)
    ax.set(ylabel='Recorded CO2 (ppm)',xlabel='Embedded measurement date (UTC)',
           title='Primary sensor: unique measurements and chronological partitions')
    ax.legend(frameon=False,ncol=3,fontsize=8,loc='upper right')
    finish(fig,'data_timeline')

    fig,axes=plt.subplots(1,2,figsize=(9,3.5),gridspec_kw={'width_ratios':[.9,1.5]})
    methods=list(COLORS)
    axes[0].bar(range(3),[summary['validation_macro_rmse_ppm'][m] for m in methods],color=list(COLORS.values()))
    axes[0].set_xticks(range(3),[LABELS[m] for m in methods],rotation=20)
    axes[0].set(ylabel='Macro RMSE (ppm)',title='Validation selection')
    x=np.arange(3)
    for index,m in enumerate(methods):
        rows=metrics[(metrics.partition=='test')&(metrics.method==m)].sort_values('missing_count')
        axes[1].bar(x+(index-1)*.24,rows.rmse,.24,label=LABELS[m],color=COLORS[m])
    axes[1].set_xticks(x,['1 (~10 min)','3 (~30 min)','6 (~60 min)'])
    axes[1].set(ylabel='Pooled RMSE (ppm)',xlabel='Hidden readings (nominal missing duration)',title='Later primary test period')
    axes[1].legend(frameon=False,fontsize=8,ncol=3,loc='upper center',bbox_to_anchor=(.5,1.0))
    axes[1].set_ylim(0,14)
    for i,n in enumerate([102,70,22]):axes[1].text(i,.35,f'{n} windows',ha='center',fontsize=8,color='white',fontweight='bold')
    finish(fig,'method_comparison')

    fig,axes=plt.subplots(1,2,figsize=(9,3.5))
    for ax,key,label in zip(axes,['rmse','max_abs_error'],['Pooled RMSE (ppm)','Maximum absolute error (ppm)']):
        for m in methods:
            rows=metrics[(metrics.partition=='secondary')&(metrics.method==m)].sort_values('missing_count')
            ax.plot([1,3,6],rows[key],marker='o',lw=1.4,label=LABELS[m],color=COLORS[m])
        ax.set(xticks=[1,3,6],xlabel='Consecutive hidden readings',ylabel=label)
    axes[0].set_title('Secondary signal: unknown room location',loc='left')
    axes[0].legend(frameon=False,fontsize=8)
    axes[1].set_title('Long-gap extremes remain material',loc='left')
    finish(fig,'secondary_check')

    example=pd.read_csv(ROOT/'results/tables/example_gap.csv')
    fig,ax=plt.subplots(figsize=(9,3.2))
    ax.plot(example.time_from_left_anchor_min,example.truth_ppm,'o-',color='#18364A',label='Withheld readings',lw=1.4)
    for m in methods:ax.plot(example.time_from_left_anchor_min,example[m],marker='.',lw=1.3,color=COLORS[m],label=LABELS[m])
    ax.set(xlabel='Minutes after observed left anchor',ylabel='CO2 (ppm)',
           title='First eligible six-reading test window')
    ax.set_ylim(float(example.truth_ppm.min())-3,float(example.truth_ppm.max())+8)
    ax.legend(frameon=False,ncol=4,fontsize=8,loc='upper center')
    finish(fig,'example_gap')

    opt=pd.read_csv(ROOT/'results/tables/optimisation.csv')
    fig,axes=plt.subplots(1,2,figsize=(9,3.4))
    axes[0].bar(['Scalar loop','Vectorised'],1000*opt.median_runtime_s,color=['#B86730','#087F8C'])
    for i,r in opt.iterrows():axes[0].text(i,1000*r.median_runtime_s+.055,f'{1000*r.median_runtime_s:.3f} ms',ha='center',fontsize=9)
    axes[0].set(ylabel='Median call runtime (ms)',title='Same linear interpolant, 8,280 queries',ylim=(0,3.3))
    rt=pd.read_csv(ROOT/'results/tables/method_runtime.csv')
    axes[1].bar([LABELS[m] for m in rt.method],1000*rt.median_runtime_s,color=[COLORS[m] for m in rt.method])
    axes[1].set(ylabel='Median whole-batch runtime (ms)',title='158 validation windows; seven repeats')
    for i,r in rt.iterrows():axes[1].text(i,1000*r.median_runtime_s+.15,f'{1000*r.median_runtime_s:.2f}',ha='center',fontsize=9)
    axes[1].set_ylim(0,15)
    finish(fig,'performance')
    print('Saved five scientific PNG/PDF figure pairs')

if __name__=='__main__':main()
