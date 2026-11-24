-- Member 2 outputs exposed to Hive (for Member 4/6/7). External tables: dropping them never deletes the files.
-- Run with:  hive -f hive/member2_tables.hql   (or paste into Beeline / Zeppelin %jdbc(hive))

CREATE DATABASE IF NOT EXISTS ahd_curated;
USE ahd_curated;

-- Job 1 output: one row per lab result (OBX), cleaned
CREATE EXTERNAL TABLE IF NOT EXISTS lab_results (
  control_id     STRING,
  mrn            STRING,
  encounter_id   STRING,
  patient_class  STRING,     -- I inpatient, E emergency, O outpatient
  department     STRING,
  panel_code     STRING,
  order_ts       TIMESTAMP,
  result_ts      TIMESTAMP,
  test_code      STRING,
  test_name      STRING,
  value          DOUBLE,     -- glucose always mg/dL
  unit           STRING,
  ref_low        DOUBLE,
  ref_high       DOUBLE,
  abnormal_flag  STRING,     -- H / L / N
  qc_note        STRING      -- OK, GLU_MMOL_CONVERTED, FLAG_DERIVED, RESULT_BEFORE_ORDER (';'-separated)
)
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
STORED AS TEXTFILE
LOCATION '/datalake/curated/lab_results';

-- Job 2 output
CREATE EXTERNAL TABLE IF NOT EXISTS lab_abnormal_counts (
  panel_code STRING, test_code STRING, abnormal_flag STRING, n BIGINT
)
ROW FORMAT DELIMITED FIELDS TERMINATED BY '\t'
STORED AS TEXTFILE
LOCATION '/datalake/curated/lab_abnormal_counts';

-- Job 3 output (ranked complaint words; part-r-00000 English, part-r-00001 Arabic)
CREATE EXTERNAL TABLE IF NOT EXISTS feedback_word_rank (
  word_rank INT, word STRING, n BIGINT
)
ROW FORMAT DELIMITED FIELDS TERMINATED BY '\t'
STORED AS TEXTFILE
LOCATION '/datalake/curated/feedback_words/ranked';

-- Checks for screenshots
SELECT qc_note, COUNT(*) FROM lab_results GROUP BY qc_note;

SELECT panel_code, test_code,
       SUM(CASE WHEN abnormal_flag <> 'N' THEN n ELSE 0 END)                         AS abnormal,
       SUM(n)                                                                        AS total,
       ROUND(100 * SUM(CASE WHEN abnormal_flag <> 'N' THEN n ELSE 0 END) / SUM(n), 1) AS abnormal_pct
FROM lab_abnormal_counts
GROUP BY panel_code, test_code
ORDER BY abnormal_pct DESC;
