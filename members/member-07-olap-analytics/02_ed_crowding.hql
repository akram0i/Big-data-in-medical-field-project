-- P2: ED encounter month/year plus ward census from inpatient bed days.
USE ahd_member7;
WITH ip AS (
  SELECT * FROM (
    SELECT e.*, row_number() OVER (PARTITION BY encounter_id ORDER BY admit_ts) rn
    FROM encounters e WHERE encounter_type = 'IP' AND bed_id LIKE 'W%'
  ) x WHERE rn = 1
), census AS (
  SELECT m.month_key,
         sum(greatest(0, datediff(least(to_date(coalesce(e.discharge_ts,
                                                        date_add(to_date(e.admit_ts),1))),
                                         to_date(m.next_date)),
                                  greatest(to_date(e.admit_ts),to_date(m.start_date))))) bed_days,
         datediff(to_date(m.next_date),to_date(m.start_date)) * 228 capacity_days
  FROM months m JOIN ip e
    ON to_date(e.admit_ts) < to_date(m.next_date)
   AND to_date(coalesce(e.discharge_ts,date_add(to_date(e.admit_ts),1))) >= to_date(m.start_date)
  GROUP BY m.month_key, m.start_date, m.next_date
), ed_base AS (
  SELECT substr(admit_ts,1,4) year, substr(admit_ts,1,7) month_key,
         ed_wait_minutes, discharge_disposition
  FROM (SELECT e.*, row_number() OVER (PARTITION BY encounter_id ORDER BY admit_ts) rn
        FROM encounters e WHERE encounter_type = 'ED') x WHERE rn = 1
), ed_agg AS (
  SELECT year, month_key, grouping__id AS grouping_id,
         count(*) ed_visits, percentile_approx(cast(ed_wait_minutes AS double),0.5) median_wait_min,
         sum(CASE WHEN discharge_disposition = 'LEFT_WITHOUT_BEING_SEEN' THEN 1 ELSE 0 END) lwbs
  FROM ed_base GROUP BY year, month_key
  GROUPING SETS ((year,month_key),(year),())
)
SELECT a.*, round(100.0 * a.lwbs/a.ed_visits,2) lwbs_pct,
       c.bed_days, c.capacity_days,
       round(100.0*c.bed_days/c.capacity_days,2) ward_occupancy_pct
FROM ed_agg a LEFT JOIN census c ON a.month_key = c.month_key
ORDER BY a.year, a.month_key;
