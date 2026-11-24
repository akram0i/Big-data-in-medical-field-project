-- P7: Deduplicated historical vitals, clock-corrected during landing, join events.
-- Bucket 4=180-240 min before; bucket 1=0-60 min before event.
USE ahd_member7;
DROP TABLE IF EXISTS icu_hourly_summary;
CREATE TABLE icu_hourly_summary STORED AS ORC AS
WITH unique_vitals AS (
  SELECT * FROM (
    SELECT v.*, row_number() OVER (PARTITION BY bed_id,mrn,vital_ts ORDER BY vital_ts) rn
    FROM vitals v) x WHERE rn=1
), before_event AS (
  SELECT e.event_id,e.event_type,
         cast(ceil((unix_timestamp(e.event_ts)-unix_timestamp(v.vital_ts))/3600.0) AS int) hour_before,
         v.hr,v.spo2,v.rr,v.sbp
  FROM events e JOIN unique_vitals v ON e.bed_id=v.bed_id AND e.mrn=v.mrn
  WHERE unix_timestamp(v.vital_ts) >= unix_timestamp(e.event_ts)-14400
    AND unix_timestamp(v.vital_ts) < unix_timestamp(e.event_ts)
), hourly AS (
  SELECT hour_before, count(DISTINCT event_id) matched_events,
         count(*) readings,
         round(avg(CASE WHEN hr BETWEEN 30 AND 250 THEN hr END),2) mean_hr,
         round(avg(CASE WHEN spo2 BETWEEN 50 AND 100 THEN spo2 END),2) mean_spo2,
         round(avg(CASE WHEN rr BETWEEN 5 AND 80 THEN rr END),2) mean_rr,
         round(avg(CASE WHEN sbp BETWEEN 50 AND 250 THEN sbp END),2) mean_sbp
  FROM before_event GROUP BY hour_before
)
SELECT hour_before, matched_events, readings, mean_hr, mean_spo2, mean_rr, mean_sbp
FROM hourly;

SELECT hour_before, matched_events, readings, mean_hr, mean_spo2, mean_rr, mean_sbp,
       round(avg(mean_hr) OVER (ORDER BY hour_before DESC
         ROWS BETWEEN 1 PRECEDING AND CURRENT ROW),2) moving_two_hour_hr
FROM icu_hourly_summary ORDER BY hour_before DESC;
