-- P8: Linked feedback and first claim per encounter; complaint themes by denial.
USE ahd_member7;
WITH e AS (SELECT DISTINCT encounter_id FROM encounters),
first_claim AS (
  SELECT * FROM (
    SELECT c.*, row_number() OVER (PARTITION BY encounter_id ORDER BY submitted_ts,claim_id) rn
    FROM claims c WHERE resubmission_of IS NULL AND coalesce(denial_code,'') <> 'DUP-004'
  ) x WHERE rn=1
), linked AS (
  SELECT substr(f.submitted_ts,1,4) feedback_year,
         CASE WHEN c.status='DENIED' THEN 'denied' ELSE 'not_denied' END claim_outcome,
         CASE WHEN lower(f.comment) RLIKE 'bill|insur|claim|payment|فاتورة|تأمين'
              THEN 1 ELSE 0 END billing_complaint,
         f.rating
  FROM feedback f JOIN e ON f.encounter_id=e.encounter_id
  JOIN first_claim c ON e.encounter_id=c.encounter_id
), agg AS (
  SELECT feedback_year,claim_outcome,grouping__id AS grouping_id,
         count(*) linked_feedback,sum(billing_complaint) billing_complaints,
         round(avg(cast(rating AS double)),2) mean_rating
  FROM linked GROUP BY feedback_year,claim_outcome
  GROUPING SETS ((feedback_year,claim_outcome),(claim_outcome),())
)
SELECT *,round(100.0*billing_complaints/linked_feedback,2) billing_complaint_pct
FROM agg ORDER BY grouping_id,feedback_year,claim_outcome;
