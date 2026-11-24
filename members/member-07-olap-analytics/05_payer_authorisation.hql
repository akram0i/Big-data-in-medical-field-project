-- P5: Payer x department x year CUBE, with focused ORTH/BARI day-case/IP cohort.
USE ahd_member7;
WITH base AS (
  SELECT c.claim_id, c.payer, e.department, substr(c.submitted_ts,1,4) claim_year,
         c.status, c.denial_code
  FROM claims c JOIN encounters e ON c.encounter_id = e.encounter_id
  WHERE c.resubmission_of IS NULL AND coalesce(c.denial_code,'') <> 'DUP-004'
    AND e.encounter_type IN ('IP','DAY')
), cube_data AS (
  SELECT payer, department, claim_year, grouping__id AS grouping_id,
         count(DISTINCT claim_id) first_claims,
         count(DISTINCT CASE WHEN status='DENIED' THEN claim_id END) denied,
         count(DISTINCT CASE WHEN denial_code='AUTH-002' THEN claim_id END) auth002_denials
  FROM base GROUP BY payer, department, claim_year WITH CUBE
)
SELECT *, round(100.0*denied/first_claims,2) denial_pct,
          round(100.0*auth002_denials/first_claims,2) auth002_pct
FROM cube_data ORDER BY grouping_id,payer,department,claim_year;
