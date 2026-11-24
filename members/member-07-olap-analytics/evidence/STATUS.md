# Member 7 execution status

**Data:** supplied full synthetic dataset from `byh5kn.zip`. Its manifest matches the README counts: 780,371 encounters, 1,296,906 diagnoses, 735,391 claims, 1,011,013 dispenses, 99,299 inventory transactions, 92,593 feedback rows, 126 ICU events and 5,510,388 vital lines. The 2% kit was used for development. No real hospital data was used.

**Hive environment:** Apache Hive 4.0.1 in Docker on the user's Mac, with the normalized landing files mounted as `file:///data/stage`. Tez completed the full queries in the isolated `member7-hive-actual` container. This is a real Hive run, but it is not the course VM's HDFS/YARN or the integrated Member 6 star schema.

| HQL file | Full Hive result | Independent full-file check |
| --- | ---: | --- |
| `00_tables.hql` | 8 source counts | source manifest checked |
| `01_winter_beds.hql` | 265 rows | 24 monthly totals match |
| `02_ed_crowding.hql` | 27 rows | counts/rates match; Hive `percentile_approx` differs slightly from exact median |
| `03_heart_failure.hql` | 11 rows | cohort totals match |
| `04_coding_denials.hql` | 2 rows | all counts/rates match |
| `05_payer_authorisation.hql` | 231 rows | detailed payer/department/year cells match |
| `06_drug_stockouts.hql` | 3 rows | all counts match |
| `07_icu_deterioration.hql` | 4 final rows | four hourly means match; materialized summary fixes Hive's nested window binding |
| `08_billing_feedback.hql` | 7 rows | linked-outcome totals match |

The `.log` files in `full/` are direct Beeline output and include the SQL statements, Tez task progress, row counts, and result rows. None of the final full logs contain `Error:` or `FAILED:`. The smaller development-run logs are in `sample/`. The CSVs in `results_full/` are from the independent DuckDB check, not captured Hive output. The DuckDB and Hive results agree; Hive uses `percentile_approx` for the ED median, so that one measure is expected to differ slightly from the exact reference median.

**Team integration audit:** The updated Member 6 package repairs its clinical adapter. `06_member4_views.hql` now reads Member 4's actual `default.curated_patients`, `default.curated_encounters`, `default.curated_diagnoses`, and `default.mrn_map(std_mrn, master_mrn)` outputs, aliasing the MRN fields to `mrn/canonical_mrn`; its team guide records a successful full-data warehouse rebuild. Member 7's isolated source-preserving schema remains the executed evidence path, so this package does not claim that the eight HQL files ran unchanged against the integrated warehouse.

**Screenshots:** `screenshots/` contains three genuine captures from this Mac: `member7_01_code.png` shows the actual HQL source, `member7_02_running.png` shows the full Hive/Tez job running, and `member7_03_output.png` shows the same run with four output rows and `4 rows selected`. They are inserted into `Member7_Report.docx`.
