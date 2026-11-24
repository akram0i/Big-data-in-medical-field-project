USE dw;
-- Problem 3: 30-day readmission after inpatient stays, heart failure (I50.9) vs all other primary diagnoses
SELECT dg.icd10_code = 'I50.9' AS heart_failure, ROUND(AVG(f.readmit_30d_flag), 3) AS readmit_30d_rate,
       COUNT(*) AS ip_stays
FROM fact_encounter f JOIN dim_diagnosis dg ON f.primary_diagnosis_key = dg.diagnosis_key
WHERE f.encounter_type = 'IP'
GROUP BY dg.icd10_code = 'I50.9';
