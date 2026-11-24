#!/usr/bin/env python3
"""Prepare source-preserving, tabular Hive landing files from the AHD kit.

Python is used only for format normalization (CSV/JSON/XML and timestamp variants).
All aggregations and cross-source joins remain in the Member 7 HQL files.
"""
import argparse
import csv
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

GST = timezone(timedelta(hours=4))
DEPTS = {
    'CARDIOLOGY': 'CARD', 'CARDIO': 'CARD', 'ORTHOPAEDICS': 'ORTH',
    'ORTHOPEDICS': 'ORTH', 'ORTHO': 'ORTH',
    'BARIATRICS': 'BARI', 'BARIATRIC': 'BARI', 'BARIATRIC SURGERY': 'BARI',
    'GENERAL MEDICINE': 'GIM', 'GENERAL INTERNAL MEDICINE': 'GIM',
    'INTERNAL MEDICINE': 'GIM', 'IM': 'GIM',
    'GENERAL SURGERY': 'GSURG', 'GEN SURGERY': 'GSURG', 'SURG': 'GSURG',
    'EMERGENCY': 'ED', 'EMERGENCY DEPARTMENT': 'ED', 'ER': 'ED',
    'INTENSIVE CARE': 'ICU', 'CRITICAL CARE': 'ICU',
    'ONCOLOGY': 'ONC', 'ONCO': 'ONC',
    'OBSTETRICS AND GYNAECOLOGY': 'OBGY', 'OBSTETRICS & GYNAECOLOGY': 'OBGY',
    'OB/GYN': 'OBGY', 'OBGYN': 'OBGY',
    'PAEDIATRICS': 'PED', 'PAEDS': 'PED', 'PEDIATRICS': 'PED',
    'NEUROLOGY': 'NEUR', 'NEURO': 'NEUR',
    'ENDOCRINOLOGY': 'ENDO', 'ENDOCRINE': 'ENDO',
    'DERMATOLOGY': 'DERM', 'DERMA': 'DERM',
}
DX_RE = re.compile(r'^[A-TV-Z][0-9][0-9AB](\.[0-9A-TV-Z]{1,4})?$')


def ts(value):
    if value is None or str(value).strip() == '':
        return ''
    s = str(value).strip()
    if s.isdigit() and len(s) == 13:
        return datetime.fromtimestamp(int(s) / 1000, timezone.utc).astimezone(GST).strftime('%Y-%m-%d %H:%M:%S')
    for fmt in ('%d/%m/%Y %H:%M', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y',
                '%d-%b-%Y %H:%M', '%d-%b-%Y %H:%M:%S'):
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            pass
    try:
        d = datetime.fromisoformat(s.replace('Z', '+00:00'))
        if d.tzinfo:
            d = d.astimezone(GST)
        return d.strftime('%Y-%m-%d %H:%M:%S')
    except ValueError:
        return ''


def dept(value):
    s = (value or '').strip().upper()
    return DEPTS.get(s, s)


def text(value):
    if value is None or value == '':
        return r'\N'
    return str(value).replace('\t', ' ').replace('\r', ' ').replace('\n', ' ')


def write_rows(dst, rows):
    dst.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with dst.open('w', encoding='utf-8', newline='') as f:
        for row in rows:
            f.write('\t'.join(text(v) for v in row) + '\n')
            n += 1
    print(dst.parent.name, n, flush=True)


def csv_rows(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        yield from csv.DictReader(f)


def encounters(src):
    for r in csv_rows(src / 'ehr_cerner/encounters.csv'):
        yield (r['encounter_id'], r['mrn'], r['encounter_type'], dept(r['department']),
               ts(r['admit_ts']), ts(r['discharge_ts']), r['bed_id'],
               r['ed_wait_minutes'], r['discharge_disposition'], r['readmission_flag'])


def diagnoses(src):
    for r in csv_rows(src / 'ehr_cerner/diagnoses.csv'):
        code = r['icd10_code'].strip().upper()
        if '.' not in code and len(code) > 3:
            code = code[:3] + '.' + code[3:]
        valid = bool(DX_RE.fullmatch(code) and r['description'].strip())
        yield (r['encounter_id'], r['seq'], code, r['dx_type'], int(valid))


def claims(src):
    for r in csv_rows(src / 'billing_oracle/claims.csv'):
        yield (r['claim_id'], r['encounter_id'], r['mrn'], r['payer'],
               ts(r['submitted_date']), r['status'], r['denial_code'],
               r['resubmission_of'])


def dispenses(src):
    for file in sorted((src / 'pharmacy_api').glob('dispense_*.jsonl')):
        with file.open(encoding='utf-8') as f:
            for line in f:
                r = json.loads(line)
                patient = r.get('patient') or {}
                drug = r.get('drug') or {}
                yield (r.get('dispense_id', r.get('id')),
                       r.get('encounter_id', patient.get('encounter')),
                       r.get('mrn', patient.get('mrn')),
                       r.get('drug_code', drug.get('code')),
                       r.get('drug_name', drug.get('name')),
                       r.get('qty', r.get('quantity')),
                       ts(r.get('dispensed_at', r.get('timestamp'))),
                       r.get('status'), r.get('substituted_for'))


def inventory(src):
    for file in sorted((src / 'erp_oracle').glob('inventory_*.xml')):
        for _, node in ET.iterparse(file, events=('end',)):
            if node.tag == 'Txn':
                yield (node.attrib.get('id'), node.findtext('ItemCode'),
                       node.findtext('Type'), node.findtext('Qty'),
                       ts(node.findtext('Timestamp')))
                node.clear()


def feedback(src):
    for r in csv_rows(src / 'feedback/patient_feedback.csv'):
        yield (r['feedback_id'], ts(r['submitted_at']), r['encounter_id'],
               r['rating'], r['comment'])


def events(src):
    for r in csv_rows(src / 'icu_monitors/icu_events.csv'):
        yield (r['event_id'], r['bed_id'], r['mrn'], r['encounter_id'],
               ts(r['event_ts']), r['event_type'])


def vitals(src):
    for file in sorted((src / 'icu_monitors/vitals_stream').glob('vitals_*.jsonl')):
        with file.open(encoding='utf-8') as f:
            for line in f:
                r = json.loads(line)
                clock = ts(r['ts'])
                d = datetime.strptime(clock, '%Y-%m-%d %H:%M:%S')
                if r['bed_id'] in ('ICU-07', 'ICU-15') and d >= datetime(2025, 10, 1):
                    d -= timedelta(minutes=7)
                yield (r['bed_id'], r['mrn'], d.strftime('%Y-%m-%d %H:%M:%S'),
                       r.get('hr'), r.get('spo2'), r.get('rr'), r.get('sbp'))


def months(_src):
    for year in (2024, 2025):
        for month in range(1, 13):
            yield (f'{year}-{month:02d}', f'{year}-{month:02d}-01',
                   f'{year + (month == 12)}-{month % 12 + 1:02d}-01')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', type=Path, required=True, help='sample_2pct or generated full data root')
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    for name, fn in [('encounters', encounters), ('diagnoses', diagnoses),
                     ('claims', claims), ('dispenses', dispenses),
                     ('inventory', inventory), ('feedback', feedback),
                     ('events', events), ('vitals', vitals), ('months', months)]:
        write_rows(a.out / name / 'part-00000', fn(a.input))


if __name__ == '__main__':
    main()
