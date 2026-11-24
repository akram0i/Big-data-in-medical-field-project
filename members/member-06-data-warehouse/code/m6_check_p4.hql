USE dw;
-- Problem 4 straight from the star: denial rate of first submissions by coding status
SELECT dg.coding_status, SUM(f.claim_count) AS claims,
       ROUND(AVG(f.denied_flag), 3) AS denial_rate
FROM fact_claim f JOIN dim_diagnosis dg ON f.diagnosis_key = dg.diagnosis_key
WHERE f.first_submission_flag = 1
GROUP BY dg.coding_status;
