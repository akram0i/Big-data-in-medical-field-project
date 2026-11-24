-- Member 6 - 05_member6_views.hql : expose Member 5's ahd.cur_* tables under the names
-- member6_star_schema.hql reads (curated.claims / dispense / inventory). Views only, no data copied.
-- Run after run_member5.sh (needs the patched 01-03 scripts in this folder).

CREATE DATABASE IF NOT EXISTS curated;

DROP VIEW IF EXISTS curated.claims;
CREATE VIEW curated.claims AS
SELECT claim_id, encounter_id, mrn, payer, submitted_date, claim_amount AS total_amount, status,
       denial_code, denial_reason, paid_amount, paid_date, resubmission_of
FROM ahd.cur_claims;

DROP VIEW IF EXISTS curated.dispense;
CREATE VIEW curated.dispense AS
SELECT dispense_id, mrn, encounter_id, drug_code, drug_name, qty, dispensed_ts AS dispensed_at,
       status, delay_minutes, substituted_for
FROM ahd.cur_dispense;

-- one row = one <Txn> movement; Member 5 named the Qty field qty_on_hand
DROP VIEW IF EXISTS curated.inventory;
CREATE VIEW curated.inventory AS
SELECT record_id AS txn_id, drug_code AS item_code, drug_name AS item_name, txn_type,
       qty_on_hand AS qty, unit_cost, store, snapshot_date AS txn_ts
FROM ahd.cur_inventory;

SELECT 'claims', COUNT(*) FROM curated.claims UNION ALL
SELECT 'dispense', COUNT(*) FROM curated.dispense UNION ALL
SELECT 'inventory', COUNT(*) FROM curated.inventory;
