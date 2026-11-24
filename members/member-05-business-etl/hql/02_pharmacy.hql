-- Increase memory limits for handling large JSON logs
SET mapreduce.map.memory.mb=2048;
SET mapreduce.map.java.opts=-Xmx1536m;
SET mapreduce.reduce.memory.mb=2048;
SET mapreduce.reduce.java.opts=-Xmx1536m;

-- Member 5 - 02_pharmacy.hql : pharmacy dispensing JSON (v1 2024, v2 2025) -> ahd.cur_dispense
-- Needs ahd.cur_inventory (run 01_inventory.hql first).
--
-- ASSUMED JSON KEYS (check with 00_discover.sh; edit only the lines marked VERIFY):
--   v1 (2024): dispense_id, encounter_id, mrn, drug_code, drug_name, qty, unit_price, dispensed_at (epoch ms)
--   v2 (2025): dispense_id, encounter_id, patient.mrn, drug.code, drug.name, quantity, unit_price, dispense_ts (epoch ms)
-- COALESCE takes whichever name the row has, so both versions land in one layout.

USE ahd;
SET hive.exec.dynamic.partition=true;
SET hive.exec.dynamic.partition.mode=nonstrict;
SET hive.enforce.bucketing=true;
SET mapreduce.input.fileinputformat.input.dir.recursive=true;
SET hive.mapred.supports.subdirectories=true;

-- 1. Raw external table: one STRING per JSON line.
DROP TABLE IF EXISTS raw_pharmacy_json;
CREATE EXTERNAL TABLE raw_pharmacy_json (line STRING)
STORED AS TEXTFILE
LOCATION '${hivevar:RAW}/pharmacy_api';

-- 2. Parse both schema versions into one layout and convert epoch milliseconds / strings.
DROP TABLE IF EXISTS stg_pharmacy;
CREATE TABLE stg_pharmacy STORED AS ORC AS
SELECT
  src_file,
  CASE WHEN regexp_extract(src_file, 'dispense_(\\d{4})-', 1) = '2024' THEN 'v1' ELSE 'v2' END AS schema_ver,
  dispense_id, encounter_id, mrn, drug_code, drug_name,
  CAST(qty_s AS INT)                  AS qty,
  CAST(price_s AS DECIMAL(10,2))      AS unit_price,
  -- Handle both epoch milliseconds and string timestamps safely
  CASE
    WHEN ts_ms RLIKE '^[0-9]{13}$' THEN from_utc_timestamp(CAST(CAST(ts_ms AS BIGINT) / 1000 AS TIMESTAMP), 'Asia/Dubai')
    WHEN ts_ms RLIKE '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN CAST(regexp_replace(substr(ts_ms, 1, 19), 'T', ' ') AS TIMESTAMP)
  END AS dispensed_ts,
  line AS raw_record
FROM (
  SELECT
    INPUT__FILE__NAME AS src_file, line,
    COALESCE(get_json_object(line, '$.dispense_id'), get_json_object(line, '$.id')) AS dispense_id,
    COALESCE(get_json_object(line, '$.encounter_id'), get_json_object(line, '$.patient.encounter')) AS encounter_id,
    COALESCE(get_json_object(line, '$.mrn'),
             get_json_object(line, '$.patient.mrn'))                            AS mrn,
    COALESCE(get_json_object(line, '$.drug_code'),
             get_json_object(line, '$.drug.code'))                              AS drug_code,
    COALESCE(get_json_object(line, '$.drug_name'),
             get_json_object(line, '$.drug.name'))                              AS drug_name,
    COALESCE(get_json_object(line, '$.qty'),
             get_json_object(line, '$.quantity'))                               AS qty_s,
    get_json_object(line, '$.unit_price')                                       AS price_s,
    COALESCE(get_json_object(line, '$.dispensed_at'),
             get_json_object(line, '$.timestamp'))                              AS ts_ms
  FROM raw_pharmacy_json
  WHERE trim(line) <> ''
) p;

-- 3. Check rules and de-duplicate (one reason per row, first failing rule wins;
--    a valid row beats an invalid row that shares its dispense_id).
DROP TABLE IF EXISTS chk_pharmacy;
CREATE TABLE chk_pharmacy STORED AS ORC AS
SELECT t.*,
  COALESCE(t.bad_reason, CASE WHEN t.rn > 1 THEN 'DUPLICATE_ID' END) AS reason
FROM (
  SELECT s.*,
    row_number() OVER (PARTITION BY dispense_id
                       ORDER BY (CASE WHEN bad_reason IS NULL THEN 0 ELSE 1 END),
                                dispensed_ts, src_file) AS rn
  FROM (
    SELECT p.*,
      CASE WHEN dispense_id IS NULL OR dispense_id = ''  THEN 'MISSING_ID'
           WHEN drug_code  IS NULL OR drug_code  = ''    THEN 'MISSING_DRUG_CODE'
           WHEN mrn        IS NULL OR mrn        = ''    THEN 'MISSING_MRN'
           WHEN qty IS NULL OR qty <= 0                  THEN 'BAD_QUANTITY'
           WHEN dispensed_ts IS NULL
             OR dispensed_ts <  CAST('2024-01-01 00:00:00' AS TIMESTAMP)
             OR dispensed_ts >= CAST('2026-01-01 00:00:00' AS TIMESTAMP) THEN 'BAD_TIMESTAMP'
      END AS bad_reason
    FROM stg_pharmacy p
  ) s
) t;

-- 4. Curated table (stored in the curated zone, /datalake/curated/cur_dispense): partitioned by month, 8 buckets by MRN (joins with Member 4's tables).
DROP TABLE IF EXISTS cur_dispense;
CREATE TABLE cur_dispense (
  dispense_id STRING, encounter_id STRING, mrn STRING,
  drug_code STRING, drug_name STRING, qty INT, unit_price DECIMAL(10,2),
  dispensed_ts TIMESTAMP, schema_ver STRING, drug_in_inventory BOOLEAN
)
PARTITIONED BY (year INT, month INT)
CLUSTERED BY (mrn) INTO 8 BUCKETS
STORED AS ORC
LOCATION '${hivevar:CURATED}/cur_dispense';

-- lookup: does the dispensed drug_code exist in the stock table? (flag only, row is kept)
INSERT OVERWRITE TABLE cur_dispense PARTITION (year, month)
SELECT c.dispense_id, c.encounter_id, c.mrn, c.drug_code, c.drug_name, c.qty, c.unit_price,
       c.dispensed_ts, c.schema_ver, (i.drug_code IS NOT NULL) AS drug_in_inventory,
       year(c.dispensed_ts), month(c.dispensed_ts)
FROM chk_pharmacy c
LEFT OUTER JOIN (SELECT DISTINCT drug_code FROM cur_inventory) i ON c.drug_code = i.drug_code
WHERE c.reason IS NULL;

-- 5. Rejects.
DROP TABLE IF EXISTS rej_pharmacy;
CREATE TABLE rej_pharmacy STORED AS ORC AS
SELECT 'pharmacy' AS source, reason, dispense_id AS record_key, raw_record, src_file AS source_file
FROM chk_pharmacy
WHERE reason IS NOT NULL;
