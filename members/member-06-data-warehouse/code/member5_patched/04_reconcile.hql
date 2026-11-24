-- Member 5 - 04_reconcile.hql : rej_business, count reconciliation, evidence queries.
-- Rule: every raw row ends up in exactly one place, so  raw = curated + rejected  for each source.

USE ahd;

-- 1. One reject table for all three sources (rebuilt on every run).
DROP TABLE IF EXISTS rej_business;
CREATE TABLE rej_business STORED AS ORC AS
SELECT source, reason, record_key, raw_record, source_file FROM rej_pharmacy
UNION ALL
SELECT source, reason, record_key, raw_record, source_file FROM rej_inventory
UNION ALL
SELECT source, reason, record_key, raw_record, source_file FROM rej_claims;

-- 2. Counts per reason (screenshot this).
SELECT source, reason, count(*) AS rows_rejected
FROM rej_business
GROUP BY source, reason
ORDER BY source, rows_rejected DESC;

-- 3. Reconciliation (screenshot this). balanced must be true on every line.
--    Raw counts use the same filters as the staging step: non-blank JSON lines, <item> lines, CSV rows.
DROP TABLE IF EXISTS etl_counts;
CREATE TABLE etl_counts STORED AS ORC AS
SELECT 'pharmacy' AS source, r.n AS raw_rows, c.n AS curated_rows, j.n AS rejected_rows,
       (r.n = c.n + j.n) AS balanced
FROM (SELECT count(*) n FROM raw_pharmacy_json WHERE trim(line) <> '') r
CROSS JOIN (SELECT count(*) n FROM cur_dispense) c
CROSS JOIN (SELECT count(*) n FROM rej_business WHERE source = 'pharmacy') j
UNION ALL
SELECT 'inventory', r.n, c.n, j.n, (r.n = c.n + j.n)
FROM (SELECT count(*) n FROM raw_inventory_xml WHERE line RLIKE '<item[ >]') r
CROSS JOIN (SELECT count(*) n FROM cur_inventory) c
CROSS JOIN (SELECT count(*) n FROM rej_business WHERE source = 'inventory') j
UNION ALL
SELECT 'claims', r.n, c.n, j.n, (r.n = c.n + j.n)
FROM (SELECT count(*) n FROM raw_claims_csv) r
CROSS JOIN (SELECT count(*) n FROM cur_claims) c
CROSS JOIN (SELECT count(*) n FROM rej_business WHERE source = 'claims') j;

SELECT * FROM etl_counts ORDER BY source;

-- 4. Evidence queries for the report screenshots.
SHOW PARTITIONS cur_dispense;
DESCRIBE FORMATTED cur_dispense;

-- both schema versions present and merged; epoch-ms converted
SELECT schema_ver, count(*) AS rows, min(dispensed_ts) AS first_ts, max(dispensed_ts) AS last_ts
FROM cur_dispense GROUP BY schema_ver;
SELECT dispense_id, mrn, drug_code, qty, dispensed_ts, schema_ver, drug_in_inventory
FROM cur_dispense WHERE year = 2025 AND month = 1 LIMIT 5;

-- inventory: dates converted, one row per record_id
SELECT record_id, drug_code, qty_on_hand, snapshot_date FROM cur_inventory WHERE year = 2024 AND month = 1 LIMIT 5;

-- claims: amounts cleaned, blanks kept as NULL and flagged, diagnosis code flag, resubmissions linked
SELECT claim_id, payer, diagnosis_code, dx_valid, claim_amount, amount_missing, status, original_claim_id, resub_link_ok
FROM cur_claims WHERE year = 2025 LIMIT 5;
SELECT count(*) AS claims, sum(CASE WHEN amount_missing THEN 1 ELSE 0 END) AS blank_amounts,
       sum(CASE WHEN NOT dx_valid OR dx_valid IS NULL THEN 1 ELSE 0 END) AS missing_or_invalid_dx,
       sum(CASE WHEN is_resubmission THEN 1 ELSE 0 END) AS resubmissions,
       sum(CASE WHEN NOT resub_link_ok THEN 1 ELSE 0 END) AS dangling_links
FROM cur_claims;
