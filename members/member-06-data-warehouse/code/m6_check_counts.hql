USE dw;
-- Row counts: each fact must equal its curated source (LEFT JOINs drop nothing)
SELECT 'curated.encounters', COUNT(*) FROM curated.encounters UNION ALL
SELECT 'fact_encounter', COUNT(*) FROM fact_encounter UNION ALL
SELECT 'curated.claims', COUNT(*) FROM curated.claims UNION ALL
SELECT 'fact_claim', COUNT(*) FROM fact_claim UNION ALL
SELECT 'curated.dispense', COUNT(*) FROM curated.dispense UNION ALL
SELECT 'fact_dispense', COUNT(*) FROM fact_dispense UNION ALL
SELECT 'curated.inventory', COUNT(*) FROM curated.inventory UNION ALL
SELECT 'fact_inventory_txn', COUNT(*) FROM fact_inventory_txn;
