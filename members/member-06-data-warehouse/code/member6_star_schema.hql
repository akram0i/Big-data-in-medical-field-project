-- =====================================================================
-- ISIT312 AHD Data Lake: Member 6, star schema build (Hive)
-- Builds database dw: 9 dimensions, 1 bridge table, 4 facts, 2 summary tables.
-- Source = curated tables from Members 4 and 5 (Phase 3).
--
-- CONTRACT WITH MEMBERS 4 AND 5 (agree on this, or edit the names below):
-- curated tables keep the README column names, already cleaned:
--   curated.patients   (mrn, first_name, last_name, gender, date_of_birth, nationality, emirate, ...)
--   curated.mrn_map    (mrn, canonical_mrn)   -- every duplicate AHD2xxxxxx / legacy MRN -> its real MRN
--   curated.encounters (encounter_id, mrn, encounter_type, department, attending_id, admit_ts,
--                       discharge_ts, bed_id, triage_level, ed_wait_minutes, discharge_disposition,
--                       readmission_flag, source_system)
--   curated.diagnoses  (encounter_id, seq, icd10_code, description, dx_type, recorded_at)
--   curated.claims     (claim_id, encounter_id, mrn, payer, submitted_date, total_amount, status,
--                       denial_code, denial_reason, paid_amount, paid_date, resubmission_of)
--   curated.dispense   (dispense_id, mrn, encounter_id, drug_code, drug_name, qty, dispensed_at,
--                       status, delay_minutes, substituted_for)              -- v1 + v2 merged
--   curated.inventory  (txn_id, item_code, item_name, txn_type, qty, unit_cost, store, txn_ts)
-- Cleaned means: timestamps as yyyy-MM-dd HH:mm:ss, department = code (CARD, ORTH, ...),
-- ICD codes upper case with the dot, amounts numeric, exact duplicates removed.
-- =====================================================================

CREATE DATABASE IF NOT EXISTS dw;
USE dw;

SET hive.exec.dynamic.partition=true;
SET hive.exec.dynamic.partition.mode=nonstrict;
-- Full data: map joins load the 754k-row primary-dx table into each map task (default heap ran out)
SET mapreduce.map.memory.mb=2048;
SET mapreduce.map.java.opts=-Xmx1536m;
SET mapreduce.reduce.memory.mb=2048;
SET mapreduce.reduce.java.opts=-Xmx1536m;
-- Each open file reserves one block: 25 month partitions x parallel reducers x 128 MB exceeded the VM disk
SET dfs.blocksize=33554432;
-- Hive 1.x only (removed in Hive 2, where bucketing is always enforced):
-- SET hive.enforce.bucketing=true;

-- ---------------------------------------------------------------------
-- 1. DIMENSIONS (Rule 1: one table per dimension, surrogate key *_key)
--    Star schema: hierarchy levels flattened into columns.
--    Negative keys = placeholder members, so no fact row is ever dropped.
-- ---------------------------------------------------------------------

-- Time: Day -> Month -> Quarter -> Year, and the alternative path Day -> Week.
-- One table, six roles (admit, discharge, submitted, paid, dispensed, transaction).
DROP TABLE IF EXISTS dim_date;
CREATE TABLE dim_date (
  date_key     INT,          -- yyyymmdd
  full_date    STRING,
  day_name     STRING,
  week_start   STRING,       -- Monday of the week (1900-01-01 was a Monday)
  month        INT,
  month_name   STRING,
  quarter      INT,
  year         INT
) STORED AS TEXTFILE;

-- 912 days = 2024-01-01 .. 2026-06-30 (space(911) splits into 912 elements). The data covers
-- 2024-2025, but stays admitted in late December are discharged and dispensed in January 2026.
INSERT OVERWRITE TABLE dim_date
SELECT * FROM (
  SELECT CAST(regexp_replace(d, '-', '') AS INT), CAST(d AS STRING), date_format(d, 'EEEE'),
         CAST(date_sub(d, pmod(datediff(d, '1900-01-01'), 7)) AS STRING),
         month(d), date_format(d, 'MMMM'), CAST(ceil(month(d) / 3) AS INT), year(d)
  FROM (
    SELECT date_add('2024-01-01', t.pos) AS d
    FROM (SELECT 1 AS one) s
    LATERAL VIEW posexplode(split(space(911), ' ')) t AS pos, x
  ) days
  UNION ALL
  SELECT -1, 'Unknown', 'Unknown', 'Unknown', -1, 'Unknown', -1, -1 FROM (SELECT 1 AS one) s
) u;

-- Patient: two parallel hierarchies, Patient -> Nationality and Patient -> Emirate.
-- Only canonical MRNs become patients (duplicates are folded in through mrn_map).
DROP TABLE IF EXISTS dim_patient;
CREATE TABLE dim_patient (
  patient_key  INT,
  mrn          STRING,
  gender       STRING,
  birth_year   INT,
  nationality  STRING,
  emirate      STRING
)
CLUSTERED BY (patient_key) INTO 8 BUCKETS
STORED AS TEXTFILE;

INSERT OVERWRITE TABLE dim_patient
SELECT * FROM (
  SELECT ROW_NUMBER() OVER (ORDER BY p.mrn) AS patient_key, p.mrn, p.gender, year(p.date_of_birth),
         -- Emiratis are written 4 ways in the source
         CASE WHEN p.nationality IN ('Emirati', 'UAE', 'AE', 'United Arab Emirates') THEN 'Emirati'
              ELSE p.nationality END,
         p.emirate
  FROM curated.patients p
  LEFT JOIN (SELECT mrn FROM curated.mrn_map WHERE mrn <> canonical_mrn) dup ON p.mrn = dup.mrn
  WHERE dup.mrn IS NULL
  UNION ALL
  SELECT -1, 'UNKNOWN', CAST(NULL AS STRING), CAST(NULL AS INT), 'Unknown', 'Unknown' FROM (SELECT 1 AS one) s
) u;

-- Department (single level): the 13 codes from the README
DROP TABLE IF EXISTS dim_department;
CREATE TABLE dim_department (department_key INT, department_code STRING, department_name STRING)
STORED AS TEXTFILE;

INSERT INTO TABLE dim_department VALUES
  (1, 'CARD', 'Cardiology'), (2, 'ONC', 'Oncology'), (3, 'ORTH', 'Orthopaedics'),
  (4, 'OBGY', 'Obstetrics & Gynaecology'), (5, 'PED', 'Paediatrics'),
  (6, 'GIM', 'General Internal Medicine'), (7, 'GSURG', 'General Surgery'),
  (8, 'NEUR', 'Neurology'), (9, 'ENDO', 'Endocrinology'), (10, 'BARI', 'Bariatric Surgery'),
  (11, 'DERM', 'Dermatology'), (12, 'ED', 'Emergency Department'), (13, 'ICU', 'Intensive Care'),
  (-1, 'UNKNOWN', 'Unknown');

-- Bed -> Ward (balanced). bed_id W3-07 -> ward W3, ICU-05 -> ICU, OVERFLOW = admitted with no
-- ward bed free. ED/OP/DAY visits have no bed: placeholder -1 (the Encounter-Bed link is 0..1).
DROP TABLE IF EXISTS dim_bed;
CREATE TABLE dim_bed (bed_key INT, bed_id STRING, ward STRING, bed_type STRING) STORED AS TEXTFILE;

INSERT OVERWRITE TABLE dim_bed
SELECT * FROM (
  SELECT ROW_NUMBER() OVER (ORDER BY bed_id) AS bed_key, bed_id,
         CASE WHEN bed_id = 'OVERFLOW' THEN 'OVERFLOW' ELSE split(bed_id, '-')[0] END,
         CASE WHEN bed_id = 'OVERFLOW' THEN 'OVERFLOW'
              WHEN bed_id LIKE 'ICU-%' THEN 'ICU' ELSE 'WARD' END
  FROM (SELECT DISTINCT bed_id FROM curated.encounters WHERE bed_id IS NOT NULL AND bed_id <> '') b
  UNION ALL
  SELECT -1, 'NO BED', 'NO BED', 'NONE' FROM (SELECT 1 AS one) s
) u;

-- Diagnosis: ICD code -> ICD category (3 chars) -> ICD chapter (balanced).
-- Valid = letter, 2 digits, optional dot + digit + up to 3 more. This rejects the planted
-- bad codes (R99.X, I5O.9, E11..9, 000, UNKNOWN). Placeholders carry coding_status (problem 4):
--   -1 UNKNOWN = claim with no matching encounter (orphan)
--   -2 MISSING = encounter has no PRIMARY diagnosis
--   -3 INVALID = the code fails the check
DROP TABLE IF EXISTS dim_diagnosis;
CREATE TABLE dim_diagnosis (
  diagnosis_key  INT,
  icd10_code     STRING,
  description    STRING,
  icd_category   STRING,
  icd_chapter    STRING,
  coding_status  STRING      -- VALID / UNKNOWN / MISSING / INVALID
) STORED AS TEXTFILE;

INSERT OVERWRITE TABLE dim_diagnosis
SELECT * FROM (
  SELECT ROW_NUMBER() OVER (ORDER BY icd10_code) AS diagnosis_key, icd10_code, description,
         substr(icd10_code, 1, 3),
         CASE
           WHEN substr(icd10_code,1,3) BETWEEN 'A00' AND 'B99' THEN 'I Infectious'
           WHEN substr(icd10_code,1,3) BETWEEN 'C00' AND 'D49' THEN 'II Neoplasms'
           WHEN substr(icd10_code,1,3) BETWEEN 'D50' AND 'D89' THEN 'III Blood'
           WHEN substr(icd10_code,1,3) BETWEEN 'E00' AND 'E90' THEN 'IV Endocrine'
           WHEN substr(icd10_code,1,3) BETWEEN 'F00' AND 'F99' THEN 'V Mental'
           WHEN substr(icd10_code,1,3) BETWEEN 'G00' AND 'G99' THEN 'VI Nervous'
           WHEN substr(icd10_code,1,3) BETWEEN 'H00' AND 'H59' THEN 'VII Eye'
           WHEN substr(icd10_code,1,3) BETWEEN 'H60' AND 'H95' THEN 'VIII Ear'
           WHEN substr(icd10_code,1,3) BETWEEN 'I00' AND 'I99' THEN 'IX Circulatory'
           WHEN substr(icd10_code,1,3) BETWEEN 'J00' AND 'J99' THEN 'X Respiratory'
           WHEN substr(icd10_code,1,3) BETWEEN 'K00' AND 'K95' THEN 'XI Digestive'
           WHEN substr(icd10_code,1,3) BETWEEN 'L00' AND 'L99' THEN 'XII Skin'
           WHEN substr(icd10_code,1,3) BETWEEN 'M00' AND 'M99' THEN 'XIII Musculoskeletal'
           WHEN substr(icd10_code,1,3) BETWEEN 'N00' AND 'N99' THEN 'XIV Genitourinary'
           WHEN substr(icd10_code,1,3) BETWEEN 'O00' AND 'O99' THEN 'XV Pregnancy'
           WHEN substr(icd10_code,1,3) BETWEEN 'P00' AND 'P96' THEN 'XVI Perinatal'
           WHEN substr(icd10_code,1,3) BETWEEN 'Q00' AND 'Q99' THEN 'XVII Congenital'
           WHEN substr(icd10_code,1,3) BETWEEN 'R00' AND 'R99' THEN 'XVIII Symptoms'
           WHEN substr(icd10_code,1,3) BETWEEN 'S00' AND 'T98' THEN 'XIX Injury'
           WHEN substr(icd10_code,1,3) BETWEEN 'U00' AND 'U99' THEN 'XXII Special'
           WHEN substr(icd10_code,1,3) BETWEEN 'V00' AND 'Y99' THEN 'XX External causes'
           WHEN substr(icd10_code,1,3) BETWEEN 'Z00' AND 'Z99' THEN 'XXI Health status'
           ELSE 'Unknown'
         END,
         'VALID'
  FROM (SELECT icd10_code, max(description) AS description FROM curated.diagnoses
        WHERE icd10_code RLIKE '^[A-Z][0-9]{2}(\\.[0-9][0-9A-Z]{0,3})?$'
        GROUP BY icd10_code) c
  UNION ALL
  SELECT -1, 'UNKNOWN', 'No matching encounter',     'UNKNOWN', 'Unknown', 'UNKNOWN' FROM (SELECT 1 AS one) s
  UNION ALL
  SELECT -2, 'MISSING', 'No primary diagnosis coded', 'MISSING', 'Unknown', 'MISSING' FROM (SELECT 1 AS one) s
  UNION ALL
  SELECT -3, 'INVALID', 'Invalid ICD-10 code',        'INVALID', 'Unknown', 'INVALID' FROM (SELECT 1 AS one) s
) u;

-- Payer (single level)
DROP TABLE IF EXISTS dim_payer;
CREATE TABLE dim_payer (payer_key INT, payer_name STRING) STORED AS TEXTFILE;

INSERT OVERWRITE TABLE dim_payer
SELECT * FROM (
  SELECT ROW_NUMBER() OVER (ORDER BY payer) AS payer_key, payer
  FROM (SELECT DISTINCT payer FROM curated.claims WHERE payer IS NOT NULL) p
  UNION ALL
  SELECT -1, 'Unknown' FROM (SELECT 1 AS one) s
) u;

-- Denial reason (single level). -1 = claim not denied.
DROP TABLE IF EXISTS dim_denial_reason;
CREATE TABLE dim_denial_reason (denial_reason_key INT, denial_code STRING, denial_reason STRING)
STORED AS TEXTFILE;

INSERT OVERWRITE TABLE dim_denial_reason
SELECT * FROM (
  SELECT ROW_NUMBER() OVER (ORDER BY denial_code) AS denial_reason_key, denial_code, denial_reason
  FROM (SELECT denial_code, max(denial_reason) AS denial_reason FROM curated.claims
        WHERE denial_code IS NOT NULL AND denial_code <> '' GROUP BY denial_code) r
  UNION ALL
  SELECT -1, 'NONE', 'Not denied' FROM (SELECT 1 AS one) s
) u;

-- Drug (single level). Pharmacy drug_code = ERP ItemCode (README join key).
DROP TABLE IF EXISTS dim_drug;
CREATE TABLE dim_drug (drug_key INT, drug_code STRING, drug_name STRING) STORED AS TEXTFILE;

INSERT OVERWRITE TABLE dim_drug
SELECT * FROM (
  SELECT ROW_NUMBER() OVER (ORDER BY drug_code) AS drug_key, drug_code, drug_name
  FROM (
    SELECT drug_code, max(drug_name) AS drug_name FROM (
      SELECT drug_code, drug_name FROM curated.dispense
      UNION ALL
      SELECT item_code AS drug_code, item_name AS drug_name FROM curated.inventory
    ) a GROUP BY drug_code
  ) d
  UNION ALL
  SELECT -1, 'UNKNOWN', 'Unknown' FROM (SELECT 1 AS one) s
) u;

-- Store (single level): MAIN_PHARMACY, ICU_SATELLITE, ED_SATELLITE
DROP TABLE IF EXISTS dim_store;
CREATE TABLE dim_store (store_key INT, store_name STRING) STORED AS TEXTFILE;

INSERT OVERWRITE TABLE dim_store
SELECT * FROM (
  SELECT ROW_NUMBER() OVER (ORDER BY store) AS store_key, store
  FROM (SELECT DISTINCT store FROM curated.inventory WHERE store IS NOT NULL) st
  UNION ALL
  SELECT -1, 'Unknown' FROM (SELECT 1 AS one) s
) u;

-- ---------------------------------------------------------------------
-- 2. BRIDGE TABLE (Rule 3c): Encounter <-> Diagnosis is many-to-many
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS bridge_encounter_diagnosis;
CREATE TABLE bridge_encounter_diagnosis (
  encounter_id   STRING,
  diagnosis_key  INT,
  seq            INT,
  dx_type        STRING      -- PRIMARY / SECONDARY
) STORED AS TEXTFILE;

INSERT OVERWRITE TABLE bridge_encounter_diagnosis
SELECT d.encounter_id, COALESCE(dd.diagnosis_key, -3), d.seq, d.dx_type
FROM curated.diagnoses d
LEFT JOIN (SELECT diagnosis_key, icd10_code FROM dim_diagnosis WHERE diagnosis_key > 0) dd
       ON d.icd10_code = dd.icd10_code;

-- Primary diagnosis per encounter, used by both fact_encounter and fact_claim.
-- No PRIMARY row -> -2 MISSING is applied in the fact loads.
DROP TABLE IF EXISTS encounter_primary_dx;
CREATE TABLE encounter_primary_dx STORED AS TEXTFILE AS
SELECT encounter_id, diagnosis_key FROM (
  SELECT encounter_id, diagnosis_key,
         ROW_NUMBER() OVER (PARTITION BY encounter_id ORDER BY seq) AS rn
  FROM bridge_encounter_diagnosis WHERE dx_type = 'PRIMARY'
) p WHERE rn = 1;

-- ---------------------------------------------------------------------
-- 3. FACTS (Rule 2 + Rule 3b): measures + one FK per dimension.
--    Partitioned by (year, month) of the main date, bucketed by patient_key (= MRN).
--    Lookups use LEFT JOIN + COALESCE(..., -1) so no row is dropped.
-- ---------------------------------------------------------------------

-- Encounter: one row = one visit or admission (OP, ED, DAY or IP)
DROP TABLE IF EXISTS fact_encounter;
CREATE TABLE fact_encounter (
  encounter_id           STRING,   -- degenerate dimensions: encounter_id .. source_system
  encounter_type         STRING,
  discharge_disposition  STRING,
  source_system          STRING,
  patient_key            INT,
  admit_date_key         INT,      -- Time role: admit
  discharge_date_key     INT,      -- Time role: discharge
  department_key         INT,
  bed_key                INT,
  primary_diagnosis_key  INT,
  triage_level           INT,      -- non-additive (a category, report it, never sum it)
  los_days               INT,      -- additive, NULL if discharge missing or before admit
  ed_wait_minutes        INT,      -- additive, report AVG / median
  lwbs_flag              INT,      -- 1 = LEFT_WITHOUT_BEING_SEEN
  overflow_flag          INT,      -- 1 = admitted with no ward bed free (bed_id OVERFLOW)
  readmit_30d_flag       INT,      -- 1 = this IP stay is followed by another IP admission within 30 days
  is_readmission_flag    INT,      -- source readmission_flag: 1 = this stay IS the readmission
  encounter_count        INT       -- always 1, so SUM = number of encounters
)
PARTITIONED BY (year INT, month INT)
CLUSTERED BY (patient_key) INTO 8 BUCKETS
STORED AS TEXTFILE;

-- readmit_30d_flag sits on the INDEX stay, so "readmission rate by primary diagnosis"
-- (problem 3) is a plain AVG over IP rows. The source flag sits on the second stay instead,
-- which attaches the rate to the wrong diagnosis. LEAD runs over the canonical MRN, so
-- stays filed under a duplicate MRN still count.
INSERT OVERWRITE TABLE fact_encounter PARTITION (year, month)
SELECT e.encounter_id, e.encounter_type, e.discharge_disposition, e.source_system,
       COALESCE(p.patient_key, -1),
       CAST(regexp_replace(to_date(e.admit_ts), '-', '') AS INT),
       COALESCE(CAST(regexp_replace(to_date(e.discharge_ts), '-', '') AS INT), -1),
       COALESCE(dep.department_key, -1),
       COALESCE(b.bed_key, -1),
       COALESCE(pd.diagnosis_key, -2),
       CAST(e.triage_level AS INT),
       CASE WHEN e.encounter_type = 'IP' AND e.discharge_ts >= e.admit_ts
            THEN datediff(e.discharge_ts, e.admit_ts) END,
       CAST(e.ed_wait_minutes AS INT),
       CASE WHEN e.discharge_disposition = 'LEFT_WITHOUT_BEING_SEEN' THEN 1 ELSE 0 END,
       CASE WHEN e.bed_id = 'OVERFLOW' THEN 1 ELSE 0 END,
       CASE WHEN e.encounter_type = 'IP' AND e.next_admit_ts IS NOT NULL
             AND datediff(e.next_admit_ts, e.discharge_ts) BETWEEN 0 AND 30 THEN 1 ELSE 0 END,
       CASE WHEN e.readmission_flag = 'Y' THEN 1 ELSE 0 END,
       1,
       year(e.admit_ts), month(e.admit_ts)
FROM (
  SELECT x.*,
         CASE WHEN x.encounter_type = 'IP' THEN
           LEAD(x.admit_ts) OVER (PARTITION BY x.canonical_mrn, x.encounter_type ORDER BY x.admit_ts)
         END AS next_admit_ts
  FROM (
    SELECT en.encounter_id, en.encounter_type, en.department, en.admit_ts, en.discharge_ts,
           en.bed_id, en.triage_level, en.ed_wait_minutes, en.discharge_disposition,
           en.readmission_flag, en.source_system,
           COALESCE(m.canonical_mrn, en.mrn) AS canonical_mrn
    FROM curated.encounters en
    LEFT JOIN curated.mrn_map m ON en.mrn = m.mrn
  ) x
) e
LEFT JOIN dim_patient          p   ON e.canonical_mrn = p.mrn
LEFT JOIN dim_department       dep ON e.department = dep.department_code
LEFT JOIN dim_bed              b   ON e.bed_id = b.bed_id
LEFT JOIN encounter_primary_dx pd  ON e.encounter_id = pd.encounter_id;

-- Claim: one row = one claim submission (a resubmission is its own row)
DROP TABLE IF EXISTS fact_claim;
CREATE TABLE fact_claim (
  claim_id               STRING,   -- degenerate dimensions: claim_id .. claim_status
  resubmission_of        STRING,
  encounter_id           STRING,
  claim_status           STRING,   -- PAID / PARTIAL / DENIED / PENDING
  patient_key            INT,
  submitted_date_key     INT,      -- Time role: submitted
  paid_date_key          INT,      -- Time role: paid
  payer_key              INT,
  department_key         INT,      -- from the encounter of the claim
  diagnosis_key          INT,      -- primary diagnosis of the encounter (problem 4)
  denial_reason_key      INT,
  total_amount           DECIMAL(12,2),
  paid_amount            DECIMAL(12,2),
  denied_flag            INT,
  first_submission_flag  INT,      -- 1 = not a resubmission
  claim_count            INT
)
PARTITIONED BY (year INT, month INT)
CLUSTERED BY (patient_key) INTO 8 BUCKETS
STORED AS TEXTFILE;

INSERT OVERWRITE TABLE fact_claim PARTITION (year, month)
SELECT c.claim_id, c.resubmission_of, c.encounter_id, c.status,
       COALESCE(p.patient_key, -1),
       CAST(regexp_replace(to_date(c.submitted_date), '-', '') AS INT),
       COALESCE(CAST(regexp_replace(to_date(c.paid_date), '-', '') AS INT), -1),
       COALESCE(py.payer_key, -1),
       COALESCE(dep.department_key, -1),
       CASE WHEN e.encounter_id IS NULL THEN -1          -- orphan claim
            ELSE COALESCE(pd.diagnosis_key, -2) END,     -- no primary dx = MISSING
       COALESCE(dr.denial_reason_key, -1),
       c.total_amount, c.paid_amount,
       CASE WHEN c.status = 'DENIED' THEN 1 ELSE 0 END,
       CASE WHEN c.resubmission_of IS NULL OR c.resubmission_of = '' THEN 1 ELSE 0 END,
       1,
       year(c.submitted_date), month(c.submitted_date)
FROM curated.claims c
LEFT JOIN curated.encounters   e   ON c.encounter_id = e.encounter_id
LEFT JOIN curated.mrn_map      m   ON c.mrn = m.mrn
LEFT JOIN dim_patient          p   ON COALESCE(m.canonical_mrn, c.mrn) = p.mrn
LEFT JOIN dim_payer            py  ON c.payer = py.payer_name
LEFT JOIN dim_department       dep ON e.department = dep.department_code
LEFT JOIN encounter_primary_dx pd  ON c.encounter_id = pd.encounter_id
LEFT JOIN dim_denial_reason    dr  ON c.denial_code = dr.denial_code;

-- Dispense: one row = one dispensing of one drug to one patient
DROP TABLE IF EXISTS fact_dispense;
CREATE TABLE fact_dispense (
  dispense_id         STRING,   -- degenerate dimensions: dispense_id .. substituted_for
  encounter_id        STRING,
  dispense_status     STRING,   -- DISPENSED / DELAYED_STOCKOUT / SUBSTITUTED
  substituted_for     STRING,
  patient_key         INT,
  dispense_date_key   INT,      -- Time role: dispensed
  drug_key            INT,
  qty                 INT,      -- additive
  delay_minutes       INT,      -- additive, report AVG
  stockout_flag       INT,      -- 1 = DELAYED_STOCKOUT or SUBSTITUTED
  dispense_count      INT
)
PARTITIONED BY (year INT, month INT)
CLUSTERED BY (patient_key) INTO 8 BUCKETS
STORED AS TEXTFILE;

INSERT OVERWRITE TABLE fact_dispense PARTITION (year, month)
SELECT ds.dispense_id, ds.encounter_id, ds.status, ds.substituted_for,
       COALESCE(p.patient_key, -1),
       CAST(regexp_replace(to_date(ds.dispensed_at), '-', '') AS INT),
       COALESCE(dr.drug_key, -1),
       ds.qty, ds.delay_minutes,
       CASE WHEN ds.status IN ('DELAYED_STOCKOUT', 'SUBSTITUTED') THEN 1 ELSE 0 END,
       1,
       year(ds.dispensed_at), month(ds.dispensed_at)
FROM curated.dispense ds
LEFT JOIN curated.mrn_map m  ON ds.mrn = m.mrn
LEFT JOIN dim_patient     p  ON COALESCE(m.canonical_mrn, ds.mrn) = p.mrn
LEFT JOIN dim_drug        dr ON ds.drug_code = dr.drug_code;

-- Inventory transaction: one row = one stock movement (RECEIPT / ISSUE / ADJUSTMENT)
-- of one drug in one store. The ERP gives movements, not stock levels, so stock-outs show up
-- as "no RECEIPT rows" for a drug in the weeks before and during the dispensing delays.
DROP TABLE IF EXISTS fact_inventory_txn;
CREATE TABLE fact_inventory_txn (
  txn_id         STRING,   -- degenerate dimension
  txn_type       STRING,   -- degenerate dimension
  txn_date_key   INT,      -- Time role: transaction
  drug_key       INT,
  store_key      INT,
  qty            INT,      -- additive (within one txn_type)
  receipt_qty    INT,      -- additive: qty on RECEIPT rows, else 0
  unit_cost      DECIMAL(10,2),  -- NON-additive: never SUM a price
  txn_count      INT
)
PARTITIONED BY (year INT, month INT)
STORED AS TEXTFILE;

INSERT OVERWRITE TABLE fact_inventory_txn PARTITION (year, month)
SELECT i.txn_id, i.txn_type,
       CAST(regexp_replace(to_date(i.txn_ts), '-', '') AS INT),
       COALESCE(dr.drug_key, -1),
       COALESCE(st.store_key, -1),
       i.qty,
       CASE WHEN i.txn_type = 'RECEIPT' THEN i.qty ELSE 0 END,
       i.unit_cost,
       1,
       year(i.txn_ts), month(i.txn_ts)
FROM curated.inventory i
LEFT JOIN dim_drug  dr ON i.item_code = dr.drug_code
LEFT JOIN dim_store st ON i.store = st.store_name;

-- ---------------------------------------------------------------------
-- 4. SUMMARY TABLES (L7 materialized-view idea: stored answers, refreshed with
--    INSERT OVERWRITE after each fact load, i.e. a full refresh)
-- ---------------------------------------------------------------------

-- Midnight census: an IP patient occupies a bed on day d if admit_date <= d < discharge_date.
-- posexplode(split(space(n), a space)) makes rows pos = 0..n, keep pos < n.
-- ward_beds = beds seen in the data (all 252 appear in the full dataset, far fewer in the 2% sample).
DROP TABLE IF EXISTS agg_daily_occupancy;
CREATE TABLE agg_daily_occupancy (
  census_date    STRING,
  ward           STRING,
  ward_beds      INT,
  occupied_beds  INT        -- for ward OVERFLOW: patients boarded with no bed
) STORED AS TEXTFILE;

INSERT OVERWRITE TABLE agg_daily_occupancy
SELECT o.census_date, o.ward, COALESCE(cap.ward_beds, 0), o.occupied
FROM (
  SELECT CAST(date_add(s.admit_date, t.pos) AS STRING) AS census_date, s.ward, COUNT(*) AS occupied
  FROM (
    SELECT ad.full_date AS admit_date, b.ward,
           datediff(dd.full_date, ad.full_date) AS nights
    FROM fact_encounter f
    JOIN dim_date ad ON f.admit_date_key = ad.date_key
    JOIN dim_date dd ON f.discharge_date_key = dd.date_key
    JOIN dim_bed  b  ON f.bed_key = b.bed_key
    WHERE f.encounter_type = 'IP' AND f.bed_key <> -1 AND f.los_days IS NOT NULL
  ) s
  LATERAL VIEW posexplode(split(space(s.nights), ' ')) t AS pos, x
  WHERE t.pos < s.nights
  GROUP BY CAST(date_add(s.admit_date, t.pos) AS STRING), s.ward
) o
LEFT JOIN (SELECT ward, COUNT(*) AS ward_beds FROM dim_bed
           WHERE bed_type IN ('WARD', 'ICU') GROUP BY ward) cap
       ON o.ward = cap.ward;

DROP TABLE IF EXISTS agg_monthly_denials;
CREATE TABLE agg_monthly_denials (
  year             INT,
  month            INT,
  payer_name       STRING,
  department_code  STRING,
  denial_code      STRING,
  claims           BIGINT,
  first_submissions BIGINT,
  denied_claims    BIGINT,
  denied_amount    DECIMAL(14,2)
) STORED AS TEXTFILE;

INSERT OVERWRITE TABLE agg_monthly_denials
SELECT f.year, f.month, py.payer_name, dep.department_code, dr.denial_code,
       SUM(f.claim_count), SUM(f.first_submission_flag), SUM(f.denied_flag),
       SUM(CASE WHEN f.denied_flag = 1 THEN f.total_amount ELSE 0 END)
FROM fact_claim f
JOIN dim_payer         py  ON f.payer_key = py.payer_key
JOIN dim_department    dep ON f.department_key = dep.department_key
JOIN dim_denial_reason dr  ON f.denial_reason_key = dr.denial_reason_key
GROUP BY f.year, f.month, py.payer_name, dep.department_code, dr.denial_code;

-- ---------------------------------------------------------------------
-- 5. CHECKS (screenshot these for the report)
-- ---------------------------------------------------------------------

-- Row counts: each fact must equal its curated source (LEFT JOINs drop nothing)
SELECT 'curated.encounters', COUNT(*) FROM curated.encounters UNION ALL
SELECT 'fact_encounter', COUNT(*) FROM fact_encounter UNION ALL
SELECT 'curated.claims', COUNT(*) FROM curated.claims UNION ALL
SELECT 'fact_claim', COUNT(*) FROM fact_claim UNION ALL
SELECT 'curated.dispense', COUNT(*) FROM curated.dispense UNION ALL
SELECT 'fact_dispense', COUNT(*) FROM fact_dispense UNION ALL
SELECT 'curated.inventory', COUNT(*) FROM curated.inventory UNION ALL
SELECT 'fact_inventory_txn', COUNT(*) FROM fact_inventory_txn;

-- Placeholder hits = data-quality evidence
SELECT SUM(CASE WHEN patient_key = -1 THEN 1 ELSE 0 END)           AS unknown_patient,
       SUM(CASE WHEN department_key = -1 THEN 1 ELSE 0 END)        AS unknown_department,
       SUM(CASE WHEN primary_diagnosis_key = -2 THEN 1 ELSE 0 END) AS missing_primary_dx,
       SUM(CASE WHEN primary_diagnosis_key = -3 THEN 1 ELSE 0 END) AS invalid_primary_dx
FROM fact_encounter;

-- Problem 4 straight from the star: denial rate of first submissions by coding status
-- (answer key: about 53% for missing/invalid vs about 6% otherwise)
SELECT dg.coding_status, SUM(f.claim_count) AS claims,
       ROUND(AVG(f.denied_flag), 3) AS denial_rate
FROM fact_claim f JOIN dim_diagnosis dg ON f.diagnosis_key = dg.diagnosis_key
WHERE f.first_submission_flag = 1
GROUP BY dg.coding_status;

-- Partitions + partition pruning (compare with Lab 5 B2)
SHOW PARTITIONS fact_claim;
EXPLAIN EXTENDED
SELECT SUM(total_amount) FROM fact_claim WHERE year = 2025 AND month = 1;
