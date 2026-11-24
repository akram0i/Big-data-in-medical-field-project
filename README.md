# ISIT312 American Hospital Dubai Synthetic Data Lake

This repository contains the eight-member group project for ISIT312 Big Data Management. The project designs and demonstrates a Hadoop data lake modelled on American Hospital Dubai systems, using synthetic data only. It covers ingestion, Java MapReduce, Hive ETL, real-time ICU processing, a dimensional warehouse, OLAP analysis, and HBase serving tables.

No real hospital, patient, employee, insurer, or financial data is included.

## Repository guide

| Folder | Contribution | Main contents |
| --- | --- | --- |
| [`member-01-platform-ingestion`](members/member-01-platform-ingestion/) | Hadoop platform and HDFS ingestion | Implementation report and VM evidence |
| [`member-02-mapreduce`](members/member-02-mapreduce/) | MapReduce for HL7 labs and feedback text | Report, Java source, Hive DDL, build and run scripts |
| [`member-03-realtime-icu`](members/member-03-realtime-icu/) | Real-time and ICU processing | Batch-versus-streaming analysis and implementation report |
| [`member-04-hive-clinical-etl`](members/member-04-hive-clinical-etl/) | Hive ETL for clinical data | Report, HQL, execution logs, and supporting command notes |
| [`member-05-business-etl`](members/member-05-business-etl/) | Hive ETL for business data and BPMN | Report, HQL, logs, BPMN diagrams, and build tools |
| [`member-06-data-warehouse`](members/member-06-data-warehouse/) | Dimensional warehouse design | Updated report, star-schema HQL, integration adapters, diagrams, screenshots, and slides |
| [`member-07-olap-analytics`](members/member-07-olap-analytics/) | OLAP analytics and business intelligence | Eight HQL reports, OLAP algebra, full-data results, charts, genuine Hive evidence, and final report |
| [`member-08-hbase-current-state`](members/member-08-hbase-current-state/) | HBase serving layer and current-state study | HBase design, commands, and report section |

The original project brief and university specifications are under [`docs/requirements`](docs/requirements/). The synthetic data generator, schema documentation, answer key, and sample manifest are under [`data/synthetic-kit`](data/synthetic-kit/).

## Architecture

The proposed data lake has three HDFS zones:

1. `raw` preserves source exports in their original formats.
2. `curated` stores cleaned, linked, and quality-controlled tables.
3. `serving` exposes the Hive warehouse for analytics and HBase tables for fast current-state lookups.

The batch lane uses HDFS, Java MapReduce, Hive, and a dimensional warehouse. The real-time lane replays ICU monitor readings, maintains the latest readings in HBase, and evaluates sustained warning conditions.

## Data and reproducibility

The supplied full synthetic dataset represents 2024–2025 and contains about 12.6 million rows across CSV, JSONL, XML, and HL7 sources. It is about 1.9 GB uncompressed, so the generated raw files are intentionally not committed to GitHub. They can be regenerated with:

```bash
python3 data/synthetic-kit/generate_ahd.py --out ahd_data
```

For a smaller development dataset:

```bash
python3 data/synthetic-kit/generate_ahd.py --out ahd_data --scale 0.02
```

See [`data/README.md`](data/README.md) for the committed data artifacts and full-run counts.

## Execution evidence

The member folders preserve the submitted reports, scripts, screenshots, and logs. Evidence was produced in more than one environment, so this repository does not claim that every component ran end to end in a single cluster.

- Members 1–6 document work on the course Hadoop/Hive VM and their supplied execution evidence.
- The updated Member 6 adapter maps Member 4's `default.curated_*` tables and `mrn_map(std_mrn, master_mrn)` into the warehouse interface.
- Member 7 was independently rerun on the supplied full dataset in Apache Hive 4.0.1 in Docker. All eight HQL files completed, and the report distinguishes sample checks, independent validation, and genuine Hive output.

## Important academic note

This is a university group submission. The repository is public for assessment and review; no reuse licence is granted. Claims and screenshots should be read with the limitations stated in each member's report.
