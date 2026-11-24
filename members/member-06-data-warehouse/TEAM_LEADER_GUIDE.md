# Member 6 (warehouse): guide for the team leader

## What is in this folder

| Item | What it is |
|---|---|
| `Member6_Warehouse_Report.docx` | My full section: design, diagrams, build evidence (screenshots S1–S9), results, section iv, slides, lessons learned |
| `Member6_Section_iv_Slides.pptx` | The 2 slides for section iv (they are also in the report as Figures 16–17) |
| `code/member6_star_schema.hql` | Builds the warehouse (database `dw`) from the curated tables, then runs the check queries |
| `code/member5_patched/` | A copy of Member 5's ETL with the columns the warehouse needs added (`00`–`03`), plus `05_member6_views.hql`, which maps `ahd.cur_*` to the `curated.*` names my script reads |
| `code/member4/` | Member 4's `ahd_clinical_etl.hql`, their raw-table DDL (`m4_raw_tables.hql`) and `m4_settings.hql` (memory and block-size settings for the full data) |
| `code/06_member4_views.hql` | Points `curated.*` at Member 4's tables (`default.curated_*`, `default.mrn_map`) |
| `code/build_standin.py` | Independent Python check of the expected results |
| `code/m6_check_*.hql` | The check queries used for the screenshots |
| `screenshots/`, `diagrams/` | All images used in the report |
| `MEMBER6_RUN_GUIDE.md` | Detailed run notes and troubleshooting |

## Status: complete

- All curated tables are the group's own:
  - **clinical**: Member 4's `ahd_clinical_etl.hql`
  - **business**: Member 5's ETL. The only change is that I kept a few raw columns their scripts dropped: `txn_type`, `store`, `status`, `delay_minutes`, `substituted_for`, `denial_code`, `paid_amount`, `paid_date`.
- The warehouse was rebuilt on these tables over the full dataset. All screenshots and numbers in the report come from that run, and every check passed.
- Problem 4 and the row counts are identical to my earlier test build. The only change is that readmissions after non-heart-failure stays went from 8.7% to 8.8%, because Member 4's de-duplication merges slightly more patients.

## How to reproduce the whole run on a VM (about 1.5 hours, mostly waiting)

The raw files must be in HDFS:
- `/datalake/raw/ehr_cerner/{patients,encounters,diagnoses}/<name>.csv`
- `/datalake/raw/billing_oracle/claims.csv`
- `/datalake/raw/erp_oracle/` and `/datalake/raw/pharmacy_api/`

Start HiveServer2 with `nohup ./hiveserver2 &`. A plain `&` lets the terminal pause it, and the run hangs.

```bash
B="beeline -u jdbc:hive2://localhost:10000 -n bigdata"
# Member 4 (clinical). The settings file adds the memory and block-size fixes the full data needs.
$B -f code/member4/m4_raw_tables.hql
$B -i code/member4/m4_settings.hql -f code/member4/ahd_clinical_etl.hql
# Member 5 (business), patched copy
for f in 00_setup 01_inventory 02_pharmacy 03_claims; do
  $B --hivevar RAW=/datalake/raw --hivevar CURATED=/datalake/curated -f code/member5_patched/$f.hql; done
$B -f code/member5_patched/05_member6_views.hql
# Point curated.* at Member 4's tables, then build the warehouse (about 25 min)
$B -f code/06_member4_views.hql
$B -f code/member6_star_schema.hql > build.log 2>&1; grep -c '^Error' build.log   # must print 0
```

Expected results are in report section 5.3. The screenshot commands are in `MEMBER6_RUN_GUIDE.md` section 4.

If you edit the report, edit the docx directly. It was hand-edited after it was generated.
