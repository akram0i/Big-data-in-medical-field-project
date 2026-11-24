-- =====================================================================
-- AHD Data Lake | Member 4 | Hive ETL (clinical): raw -> curated
-- Reads raw external tables patients, encounters, diagnoses, claims
-- (database default). Raw zone is never modified.
-- Run:
--   beeline -u jdbc:hive2://localhost:10000/default -f ahd_clinical_etl.hql 2>&1 | tee etl_run.log
-- Order matters: mrn_map -> curated_patients -> curated_encounters -> curated_diagnoses
-- =====================================================================

USE default;

SET hive.exec.dynamic.partition=true;
SET hive.exec.dynamic.partition.mode=nonstrict;
SET hive.exec.mode.local.auto=false;
-- If a join runs out of memory on the full dataset, uncomment:
SET hive.auto.convert.join=false;

-- ---------------------------------------------------------------------
-- 0. Clean slate (curated zone only; /datalake/raw is untouched)
-- ---------------------------------------------------------------------
DROP VIEW  IF EXISTS enc_primary_dx;
DROP VIEW  IF EXISTS enc_bad_stay;
DROP TABLE IF EXISTS orphan_claims;
DROP TABLE IF EXISTS curated_diagnoses;
DROP TABLE IF EXISTS curated_encounters;
DROP TABLE IF EXISTS curated_patients;
DROP TABLE IF EXISTS mrn_map;

DROP TEMPORARY MACRO IF EXISTS std_mrn;
DROP TEMPORARY MACRO IF EXISTS to_dt;
DROP TEMPORARY MACRO IF EXISTS to_ts;
DROP TEMPORARY MACRO IF EXISTS std_dept;

-- ---------------------------------------------------------------------
-- 1. Cleaning macros (session-only)
-- ---------------------------------------------------------------------
-- MRN: legacy MRNs lack the AHD prefix (1000123 -> AHD1000123)
CREATE TEMPORARY MACRO std_mrn(m STRING)
  CASE WHEN UPPER(TRIM(m)) LIKE 'AHD%' THEN UPPER(TRIM(m)) ELSE CONCAT('AHD', TRIM(m)) END;

-- Dates: yyyy-MM-dd  or  dd/MM/yyyy  (verified day-first on the sample)
CREATE TEMPORARY MACRO to_dt(s STRING)
  CASE WHEN TRIM(s) RLIKE '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN CAST(SUBSTR(TRIM(s),1,10) AS DATE)
       WHEN TRIM(s) RLIKE '^[0-9]{2}/[0-9]{2}/[0-9]{4}' THEN CAST(CONCAT(SUBSTR(TRIM(s),7,4),'-',SUBSTR(TRIM(s),4,2),'-',SUBSTR(TRIM(s),1,2)) AS DATE)
  END;

-- Timestamps: yyyy-MM-dd HH:mm:ss | yyyy-MM-ddTHH:mm:ss+04:00 (offset ignored, local time kept) | dd/MM/yyyy HH:mm
CREATE TEMPORARY MACRO to_ts(s STRING)
  CASE WHEN TRIM(s) RLIKE '^[0-9]{4}-[0-9]{2}-[0-9]{2}[ T][0-9]{2}:[0-9]{2}:[0-9]{2}'
            THEN CAST(CONCAT(SUBSTR(TRIM(s),1,10),' ',SUBSTR(TRIM(s),12,8)) AS TIMESTAMP)
       WHEN TRIM(s) RLIKE '^[0-9]{2}/[0-9]{2}/[0-9]{4} [0-9]{2}:[0-9]{2}$'
            THEN CAST(CONCAT(SUBSTR(TRIM(s),7,4),'-',SUBSTR(TRIM(s),4,2),'-',SUBSTR(TRIM(s),1,2),' ',SUBSTR(TRIM(s),12,5),':00') AS TIMESTAMP)
  END;

-- Department variants -> 13 official codes (anything else = UNKNOWN, must be 0 rows)
CREATE TEMPORARY MACRO std_dept(d STRING)
  CASE LOWER(TRIM(d))
    WHEN 'ed' THEN 'ED' WHEN 'er' THEN 'ED' WHEN 'emergency' THEN 'ED' WHEN 'emergency department' THEN 'ED'
    WHEN 'gim' THEN 'GIM' WHEN 'im' THEN 'GIM' WHEN 'internal medicine' THEN 'GIM' WHEN 'general internal medicine' THEN 'GIM'
    WHEN 'ped' THEN 'PED' WHEN 'paeds' THEN 'PED' WHEN 'pediatrics' THEN 'PED' WHEN 'paediatrics' THEN 'PED'
    WHEN 'obgy' THEN 'OBGY' WHEN 'obgyn' THEN 'OBGY' WHEN 'ob/gyn' THEN 'OBGY' WHEN 'obstetrics & gynaecology' THEN 'OBGY'
    WHEN 'orth' THEN 'ORTH' WHEN 'ortho' THEN 'ORTH' WHEN 'orthopedics' THEN 'ORTH' WHEN 'orthopaedics' THEN 'ORTH'
    WHEN 'card' THEN 'CARD' WHEN 'cardio' THEN 'CARD' WHEN 'cardiology' THEN 'CARD'
    WHEN 'endo' THEN 'ENDO' WHEN 'endocrine' THEN 'ENDO' WHEN 'endocrinology' THEN 'ENDO'
    WHEN 'gsurg' THEN 'GSURG' WHEN 'surg' THEN 'GSURG' WHEN 'gen surgery' THEN 'GSURG' WHEN 'general surgery' THEN 'GSURG'
    WHEN 'onc' THEN 'ONC' WHEN 'onco' THEN 'ONC' WHEN 'oncology' THEN 'ONC'
    WHEN 'neur' THEN 'NEUR' WHEN 'neuro' THEN 'NEUR' WHEN 'neurology' THEN 'NEUR'
    WHEN 'bari' THEN 'BARI' WHEN 'bariatric' THEN 'BARI' WHEN 'bariatrics' THEN 'BARI' WHEN 'bariatric surgery' THEN 'BARI'
    WHEN 'derm' THEN 'DERM' WHEN 'derma' THEN 'DERM' WHEN 'dermatology' THEN 'DERM'
    WHEN 'icu' THEN 'ICU' WHEN 'intensive care' THEN 'ICU' WHEN 'critical care' THEN 'ICU'
    ELSE 'UNKNOWN' END;

-- ---------------------------------------------------------------------
-- 2. mrn_map: patient de-duplication
-- Match key = first + last name (lower-case, spaces/hyphens removed, order-insensitive
-- so swapped first/last names and 'Al ' vs 'Al-' still match) + date of birth.
-- Phone is NOT used: on the sample, duplicate registrations (AHD2xxxxxx
-- vs AHD1xxxxxx) have different phone numbers, but the same policy number.
-- Patients with no usable DOB/name are never merged (key = own MRN).
-- Master MRN = original AHD1... id if present, else earliest registration.
-- ---------------------------------------------------------------------
CREATE TABLE mrn_map (std_mrn STRING, master_mrn STRING) STORED AS ORC;

WITH p AS (
  SELECT std_mrn(mrn) AS std_mrn,
         REGEXP_REPLACE(LOWER(TRIM(first_name)),'[ -]','') AS fname,
         REGEXP_REPLACE(LOWER(TRIM(last_name)),'[ -]','') AS lname,
         to_dt(date_of_birth) AS dob, to_dt(registration_date) AS reg
  FROM patients),
k AS (
  SELECT std_mrn, reg,
         CASE WHEN dob IS NULL OR COALESCE(fname,'') = '' OR COALESCE(lname,'') = '' THEN std_mrn
              ELSE CONCAT_WS('|', LEAST(fname, lname), GREATEST(fname, lname), CAST(dob AS STRING)) END AS match_key
  FROM p)
INSERT OVERWRITE TABLE mrn_map
SELECT DISTINCT std_mrn,
       FIRST_VALUE(std_mrn) OVER (PARTITION BY match_key
            ORDER BY CASE WHEN std_mrn LIKE 'AHD2%' THEN 1 ELSE 0 END, reg, std_mrn) AS master_mrn
FROM k;

-- ---------------------------------------------------------------------
-- 3. curated_patients: one row per master MRN
-- ---------------------------------------------------------------------
CREATE TABLE curated_patients (mrn STRING, first_name STRING, last_name STRING, gender STRING,
  date_of_birth DATE, nationality STRING, emirate STRING, mobile STRING, insurance_payer STRING,
  policy_number STRING, registration_date DATE)
CLUSTERED BY (mrn) INTO 8 BUCKETS STORED AS ORC LOCATION '/datalake/curated/patients';

INSERT OVERWRITE TABLE curated_patients
SELECT mrn, first_name, last_name, gender, date_of_birth, nationality, emirate, mobile,
       insurance_payer, policy_number, registration_date
FROM (
  SELECT m.master_mrn AS mrn, INITCAP(TRIM(p.first_name)) AS first_name, INITCAP(TRIM(p.last_name)) AS last_name,
         UPPER(TRIM(p.gender)) AS gender, to_dt(p.date_of_birth) AS date_of_birth,
         CASE WHEN UPPER(TRIM(p.nationality)) IN ('EMIRATI','UAE','UNITED ARAB EMIRATES','AE') THEN 'Emirati'
              ELSE TRIM(p.nationality) END AS nationality, TRIM(p.emirate) AS emirate, TRIM(p.mobile) AS mobile,
         TRIM(p.insurance_payer) AS insurance_payer, TRIM(p.policy_number) AS policy_number,
         to_dt(p.registration_date) AS registration_date,
         ROW_NUMBER() OVER (PARTITION BY m.master_mrn
              ORDER BY CASE WHEN std_mrn(p.mrn) = m.master_mrn THEN 0 ELSE 1 END, std_mrn(p.mrn)) AS rn
  FROM patients p JOIN mrn_map m ON std_mrn(p.mrn) = m.std_mrn) t
WHERE rn = 1;

-- ---------------------------------------------------------------------
-- 4. curated_encounters: partitioned by month, bucketed by MRN
-- ---------------------------------------------------------------------
CREATE TABLE curated_encounters (encounter_id STRING, mrn STRING, encounter_type STRING, department STRING,
  attending_id STRING, admit_ts TIMESTAMP, discharge_ts TIMESTAMP, bed_id STRING, triage_level INT,
  ed_wait_minutes INT, discharge_disposition STRING, readmission_flag STRING, source_system STRING)
PARTITIONED BY (year INT, month INT)
CLUSTERED BY (mrn) INTO 8 BUCKETS STORED AS ORC LOCATION '/datalake/curated/encounters';

WITH clean AS (
  SELECT DISTINCT TRIM(e.encounter_id) AS encounter_id,
         COALESCE(m.master_mrn, std_mrn(e.mrn)) AS mrn,
         UPPER(TRIM(e.encounter_type)) AS encounter_type, std_dept(e.department) AS department,
         TRIM(e.attending_id) AS attending_id, to_ts(e.admit_ts) AS admit_ts, to_ts(e.discharge_ts) AS discharge_ts,
         UPPER(TRIM(e.bed_id)) AS bed_id, CAST(TRIM(e.triage_level) AS INT) AS triage_level,
         CAST(TRIM(e.ed_wait_minutes) AS INT) AS ed_wait_minutes,
         TRIM(e.discharge_disposition) AS discharge_disposition,
         UPPER(TRIM(e.readmission_flag)) AS readmission_flag, UPPER(TRIM(e.source_system)) AS source_system
  FROM encounters e LEFT JOIN mrn_map m ON std_mrn(e.mrn) = m.std_mrn),
ranked AS (
  SELECT c.*, ROW_NUMBER() OVER (PARTITION BY encounter_id
              ORDER BY CASE WHEN source_system='CERNER' THEN 0 ELSE 1 END, admit_ts) AS rn
  FROM clean c WHERE admit_ts IS NOT NULL)
INSERT OVERWRITE TABLE curated_encounters PARTITION (year, month)
SELECT encounter_id, mrn, encounter_type, department, attending_id, admit_ts, discharge_ts, bed_id,
       triage_level, ed_wait_minutes, discharge_disposition, readmission_flag, source_system,
       YEAR(admit_ts), MONTH(admit_ts)
FROM ranked WHERE rn = 1;

-- Stays that end before they start: kept (raw data issue), exposed via a view
CREATE VIEW enc_bad_stay AS
SELECT * FROM curated_encounters WHERE discharge_ts < admit_ts;

-- ---------------------------------------------------------------------
-- 5. curated_diagnoses: format problems fixed (dots, case); codes that are invalid
-- AS RECORDED (000, UNKNOWN, I5O.9, E11..9, R99X) are flagged dx_valid='N' and the
-- clean code is NULL. The raw code is kept in icd10_raw for audit.
-- ---------------------------------------------------------------------
CREATE TABLE curated_diagnoses (encounter_id STRING, mrn STRING, seq INT, icd10_code STRING,
  icd10_raw STRING, description STRING, dx_type STRING, dx_valid STRING, recorded_at TIMESTAMP)
PARTITIONED BY (year INT, month INT)
CLUSTERED BY (mrn) INTO 8 BUCKETS STORED AS ORC LOCATION '/datalake/curated/diagnoses';

WITH dx AS (
  SELECT DISTINCT TRIM(encounter_id) AS encounter_id, CAST(TRIM(seq) AS INT) AS seq,
         TRIM(icd10_code) AS icd10_raw, UPPER(TRIM(icd10_code)) AS u,
         TRIM(description) AS description, UPPER(TRIM(dx_type)) AS dx_type, to_ts(recorded_at) AS recorded_at
  FROM diagnoses),
v AS (
  SELECT dx.*, REGEXP_REPLACE(u,'[.]','') AS c0,
         (u RLIKE '^[A-Z][0-9]{2}([.]?[0-9A-Z]{1,4})?$' AND REGEXP_REPLACE(u,'[.]','') <> 'R99X') AS ok
  FROM dx)
INSERT OVERWRITE TABLE curated_diagnoses PARTITION (year, month)
SELECT v.encounter_id, e.mrn, v.seq,
       CASE WHEN v.ok THEN IF(LENGTH(v.c0) > 3, CONCAT(SUBSTR(v.c0,1,3),'.',SUBSTR(v.c0,4)), v.c0) END AS icd10_code,
       v.icd10_raw, v.description, v.dx_type,
       IF(v.ok, 'Y', 'N') AS dx_valid,
       v.recorded_at, YEAR(v.recorded_at), MONTH(v.recorded_at)
FROM v JOIN curated_encounters e ON v.encounter_id = e.encounter_id
WHERE v.recorded_at IS NOT NULL;

-- ---------------------------------------------------------------------
-- 6. Orphan claims (claims whose encounter is not in the curated zone)
-- ---------------------------------------------------------------------
CREATE TABLE orphan_claims STORED AS ORC AS
SELECT c.* FROM claims c LEFT OUTER JOIN curated_encounters e
  ON TRIM(c.encounter_id) = e.encounter_id
WHERE e.encounter_id IS NULL;

-- Does each encounter have a valid PRIMARY diagnosis? (used for problem 4, claim denials)
CREATE VIEW enc_primary_dx AS
SELECT e.encounter_id,
       MAX(CASE WHEN d.dx_type = 'PRIMARY' AND d.dx_valid = 'Y' THEN 1 ELSE 0 END) AS has_valid_primary
FROM curated_encounters e LEFT OUTER JOIN curated_diagnoses d ON e.encounter_id = d.encounter_id
GROUP BY e.encounter_id;

-- =====================================================================
-- 7. VALIDATION + EVIDENCE (screenshot these)
-- =====================================================================
-- Before / after row counts
SELECT COUNT(*) AS raw_patients FROM patients;
SELECT COUNT(*) AS source_mrns, COUNT(DISTINCT master_mrn) AS patients_after_dedup FROM mrn_map;
SELECT COUNT(*) AS curated_patients_rows, COUNT(DISTINCT mrn) AS distinct_mrn FROM curated_patients;
SELECT * FROM mrn_map WHERE master_mrn <> std_mrn LIMIT 10;
SELECT COUNT(*) AS merged_master_mrns FROM (SELECT master_mrn FROM mrn_map GROUP BY master_mrn HAVING COUNT(*) > 1) t;

SELECT COUNT(*) AS raw_encounters FROM encounters;
SELECT COUNT(*) AS encounters_no_exact_dups FROM (SELECT DISTINCT * FROM encounters) t;
SELECT COUNT(*) AS curated_encounters_rows, COUNT(DISTINCT encounter_id) AS distinct_ids FROM curated_encounters;
SELECT COUNT(*) AS unparseable_admit_ts FROM encounters WHERE to_ts(admit_ts) IS NULL;
SELECT COUNT(*) AS bad_stays FROM enc_bad_stay;

SELECT COUNT(*) AS raw_diagnoses FROM diagnoses;
SELECT COUNT(*) AS curated_diagnoses_rows FROM curated_diagnoses;
SELECT COUNT(*) AS unparseable_recorded_at FROM diagnoses WHERE to_ts(recorded_at) IS NULL;
SELECT dx_valid, COUNT(*) AS n FROM curated_diagnoses GROUP BY dx_valid;
SELECT COUNT(DISTINCT icd10_code) AS raw_distinct_icd FROM diagnoses;
SELECT COUNT(DISTINCT icd10_code) AS curated_distinct_icd FROM curated_diagnoses;

SELECT COUNT(DISTINCT department) AS raw_distinct_departments FROM encounters;
SELECT department, COUNT(*) AS n FROM curated_encounters GROUP BY department ORDER BY n DESC;

SELECT COUNT(*) AS raw_claims FROM claims;

-- Orphan checks (LEFT OUTER JOIN ... IS NULL; Hive has no MINUS)
SELECT COUNT(*) AS orphan_diagnoses FROM diagnoses d LEFT OUTER JOIN curated_encounters e
  ON TRIM(d.encounter_id) = e.encounter_id WHERE e.encounter_id IS NULL;
SELECT COUNT(*) AS orphan_claims FROM orphan_claims;
SELECT status, COUNT(*) AS n FROM orphan_claims GROUP BY status;
SELECT COUNT(*) AS encounters_without_patient FROM curated_encounters e LEFT OUTER JOIN curated_patients p
  ON e.mrn = p.mrn WHERE p.mrn IS NULL;
SELECT COUNT(*) AS encounters_without_diagnosis FROM curated_encounters e LEFT OUTER JOIN
  (SELECT DISTINCT encounter_id FROM curated_diagnoses) d ON e.encounter_id = d.encounter_id
WHERE d.encounter_id IS NULL;

SHOW PARTITIONS curated_encounters;
SHOW PARTITIONS curated_diagnoses;

-- Problem 4 check (answer key: ~53% denied without a valid primary dx vs ~6% with one; first submissions only)
SELECT p.has_valid_primary, COUNT(*) AS claims,
       SUM(IF(c.status = 'DENIED', 1, 0)) AS denied,
       ROUND(100 * SUM(IF(c.status = 'DENIED', 1, 0)) / COUNT(*), 1) AS denied_pct
FROM claims c JOIN enc_primary_dx p ON TRIM(c.encounter_id) = p.encounter_id
WHERE COALESCE(TRIM(c.resubmission_of), '') = ''
GROUP BY p.has_valid_primary;

SELECT nationality, COUNT(*) AS n FROM curated_patients GROUP BY nationality ORDER BY n DESC;
