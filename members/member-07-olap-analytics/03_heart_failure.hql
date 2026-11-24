-- P3: One inpatient encounter, its primary diagnosis, 30-day readmission flag.
USE ahd_member7;
WITH ip AS (
  SELECT * FROM (
    SELECT e.*, row_number() OVER (PARTITION BY encounter_id ORDER BY admit_ts) rn
    FROM encounters e WHERE encounter_type = 'IP') x WHERE rn = 1
), primary_dx AS (
  SELECT * FROM (
    SELECT d.*, row_number() OVER (PARTITION BY encounter_id ORDER BY seq) rn
    FROM diagnoses d WHERE dx_type = 'PRIMARY') x WHERE rn = 1
), rates AS (
  SELECT CASE WHEN d.icd10_code = 'I50.9' AND d.dx_valid = 1
              THEN 'I50.9 heart failure' ELSE 'other inpatient' END cohort,
         e.department, count(*) discharges,
         sum(CASE WHEN e.readmission_flag = 'Y' THEN 1 ELSE 0 END) readmissions
  FROM ip e LEFT JOIN primary_dx d ON e.encounter_id = d.encounter_id
  WHERE e.discharge_ts IS NOT NULL
  GROUP BY CASE WHEN d.icd10_code = 'I50.9' AND d.dx_valid = 1
                THEN 'I50.9 heart failure' ELSE 'other inpatient' END, e.department
)
SELECT cohort, department, discharges, readmissions,
       round(100.0*readmissions/discharges,2) readmission_pct,
       rank() OVER (PARTITION BY cohort ORDER BY 1.0*readmissions/discharges DESC) department_rank
FROM rates ORDER BY cohort, department_rank;
