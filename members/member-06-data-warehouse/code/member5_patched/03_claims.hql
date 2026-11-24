-- Member 5 - 03_claims.hql : Oracle billing claims CSV -> ahd.cur_claims
--
-- ASSUMED COLUMN ORDER (check the header with 00_discover.sh; edit the column list marked VERIFY):
--   claim_id, encounter_id, mrn, payer, department, diagnosis_code, claim_amount,
--   status, denial_reason, submitted_date, resubmission_of
-- Amounts look like "AED 1,234.50" (comma inside quotes), so LazySimpleSerDe would split them.
-- OpenCSVSerde respects the quotes. It returns every column as STRING; we cast ourselves.

SET mapreduce.map.memory.mb=2048;
SET mapreduce.map.java.opts=-Xmx1536m;
SET mapreduce.reduce.memory.mb=2048;
SET mapreduce.reduce.java.opts=-Xmx1536m;

USE ahd;
SET hive.exec.dynamic.partition=true;
SET hive.exec.dynamic.partition.mode=nonstrict;
SET mapreduce.input.fileinputformat.input.dir.recursive=true;
SET hive.mapred.supports.subdirectories=true;

-- 1. Raw external table over the CSV, header skipped.
DROP TABLE IF EXISTS raw_claims_csv;
CREATE EXTERNAL TABLE raw_claims_csv (
  claim_id STRING, encounter_id STRING, mrn STRING, payer STRING,
  submitted_date STRING, claim_amount STRING, status STRING,
  denial_code STRING, denial_reason STRING, paid_amount STRING,
  paid_date STRING, resubmission_of STRING
)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
WITH SERDEPROPERTIES ('separatorChar' = ',', 'quoteChar' = '"', 'escapeChar' = '\\')
STORED AS TEXTFILE
LOCATION '${hivevar:RAW}/billing_oracle'
TBLPROPERTIES ('skip.header.line.count' = '1');

-- 2. Clean: amounts, dates, diagnosis code, resubmission link text.
DROP TABLE IF EXISTS stg_claims;
CREATE TABLE stg_claims STORED AS ORC AS
SELECT
  INPUT__FILE__NAME AS src_file,
  trim(claim_id) AS claim_id, trim(encounter_id) AS encounter_id, trim(mrn) AS mrn,
  trim(payer) AS payer, CAST(NULL AS STRING) AS department,
  -- Map denial_code into diagnosis_code format
  CASE WHEN trim(denial_code) = '' OR denial_code IS NULL THEN NULL
       ELSE regexp_replace(upper(regexp_replace(trim(denial_code), '\\.', '')),
                           '^([A-Z][0-9]{2})([0-9A-Z]+)$', '$1.$2') END AS diagnosis_code,
  claim_amount AS amount_raw,
  CASE WHEN regexp_replace(claim_amount, '[^0-9.\\-]', '') = '' THEN NULL
       ELSE CAST(regexp_replace(claim_amount, '[^0-9.\\-]', '') AS DECIMAL(12,2)) END AS claim_amount,
  trim(status) AS status, trim(denial_reason) AS denial_reason,
  -- added for Member 6
  CASE WHEN trim(denial_code) = '' THEN NULL ELSE trim(denial_code) END AS denial_code,
  CASE WHEN regexp_replace(paid_amount, '[^0-9.\\-]', '') = '' THEN NULL
       ELSE CAST(regexp_replace(paid_amount, '[^0-9.\\-]', '') AS DECIMAL(12,2)) END AS paid_amount,
  CASE WHEN trim(paid_date) RLIKE '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN to_date(substr(trim(paid_date), 1, 10)) END AS paid_date,
  submitted_date AS date_raw,
  CASE WHEN trim(submitted_date) RLIKE '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
         THEN to_date(substr(trim(submitted_date), 1, 10))
       WHEN trim(submitted_date) RLIKE '^[0-9]{2}/[0-9]{2}/[0-9]{4}'
         THEN to_date(from_unixtime(unix_timestamp(trim(submitted_date), 'dd/MM/yyyy')))
  END AS submitted_date,
  CASE WHEN resubmission_of IS NULL OR trim(resubmission_of) = '' THEN NULL ELSE trim(resubmission_of) END AS resubmission_of,
  concat_ws(',', claim_id, encounter_id, mrn, payer, denial_code, claim_amount,
            status, denial_reason, submitted_date, resubmission_of) AS raw_record
FROM raw_claims_csv;

-- 3. Check rules and de-duplicate. Blank amounts and invalid diagnosis codes are KEPT and flagged:
--    they are exactly the denied-claim evidence the business problems need.
DROP TABLE IF EXISTS chk_claims;
CREATE TABLE chk_claims STORED AS ORC AS
SELECT t.*,
  COALESCE(t.bad_reason, CASE WHEN t.rn > 1 THEN 'DUPLICATE_ID' END) AS reason
FROM (
  SELECT s.*,
    row_number() OVER (PARTITION BY claim_id
                       ORDER BY (CASE WHEN bad_reason IS NULL THEN 0 ELSE 1 END), src_file) AS rn
  FROM (
    SELECT c.*,
      CASE WHEN claim_id IS NULL OR claim_id = ''                         THEN 'MISSING_ID'
           WHEN submitted_date IS NULL                                    THEN 'BAD_DATE'
           WHEN claim_amount IS NULL AND trim(amount_raw) <> ''
                AND regexp_replace(amount_raw, '[^0-9.\\-]', '') <> ''    THEN 'BAD_AMOUNT'
           WHEN claim_amount < 0                                          THEN 'NEGATIVE_AMOUNT'
      END AS bad_reason
    FROM stg_claims c
  ) s
) t;

-- 4. Curated table (stored in the curated zone, /datalake/curated/cur_claims). Resubmission link is checked with LEFT OUTER JOIN ... IS NULL (Hive has no MINUS):
--    a link to a claim_id that does not exist is set to NULL and flagged, the claim itself is kept.
DROP TABLE IF EXISTS cur_claims;
CREATE TABLE cur_claims (
  claim_id STRING, encounter_id STRING, mrn STRING, payer STRING, department STRING,
  diagnosis_code STRING, dx_valid BOOLEAN,
  claim_amount DECIMAL(12,2), amount_missing BOOLEAN,
  status STRING, denial_reason STRING, submitted_date DATE,
  original_claim_id STRING, is_resubmission BOOLEAN, resub_link_ok BOOLEAN,
  denial_code STRING, paid_amount DECIMAL(12,2), paid_date DATE, resubmission_of STRING
)
PARTITIONED BY (year INT, month INT)
CLUSTERED BY (mrn) INTO 8 BUCKETS
STORED AS ORC
LOCATION '${hivevar:CURATED}/cur_claims';

INSERT OVERWRITE TABLE cur_claims PARTITION (year, month)
SELECT c.claim_id, c.encounter_id, c.mrn, c.payer, c.department,
       c.diagnosis_code,
       (c.diagnosis_code RLIKE '^[A-TV-Z][0-9][0-9AB](\\.[0-9A-TV-Z]{1,4})?$') AS dx_valid,
       c.claim_amount, (c.claim_amount IS NULL) AS amount_missing,
       c.status, c.denial_reason, c.submitted_date,
       CASE WHEN o.claim_id IS NOT NULL THEN c.resubmission_of END AS original_claim_id,
       (c.resubmission_of IS NOT NULL) AS is_resubmission,
       (c.resubmission_of IS NULL OR o.claim_id IS NOT NULL) AS resub_link_ok,
       c.denial_code, c.paid_amount, c.paid_date, c.resubmission_of,
       year(c.submitted_date), month(c.submitted_date)
FROM chk_claims c
LEFT OUTER JOIN (SELECT DISTINCT claim_id FROM chk_claims WHERE reason IS NULL) o
  ON c.resubmission_of = o.claim_id
WHERE c.reason IS NULL;

-- 5. Rejects.
DROP TABLE IF EXISTS rej_claims;
CREATE TABLE rej_claims STORED AS ORC AS
SELECT 'claims' AS source, reason, claim_id AS record_key, raw_record, src_file AS source_file
FROM chk_claims
WHERE reason IS NOT NULL;
