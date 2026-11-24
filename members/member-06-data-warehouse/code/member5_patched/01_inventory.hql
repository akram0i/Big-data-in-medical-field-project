-- Member 5 - 01_inventory.hql : Oracle SCM drug-stock XML -> ahd.cur_inventory
-- Loaded FIRST: cur_dispense looks drug codes up in this table.
--
-- ASSUMED XML LAYOUT (check with 00_discover.sh; edit only the xpath lines marked VERIFY):
--   one record per line, e.g.
--   <item><record_id>INV-1</record_id><drug_code>D001</drug_code><drug_name>..</drug_name>
--         <qty_on_hand>40</qty_on_hand><reorder_level>10</reorder_level><unit_cost>3.5</unit_cost>
--         <snapshot_date>15-JAN-24</snapshot_date><last_updated>2024-01-15 08:00:00</last_updated></item>
-- If a record spans several lines, see "Multi-line XML" in the report notes.

USE ahd;
SET hive.exec.dynamic.partition=true;
SET hive.exec.dynamic.partition.mode=nonstrict;
SET mapreduce.input.fileinputformat.input.dir.recursive=true;
SET hive.mapred.supports.subdirectories=true;

-- 1. Raw external table: one STRING per line. Raw files are never edited.
DROP TABLE IF EXISTS raw_inventory_xml;
CREATE EXTERNAL TABLE raw_inventory_xml (line STRING)
STORED AS TEXTFILE
LOCATION '${hivevar:RAW}/erp_oracle';

-- 2. Parse with xpath_string; convert the Oracle date and the numbers.
DROP TABLE IF EXISTS stg_inventory;
CREATE TABLE stg_inventory STORED AS ORC AS
SELECT
  INPUT__FILE__NAME                                         AS src_file,
  xpath_string(line, '/Txn/@id')                            AS record_id,
  xpath_string(line, '/Txn/ItemCode')                       AS drug_code,
  xpath_string(line, '/Txn/ItemName')                       AS drug_name,
  CAST(xpath_string(line, '/Txn/Qty') AS INT)               AS qty_on_hand,
  CAST(0 AS INT)                                            AS reorder_level,
  xpath_string(line, '/Txn/Type')                           AS txn_type,   -- added for Member 6
  xpath_string(line, '/Txn/Store')                          AS store,      -- added for Member 6
  CAST(xpath_string(line, '/Txn/UnitCost') AS DECIMAL(10,2)) AS unit_cost,
  COALESCE(
    to_date(substr(xpath_string(line, '/Txn/Timestamp'), 1, 10)),
    to_date(from_unixtime(unix_timestamp(substr(xpath_string(line, '/Txn/Timestamp'), 1, 11), 'dd-MMM-yyyy')))
  ) AS snapshot_date,
  xpath_string(line, '/Txn/Timestamp')                      AS last_updated,
  line                                                      AS raw_record
FROM raw_inventory_xml
WHERE line RLIKE '<Txn[ >]';

-- 3. Check rules and de-duplicate: one reason per row, first failing rule wins.
--    Among rows that share a record_id, a valid row beats an invalid one, then the latest update wins.
DROP TABLE IF EXISTS chk_inventory;
CREATE TABLE chk_inventory STORED AS ORC AS
SELECT t.*,
  COALESCE(t.bad_reason, CASE WHEN t.rn > 1 THEN 'DUPLICATE_ID' END) AS reason
FROM (
  SELECT s.*,
    row_number() OVER (PARTITION BY record_id
                       ORDER BY (CASE WHEN bad_reason IS NULL THEN 0 ELSE 1 END),
                                last_updated DESC, src_file DESC) AS rn
  FROM (
    SELECT i.*,
      CASE WHEN record_id IS NULL OR record_id = ''             THEN 'MISSING_ID'
           WHEN drug_code IS NULL OR drug_code = ''             THEN 'MISSING_DRUG_CODE'
           WHEN snapshot_date IS NULL                           THEN 'BAD_DATE'
           WHEN qty_on_hand IS NULL OR qty_on_hand < 0          THEN 'BAD_QUANTITY'
      END AS bad_reason
    FROM stg_inventory i
  ) s
) t;

-- 4. Curated table (stored in the curated zone, /datalake/curated/cur_inventory): internal, partitioned by month of the snapshot date.
DROP TABLE IF EXISTS cur_inventory;
CREATE TABLE cur_inventory (
  record_id STRING, drug_code STRING, drug_name STRING,
  qty_on_hand INT, reorder_level INT, unit_cost DECIMAL(10,2),
  snapshot_date DATE, last_updated STRING,
  txn_type STRING, store STRING
)
PARTITIONED BY (year INT, month INT)
STORED AS ORC
LOCATION '${hivevar:CURATED}/cur_inventory';

INSERT OVERWRITE TABLE cur_inventory PARTITION (year, month)
SELECT record_id, drug_code, drug_name, qty_on_hand, reorder_level, unit_cost,
       snapshot_date, last_updated, txn_type, store, year(snapshot_date), month(snapshot_date)
FROM chk_inventory
WHERE reason IS NULL;

-- 5. Rejects, with the reason and the original record.
DROP TABLE IF EXISTS rej_inventory;
CREATE TABLE rej_inventory STORED AS ORC AS
SELECT 'inventory' AS source, reason, record_id AS record_key, raw_record, src_file AS source_file
FROM chk_inventory
WHERE reason IS NOT NULL;
