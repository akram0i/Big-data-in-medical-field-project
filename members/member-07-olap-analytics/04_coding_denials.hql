-- P4: First claims only; denial codes are outcomes, never diagnosis codes.
USE ahd_member7;
WITH first_claim AS (
  SELECT c.* FROM claims c
  WHERE c.resubmission_of IS NULL AND coalesce(c.denial_code,'') <> 'DUP-004'
), primary_dx AS (
  SELECT * FROM (
    SELECT d.*, row_number() OVER (PARTITION BY encounter_id ORDER BY seq) rn
    FROM diagnoses d WHERE dx_type = 'PRIMARY') x WHERE rn = 1
), classified AS (
  SELECT c.claim_id, c.status, c.denial_code,
         CASE WHEN d.encounter_id IS NULL OR d.dx_valid = 0 THEN 'missing_or_invalid'
              ELSE 'valid_primary' END coding_status
  FROM first_claim c JOIN encounters e ON c.encounter_id = e.encounter_id
  LEFT JOIN primary_dx d ON e.encounter_id = d.encounter_id
)
SELECT coding_status, count(DISTINCT claim_id) first_claims,
       count(DISTINCT CASE WHEN status = 'DENIED' THEN claim_id END) denied,
       round(100.0*count(DISTINCT CASE WHEN status='DENIED' THEN claim_id END)
                    /count(DISTINCT claim_id),2) denial_pct,
       count(DISTINCT CASE WHEN denial_code = 'DX-003' THEN claim_id END) dx003_denials
FROM classified GROUP BY coding_status ORDER BY coding_status;
