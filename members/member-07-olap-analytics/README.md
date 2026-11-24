# Member 7 submission files

This folder contains the Member 7 contribution for the ISIT312 American Hospital Dubai **synthetic** data lake project. `Member7_Report.docx` is the insertable report section; `Member7_Report.md` is its editable source. The eight numbered `.hql` files implement Problems 1–8, with `00_tables.hql` defining the isolated Hive source tables. `charts/` contains six full-run figures. `results_sample/` and `results_full/` contain independent validation CSVs. `evidence/full/` contains actual Hive execution logs. See `evidence/STATUS.md` for what ran and its limits.

The final audit used the supplied full dataset in `byh5kn.zip`; its manifest matches the README counts exactly. `prepare_hive.py` creates a reproducible Member 7 landing layer directly from those source files and leaves the raw data untouched. The updated Member 6 package resolves the earlier clinical integration mismatch: its `06_member4_views.hql` reads Member 4's `default.curated_*` tables and aliases `mrn_map(std_mrn, master_mrn)` to the warehouse's `mrn/canonical_mrn` interface. The isolated Member 7 run remains a separate reproducible evidence path rather than a claim that these eight files ran unchanged on the integrated warehouse.

## Reproduce on macOS with Docker

From this folder, with the kit sample and full archive extracted and Docker Desktop running:

```sh
./run_member7.sh /path/to/AHD_synthetic_kit/sample_2pct sample
./run_member7.sh /path/to/ahd_data full
```

`run_member7.sh` writes normalized stage files under the workspace `work/`, starts a separate Hive 4 container, executes the setup and all eight HQL files, then retains the container for screenshots. Logs are saved under `evidence/sample/` or `evidence/full/`. The script checks Beeline text for errors because Beeline can return exit code 0 after a failed SQL statement.

To reproduce the independent numerical check and charts after creating stage files, install the small dependencies in `requirements.txt`, then run:

```sh
python3 validate_results.py --stage ../../work/member7_full_stage --out results_full
python3 make_charts.py --results results_full --out charts
```

The supplied full dataset is about 1.9 GB raw, and normalized stage files add about 0.6 GB. Hive ran against local files in Docker; this is not a claim of executing on the group's course VM, HDFS, or the integrated Member 6 star schema.

## Genuine screenshot evidence from this Mac

The three required captures are complete and stored in `evidence/screenshots/`. They show the actual source file, a live Hive/Tez full-data run, and its four-row result. They are embedded in `Member7_Report.docx`. The commands below are retained only so the evidence can be reproduced if required.

The audited full-run container is named `member7-hive-actual`. Use the commands below before stopping Docker Desktop. Open two Terminal windows. In the first, change into this folder and capture the code displayed there:

```sh
cd "/Users/akramkamhawi/Documents/Codex/2026-11-23/referenced-chatgpt-conversation-this-is-an/outputs/member7"
nl -ba 07_icu_deterioration.hql | sed -n '1,32p'
screencapture -i evidence/screenshots/member7_01_code.png
```

In the first Terminal, rerun the full ICU query:

```sh
docker exec member7-hive-actual /opt/hive/bin/beeline -u jdbc:hive2://localhost:10000/default -n hive --showHeader=false --outputformat=tsv2 -f /data/hql/07_icu_deterioration.hql
```

While it shows `RUNNING` and `VERTICES` progress, select that Terminal window from the second Terminal using this exact command:

```sh
screencapture -i "/Users/akramkamhawi/Documents/Codex/2026-11-23/referenced-chatgpt-conversation-this-is-an/outputs/member7/evidence/screenshots/member7_02_running.png"
```

When the first Terminal shows four data rows and `4 rows selected`, capture it from the second Terminal:

```sh
screencapture -i "/Users/akramkamhawi/Documents/Codex/2026-11-23/referenced-chatgpt-conversation-this-is-an/outputs/member7/evidence/screenshots/member7_03_output.png"
```

These images must show the actual computer screen. Do not replace them with the CSVs, charts, copied text, or staged illustrations. After they are captured, insert them into the report at the screenshot placeholder paragraph with captions identifying the full synthetic run and the isolated Docker Hive environment.
