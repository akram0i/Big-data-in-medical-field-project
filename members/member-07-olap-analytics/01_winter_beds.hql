-- P1: Grain = admission month x department; patient-days are an interval overlap.
-- The ROLLUP includes month subtotals and a grand total. OVERFLOW is not a bed.
USE ahd_member7;
WITH clean AS (
  SELECT * FROM (
    SELECT e.*, row_number() OVER (PARTITION BY encounter_id ORDER BY admit_ts) rn
    FROM encounters e WHERE encounter_type = 'IP' AND admit_ts IS NOT NULL
  ) x WHERE rn = 1
), monthly AS (
  SELECT m.month_key, e.department,
    sum(CASE WHEN substr(e.admit_ts,1,7) = m.month_key THEN 1 ELSE 0 END) admissions,
    sum(CASE WHEN substr(e.admit_ts,1,7) = m.month_key
                  AND e.bed_id = 'OVERFLOW' THEN 1 ELSE 0 END) overflow_admissions,
    sum(CASE WHEN e.bed_id LIKE 'W%'
        THEN greatest(0, datediff(least(to_date(coalesce(e.discharge_ts,
                                                       date_add(to_date(e.admit_ts),1))),
                                         to_date(m.next_date)),
                                  greatest(to_date(e.admit_ts), to_date(m.start_date))))
        ELSE 0 END) ward_bed_days
  FROM months m JOIN clean e
    ON to_date(e.admit_ts) < to_date(m.next_date)
   AND to_date(coalesce(e.discharge_ts, date_add(to_date(e.admit_ts),1))) >= to_date(m.start_date)
  GROUP BY m.month_key, e.department
)
SELECT month_key, department, grouping__id AS grouping_id,
       sum(admissions) AS admissions, sum(overflow_admissions) AS overflow_admissions,
       sum(ward_bed_days) AS ward_bed_days
FROM monthly
GROUP BY month_key, department WITH ROLLUP
ORDER BY month_key, department;
