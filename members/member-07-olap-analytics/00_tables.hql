-- Member 7 isolated reporting schema. Set ROOT to the HDFS directory containing
-- one headerless, tab-delimited file per subdirectory from prepare_hive.py.
CREATE DATABASE IF NOT EXISTS ahd_member7;
USE ahd_member7;

DROP TABLE IF EXISTS encounters;
CREATE EXTERNAL TABLE encounters (
  encounter_id STRING, mrn STRING, encounter_type STRING, department STRING,
  admit_ts STRING, discharge_ts STRING, bed_id STRING, ed_wait_minutes INT,
  discharge_disposition STRING, readmission_flag STRING
) ROW FORMAT DELIMITED FIELDS TERMINATED BY '\t' STORED AS TEXTFILE
LOCATION '${hivevar:ROOT}/encounters';

DROP TABLE IF EXISTS diagnoses;
CREATE EXTERNAL TABLE diagnoses (
  encounter_id STRING, seq INT, icd10_code STRING, dx_type STRING, dx_valid INT
) ROW FORMAT DELIMITED FIELDS TERMINATED BY '\t' STORED AS TEXTFILE
LOCATION '${hivevar:ROOT}/diagnoses';

DROP TABLE IF EXISTS claims;
CREATE EXTERNAL TABLE claims (
  claim_id STRING, encounter_id STRING, mrn STRING, payer STRING,
  submitted_ts STRING, status STRING, denial_code STRING, resubmission_of STRING
) ROW FORMAT DELIMITED FIELDS TERMINATED BY '\t' STORED AS TEXTFILE
LOCATION '${hivevar:ROOT}/claims';

DROP TABLE IF EXISTS dispenses;
CREATE EXTERNAL TABLE dispenses (
  dispense_id STRING, encounter_id STRING, mrn STRING, drug_code STRING,
  drug_name STRING, qty INT, dispensed_ts STRING, status STRING,
  substituted_for STRING
) ROW FORMAT DELIMITED FIELDS TERMINATED BY '\t' STORED AS TEXTFILE
LOCATION '${hivevar:ROOT}/dispenses';

DROP TABLE IF EXISTS inventory;
CREATE EXTERNAL TABLE inventory (
  record_id STRING, drug_code STRING, txn_type STRING, qty INT, txn_ts STRING
) ROW FORMAT DELIMITED FIELDS TERMINATED BY '\t' STORED AS TEXTFILE
LOCATION '${hivevar:ROOT}/inventory';

DROP TABLE IF EXISTS feedback;
CREATE EXTERNAL TABLE feedback (
  feedback_id STRING, submitted_ts STRING, encounter_id STRING,
  rating INT, comment STRING
) ROW FORMAT DELIMITED FIELDS TERMINATED BY '\t' STORED AS TEXTFILE
LOCATION '${hivevar:ROOT}/feedback';

DROP TABLE IF EXISTS events;
CREATE EXTERNAL TABLE events (
  event_id STRING, bed_id STRING, mrn STRING, encounter_id STRING,
  event_ts STRING, event_type STRING
) ROW FORMAT DELIMITED FIELDS TERMINATED BY '\t' STORED AS TEXTFILE
LOCATION '${hivevar:ROOT}/events';

DROP TABLE IF EXISTS vitals;
CREATE EXTERNAL TABLE vitals (
  bed_id STRING, mrn STRING, vital_ts STRING, hr INT, spo2 INT, rr INT, sbp INT
) ROW FORMAT DELIMITED FIELDS TERMINATED BY '\t' STORED AS TEXTFILE
LOCATION '${hivevar:ROOT}/vitals';

DROP TABLE IF EXISTS months;
CREATE EXTERNAL TABLE months (
  month_key STRING, start_date STRING, next_date STRING
) ROW FORMAT DELIMITED FIELDS TERMINATED BY '\t' STORED AS TEXTFILE
LOCATION '${hivevar:ROOT}/months';

SELECT 'encounters' AS source, count(*) AS row_count FROM encounters
UNION ALL SELECT 'diagnoses', count(*) FROM diagnoses
UNION ALL SELECT 'claims', count(*) FROM claims
UNION ALL SELECT 'dispenses', count(*) FROM dispenses
UNION ALL SELECT 'inventory', count(*) FROM inventory
UNION ALL SELECT 'feedback', count(*) FROM feedback
UNION ALL SELECT 'events', count(*) FROM events
UNION ALL SELECT 'vitals', count(*) FROM vitals;
