#!/usr/bin/env python3
"""Independent DuckDB check of Member 7 measures on normalized kit data.

This is a validation run, not evidence that the Hive HQL ran. Writes eight CSVs.
Requires duckdb (see requirements.txt). No invented rows or answer-key values.
"""
import argparse
from pathlib import Path
import duckdb

SCHEMAS = {
 'encounters': 'encounter_id mrn encounter_type department admit_ts discharge_ts bed_id ed_wait_minutes discharge_disposition readmission_flag',
 'diagnoses': 'encounter_id seq icd10_code dx_type dx_valid',
 'claims': 'claim_id encounter_id mrn payer submitted_ts status denial_code resubmission_of',
 'dispenses': 'dispense_id encounter_id mrn drug_code drug_name qty dispensed_ts status substituted_for',
 'inventory': 'record_id drug_code txn_type qty txn_ts',
 'feedback': 'feedback_id submitted_ts encounter_id rating comment',
 'events': 'event_id bed_id mrn encounter_id event_ts event_type',
 'vitals': 'bed_id mrn vital_ts hr spo2 rr sbp',
 'months': 'month_key start_date next_date',
}

SQL = {
 '01_winter_beds': r"""
WITH e AS (SELECT * EXCLUDE rn FROM
  (SELECT *,row_number() OVER(PARTITION BY encounter_id ORDER BY admit_ts) rn
   FROM encounters WHERE encounter_type='IP') WHERE rn=1),
bed AS (SELECT m.month_key,
 SUM(CASE WHEN e.bed_id LIKE 'W%' THEN greatest(0,
  date_diff('day',greatest(cast(e.admit_ts AS DATE),cast(m.start_date AS DATE)),
  least(coalesce(cast(e.discharge_ts AS DATE),cast(e.admit_ts AS DATE)+INTERVAL 1 DAY),cast(m.next_date AS DATE))))
 ELSE 0 END) ward_bed_days
FROM months m JOIN e ON cast(e.admit_ts AS DATE)<cast(m.next_date AS DATE)
 AND coalesce(cast(e.discharge_ts AS DATE),cast(e.admit_ts AS DATE)+INTERVAL 1 DAY)>=cast(m.start_date AS DATE)
GROUP BY m.month_key),
adm AS (SELECT substr(admit_ts,1,7) month_key,count(*) admissions,
 SUM((bed_id='OVERFLOW')::INT) overflow_admissions FROM e GROUP BY 1)
SELECT a.*,coalesce(b.ward_bed_days,0) ward_bed_days,
 round(100.0*b.ward_bed_days/(228*date_diff('day',cast(m.start_date AS DATE),cast(m.next_date AS DATE))),2) occupancy_pct
FROM adm a LEFT JOIN bed b USING(month_key) JOIN months m USING(month_key) ORDER BY month_key
""",
 '02_ed_crowding': r"""
WITH e AS (SELECT * EXCLUDE rn FROM
 (SELECT *,row_number() OVER(PARTITION BY encounter_id ORDER BY admit_ts) rn
 FROM encounters WHERE encounter_type='ED') WHERE rn=1)
SELECT substr(admit_ts,1,7) month_key,count(*) ed_visits,
 median(try_cast(ed_wait_minutes AS DOUBLE)) median_wait_min,
 sum((discharge_disposition='LEFT_WITHOUT_BEING_SEEN')::INT) lwbs,
 round(100.0*sum((discharge_disposition='LEFT_WITHOUT_BEING_SEEN')::INT)/count(*),2) lwbs_pct
FROM e GROUP BY 1 ORDER BY 1
""",
 '03_heart_failure': r"""
WITH e AS (SELECT * EXCLUDE rn FROM
 (SELECT *,row_number() OVER(PARTITION BY encounter_id ORDER BY admit_ts) rn
 FROM encounters WHERE encounter_type='IP' AND discharge_ts IS NOT NULL) WHERE rn=1),
d AS (SELECT * EXCLUDE rn FROM
 (SELECT *,row_number() OVER(PARTITION BY encounter_id ORDER BY try_cast(seq AS INT)) rn
 FROM diagnoses WHERE dx_type='PRIMARY') WHERE rn=1)
SELECT CASE WHEN d.icd10_code='I50.9' AND d.dx_valid='1' THEN 'I50.9 heart failure'
 ELSE 'other inpatient' END cohort,count(*) discharges,
 sum((e.readmission_flag='Y')::INT) readmissions,
 round(100.0*sum((e.readmission_flag='Y')::INT)/count(*),2) readmission_pct
FROM e LEFT JOIN d USING(encounter_id) GROUP BY 1 ORDER BY 1
""",
 '04_coding_denials': r"""
WITH e AS (SELECT DISTINCT encounter_id FROM encounters),
d AS (SELECT * EXCLUDE rn FROM
 (SELECT *,row_number() OVER(PARTITION BY encounter_id ORDER BY try_cast(seq AS INT)) rn
 FROM diagnoses WHERE dx_type='PRIMARY') WHERE rn=1),
c AS (SELECT * FROM claims WHERE resubmission_of IS NULL AND coalesce(denial_code,'')<>'DUP-004')
SELECT CASE WHEN d.encounter_id IS NULL OR d.dx_valid='0' THEN 'missing_or_invalid'
 ELSE 'valid_primary' END coding_status,count(*) first_claims,
 sum((c.status='DENIED')::INT) denied,
 round(100.0*sum((c.status='DENIED')::INT)/count(*),2) denial_pct,
 sum((c.denial_code='DX-003')::INT) dx003_denials
FROM c JOIN e USING(encounter_id) LEFT JOIN d USING(encounter_id)
GROUP BY 1 ORDER BY 1
""",
 '05_payer_authorisation': r"""
WITH e AS (SELECT * EXCLUDE rn FROM
 (SELECT *,row_number() OVER(PARTITION BY encounter_id ORDER BY admit_ts) rn
 FROM encounters) WHERE rn=1)
SELECT c.payer,e.department,substr(c.submitted_ts,1,4) claim_year,
 count(*) first_claims,sum((c.status='DENIED')::INT) denied,
 sum((c.denial_code='AUTH-002')::INT) auth002_denials,
 round(100.0*sum((c.status='DENIED')::INT)/count(*),2) denial_pct
FROM claims c JOIN e USING(encounter_id)
WHERE c.resubmission_of IS NULL AND coalesce(c.denial_code,'')<>'DUP-004'
AND e.encounter_type IN ('IP','DAY') GROUP BY 1,2,3 ORDER BY 1,2,3
""",
 '06_drug_stockouts': r"""
WITH a AS (SELECT dispense_id,coalesce(substituted_for,drug_code) requested_drug,
 substr(dispensed_ts,1,7) month_key,cast(dispensed_ts AS DATE) event_day,status
 FROM dispenses WHERE status IN ('DELAYED_STOCKOUT','SUBSTITUTED')),
r AS (SELECT a.*,
 (SELECT count(*) FROM inventory i WHERE i.drug_code=a.requested_drug
  AND i.txn_type='RECEIPT' AND try_cast(i.qty AS INT)>0 AND cast(i.txn_ts AS DATE)
  BETWEEN a.event_day-INTERVAL 7 DAY AND a.event_day) recent_receipts FROM a)
SELECT requested_drug,month_key,count(*) affected_dispenses,
 sum((status='DELAYED_STOCKOUT')::INT) delayed,
 sum((status='SUBSTITUTED')::INT) substituted,
 sum((recent_receipts=0)::INT) no_recent_receipt
FROM r GROUP BY 1,2 ORDER BY 1,2
""",
 '07_icu_deterioration': r"""
WITH v AS (SELECT * EXCLUDE rn FROM
 (SELECT *,row_number() OVER(PARTITION BY bed_id,mrn,vital_ts ORDER BY vital_ts) rn
 FROM vitals) WHERE rn=1),
b AS (SELECT e.event_id,
 ceil(date_diff('second',cast(v.vital_ts AS TIMESTAMP),cast(e.event_ts AS TIMESTAMP))/3600.0)::INT hour_before,
 try_cast(v.hr AS INT) hr,try_cast(v.spo2 AS INT) spo2,
 try_cast(v.rr AS INT) rr,try_cast(v.sbp AS INT) sbp
 FROM events e JOIN v ON e.bed_id=v.bed_id AND e.mrn=v.mrn
 WHERE cast(v.vital_ts AS TIMESTAMP)>=cast(e.event_ts AS TIMESTAMP)-INTERVAL 4 HOUR
 AND cast(v.vital_ts AS TIMESTAMP)<cast(e.event_ts AS TIMESTAMP))
SELECT hour_before,count(DISTINCT event_id) matched_events,count(*) readings,
 round(avg(hr) FILTER(WHERE hr BETWEEN 30 AND 250),2) mean_hr,
 round(avg(spo2) FILTER(WHERE spo2 BETWEEN 50 AND 100),2) mean_spo2,
 round(avg(rr) FILTER(WHERE rr BETWEEN 5 AND 80),2) mean_rr,
 round(avg(sbp) FILTER(WHERE sbp BETWEEN 50 AND 250),2) mean_sbp
FROM b GROUP BY 1 ORDER BY 1 DESC
""",
 '08_billing_feedback': r"""
WITH e AS (SELECT DISTINCT encounter_id FROM encounters),
c AS (SELECT * EXCLUDE rn FROM
 (SELECT *,row_number() OVER(PARTITION BY encounter_id ORDER BY submitted_ts,claim_id) rn
 FROM claims WHERE resubmission_of IS NULL AND coalesce(denial_code,'')<>'DUP-004') WHERE rn=1),
l AS (SELECT CASE WHEN c.status='DENIED' THEN 'denied' ELSE 'not_denied' END claim_outcome,
 CASE WHEN regexp_matches(lower(f.comment),'bill|insur|claim|payment|فاتورة|تأمين') THEN 1 ELSE 0 END complaint,
 try_cast(f.rating AS DOUBLE) rating
 FROM feedback f JOIN e USING(encounter_id) JOIN c USING(encounter_id))
SELECT claim_outcome,count(*) linked_feedback,sum(complaint) billing_complaints,
 round(100.0*sum(complaint)/count(*),2) billing_complaint_pct,
 round(avg(rating),2) mean_rating FROM l GROUP BY 1 ORDER BY 1
""",
}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--stage',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--only',nargs='*',choices=sorted(SQL),help='Run selected reports while a large stage is still being prepared')
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    c=duckdb.connect()
    c.execute('SET threads=4')
    for name,cols in SCHEMAS.items():
        colmap='{'+','.join(f"'{v}':'VARCHAR'" for v in cols.split())+'}'
        file=a.stage/name/'part-00000'
        if not file.exists():
            file=a.stage/f'{name}.tsv'
        path=str(file.resolve()).replace("'","''")
        c.execute(f"CREATE VIEW {name} AS SELECT * FROM read_csv('{path}', delim='\\t', header=false, columns={colmap}, nullstr='\\N', quote='')")
    for name,sql in SQL.items():
        if a.only is not None and name not in a.only:
            continue
        out=(a.out/f'{name}.csv').resolve()
        c.execute(f"COPY ({sql}) TO '{str(out).replace(chr(39),chr(39)*2)}' (HEADER, DELIMITER ',')")
        print(name,c.execute(f"SELECT count(*) FROM read_csv_auto('{out}')").fetchone()[0],flush=True)


if __name__=='__main__':main()
