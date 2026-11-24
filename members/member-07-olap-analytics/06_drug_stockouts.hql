-- P6: Original requested drug, stockout status, and preceding 7-day ERP receipts.
-- Inventory Qty denotes a transaction quantity; never treat it as stock balance.
USE ahd_member7;
WITH affected AS (
  SELECT d.dispense_id, coalesce(d.substituted_for,d.drug_code) requested_drug,
         substr(d.dispensed_ts,1,7) month_key, to_date(d.dispensed_ts) event_day,
         d.status
  FROM dispenses d WHERE d.status IN ('DELAYED_STOCKOUT','SUBSTITUTED')
), receipt_check AS (
  SELECT a.dispense_id,a.requested_drug,a.month_key,a.event_day,a.status,
         count(DISTINCT i.record_id) recent_receipts
  FROM affected a LEFT JOIN inventory i
    ON a.requested_drug=i.drug_code AND i.txn_type='RECEIPT' AND i.qty > 0
   AND to_date(i.txn_ts) BETWEEN date_sub(a.event_day,7) AND a.event_day
  GROUP BY a.dispense_id,a.requested_drug,a.month_key,a.event_day,a.status
), monthly AS (
  SELECT requested_drug, month_key, count(*) affected_dispenses,
         sum(CASE WHEN status='DELAYED_STOCKOUT' THEN 1 ELSE 0 END) delayed,
         sum(CASE WHEN status='SUBSTITUTED' THEN 1 ELSE 0 END) substituted,
         sum(CASE WHEN recent_receipts=0 THEN 1 ELSE 0 END) no_recent_receipt
  FROM receipt_check GROUP BY requested_drug,month_key
)
SELECT *, sum(affected_dispenses) OVER (PARTITION BY requested_drug ORDER BY month_key
  ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) running_affected
FROM monthly ORDER BY requested_drug,month_key;
