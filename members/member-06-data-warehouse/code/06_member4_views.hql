-- Member 6: swap Member 4's clinical tables in place of Member 6's stand-in tables.
-- Run AFTER Member 4's ETL has created their tables.
-- 1. Check with  SHOW TABLES IN default;  that curated_patients, mrn_map, curated_encounters, curated_diagnoses exist.
-- 2. The FROM lines below already point at Member 4's tables from ahd_clinical_etl.hql (database default).
-- 3. Run:  beeline -u jdbc:hive2://localhost:10000 -n bigdata -f 06_member4_views.hql
-- The stand-in tables are EXTERNAL, so dropping them removes only the table definition, not any data.
-- Run it once. To run it again, first delete the four DROP TABLE lines (Hive refuses DROP TABLE on a view).

CREATE DATABASE IF NOT EXISTS curated;

DROP TABLE IF EXISTS curated.patients;
DROP VIEW IF EXISTS curated.patients;
CREATE VIEW curated.patients AS
SELECT mrn, first_name, last_name, gender, date_of_birth, nationality, emirate
-- Member 4 table (checked against ahd_clinical_etl.hql):
FROM default.curated_patients;

-- every duplicate or legacy MRN -> its real MRN (MRNs that map to themselves may be included or not)
DROP TABLE IF EXISTS curated.mrn_map;
DROP VIEW IF EXISTS curated.mrn_map;
CREATE VIEW curated.mrn_map AS
SELECT std_mrn AS mrn, master_mrn AS canonical_mrn
-- Member 4 table (checked against ahd_clinical_etl.hql):
FROM default.mrn_map;

DROP TABLE IF EXISTS curated.encounters;
DROP VIEW IF EXISTS curated.encounters;
CREATE VIEW curated.encounters AS
SELECT encounter_id, mrn, encounter_type, department, attending_id, admit_ts, discharge_ts,
       bed_id, triage_level, ed_wait_minutes, discharge_disposition, readmission_flag, source_system
-- Member 4 table (checked against ahd_clinical_etl.hql):
FROM default.curated_encounters;

DROP TABLE IF EXISTS curated.diagnoses;
DROP VIEW IF EXISTS curated.diagnoses;
CREATE VIEW curated.diagnoses AS
SELECT encounter_id, seq, icd10_code, description, dx_type, recorded_at
-- Member 4 table (checked against ahd_clinical_etl.hql):
FROM default.curated_diagnoses;

-- Compare with the stand-in: 777278 encounters (Member 4's number may be lower if they rejected rows)
SELECT 'patients', COUNT(*) FROM curated.patients UNION ALL
SELECT 'mrn_map', COUNT(*) FROM curated.mrn_map UNION ALL
SELECT 'encounters', COUNT(*) FROM curated.encounters UNION ALL
SELECT 'diagnoses', COUNT(*) FROM curated.diagnoses;
