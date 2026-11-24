#!/usr/bin/env python3
"""Render report-ready charts from validated full-run CSVs."""
import argparse
import csv
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

NAVY='#17324d'; BLUE='#277da1'; TEAL='#43aa8b'; AMBER='#f9a03f'; RED='#d55e56'; GREY='#536575'
plt.rcParams.update({'font.size':10,'axes.titlesize':15,'axes.labelsize':10,
                     'axes.spines.top':False,'axes.spines.right':False,
                     'figure.facecolor':'white','axes.facecolor':'white',
                     'savefig.facecolor':'white'})

def rows(path):
    with path.open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))

def finish(fig,ax,path,note):
    fig.text(.02,.015,note,fontsize=8,color=GREY)
    fig.tight_layout(rect=(0,.085,1,1))
    path.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(path,dpi=190,bbox_inches='tight')
    plt.close(fig)

def main():
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    q1=rows(a.results/'01_winter_beds.csv');q2=rows(a.results/'02_ed_crowding.csv')
    x=np.arange(len(q1));labels=[r['month_key'] for r in q1]
    fig,ax=plt.subplots(figsize=(12,5));ax2=ax.twinx()
    ax.bar(x,[int(r['overflow_admissions']) for r in q1],color=AMBER,width=.72,label='Overflow admissions')
    ax2.plot(x,[float(r['occupancy_pct']) for r in q1],color=BLUE,lw=2.4,marker='o',ms=3.5,label='Ward occupancy')
    ax.set_title('Winter ward pressure and overflow',loc='left',fontweight='bold',color=NAVY)
    ax.set_ylabel('Admissions without a ward bed');ax2.set_ylabel('Ward bed-day occupancy (%)')
    ax.set_xticks(x[::2],labels[::2],rotation=45,ha='right');ax.grid(axis='y',alpha=.2)
    ax.legend(loc='upper left');ax2.legend(loc='upper right')
    finish(fig,ax,a.out/'01_winter_beds.png','Synthetic AHD model, supplied full dataset. Occupancy is ward patient-days / 228 beds × days; open stays assumed one day.')

    fig,ax=plt.subplots(figsize=(12,5));ax2=ax.twinx()
    ax.plot(x,[float(r['median_wait_min']) for r in q2],color=BLUE,lw=2.5,marker='o',ms=3.5,label='Median ED wait')
    ax2.plot(x,[float(r['lwbs_pct']) for r in q2],color=RED,lw=2,marker='s',ms=3,label='Left without being seen')
    ax.set_title('ED waits rise with winter ward pressure',loc='left',fontweight='bold',color=NAVY)
    ax.set_ylabel('Median ED wait (minutes)');ax2.set_ylabel('Left without being seen (%)')
    ax.set_xticks(x[::2],labels[::2],rotation=45,ha='right');ax.grid(axis='y',alpha=.2)
    ax.legend(loc='upper left');ax2.legend(loc='upper right')
    finish(fig,ax,a.out/'02_ed_crowding.png','Synthetic AHD model, supplied full dataset. Association does not establish a causal effect of ward occupancy.')

    hf=rows(a.results/'03_heart_failure.csv');dx=rows(a.results/'04_coding_denials.csv')
    fb=rows(a.results/'08_billing_feedback.csv')
    groups=[('30-day readmission',[r['cohort'] for r in hf],[float(r['readmission_pct']) for r in hf]),
            ('Claim denial by coding',[r['coding_status'] for r in dx],[float(r['denial_pct']) for r in dx]),
            ('Billing complaint in feedback',[r['claim_outcome'] for r in fb],[float(r['billing_complaint_pct']) for r in fb])]
    fig,axes=plt.subplots(1,3,figsize=(12,4.7))
    for ax,(title,names,vals) in zip(axes,groups):
        ax.barh(range(len(vals)),vals,color=[RED,TEAL]);ax.set_yticks(range(len(vals)),names)
        ax.set_xlim(0,max(vals)*1.27);ax.set_xlabel('Percent');ax.set_title(title,loc='left',fontweight='bold',color=NAVY,fontsize=11)
        for i,v in enumerate(vals):ax.text(v+max(vals)*.03,i,f'{v:.1f}%',va='center',fontsize=9)
        ax.grid(axis='x',alpha=.2);ax.set_axisbelow(True)
    finish(fig,axes[0],a.out/'03_risk_and_feedback.png','Synthetic AHD model, supplied full dataset. Coding-denial result differs from the supplied answer key; see report.')

    st=rows(a.results/'06_drug_stockouts.csv')
    fig,ax=plt.subplots(figsize=(9,4.5));names={'RX004':'Ceftriaxone (RX004)','RX005':'Enoxaparin (RX005)'}
    labels=[f"{names.get(r['requested_drug'],r['requested_drug'])}\n{r['month_key']}" for r in st]
    delayed=[int(r['delayed']) for r in st];sub=[int(r['substituted']) for r in st]
    xx=np.arange(len(st));ax.bar(xx,delayed,color=AMBER,label='Delayed');ax.bar(xx,sub,bottom=delayed,color=BLUE,label='Substituted')
    ax.set_xticks(xx,labels);ax.set_ylabel('Affected dispense records');ax.set_title('Three planted drug stockout periods',loc='left',fontweight='bold',color=NAVY)
    ax.legend();ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    for i,r in enumerate(st):ax.text(i,int(r['affected_dispenses'])+35,r['affected_dispenses'],ha='center')
    finish(fig,ax,a.out/'04_drug_stockouts.png','Synthetic AHD model, supplied full dataset. ERP receipt transactions were absent in the preceding seven days for these records.')

    payer={}
    for r in rows(a.results/'05_payer_authorisation.csv'):
        if r['department'] in ('ORTH','BARI'):
            v=payer.setdefault(r['payer'],[0,0]);v[0]+=int(r['first_claims']);v[1]+=int(r['auth002_denials'])
    ordered=sorted(payer.items(),key=lambda kv:kv[1][1]/kv[1][0])
    fig,ax=plt.subplots(figsize=(9,4.8))
    yy=np.arange(len(ordered));vals=[100*v[1]/v[0] for _,v in ordered]
    ax.barh(yy,vals,color=[TEAL]*(len(ordered)-1)+[RED])
    ax.set_yticks(yy,[k for k,_ in ordered]);ax.set_xlim(0,44)
    ax.set_xlabel('AUTH-002 denials / first claims (%)')
    ax.set_title('Falcon prior-authorisation gap in ORTH and BARI',loc='left',fontweight='bold',color=NAVY)
    for i,v in enumerate(vals):ax.text(v+.5,i,f'{v:.1f}%',va='center')
    ax.grid(axis='x',alpha=.2);ax.set_axisbelow(True)
    finish(fig,ax,a.out/'06_payer_authorisation.png','Synthetic AHD model, supplied full dataset. Inpatient and day-case first claims, 2024–2025.')

    q7=a.results/'07_icu_deterioration.csv'
    if q7.exists():
        v=rows(q7);xx=[int(r['hour_before']) for r in v]
        fig,ax=plt.subplots(figsize=(9,4.5));ax2=ax.twinx()
        ax.plot(xx,[float(r['mean_hr']) for r in v],color=RED,marker='o',lw=2.5,label='Heart rate')
        ax2.plot(xx,[float(r['mean_spo2']) for r in v],color=BLUE,marker='s',lw=2.5,label='SpO₂')
        ax.invert_xaxis();ax.set_xticks([4,3,2,1]);ax.set_xlabel('Hours before recorded ICU event')
        ax.set_ylabel('Mean heart rate (bpm)');ax2.set_ylabel('Mean SpO₂ (%)')
        ax.set_title('Vitals deteriorate before ICU events',loc='left',fontweight='bold',color=NAVY)
        ax.grid(axis='y',alpha=.2);ax.legend(loc='upper left');ax2.legend(loc='upper right')
        finish(fig,ax,a.out/'05_icu_deterioration.png','Synthetic AHD model, supplied full dataset. Historical 4-hour windows; this is not a live alert test.')

if __name__=='__main__':main()
