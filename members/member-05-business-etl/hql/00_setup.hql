-- Member 5 - 00_setup.hql
-- Session settings shared by every Member 5 script, and the database.
-- Run with:  hive --hivevar RAW=/datalake/raw -f 00_setup.hql   (run_member5.sh does this)

CREATE DATABASE IF NOT EXISTS ahd;
USE ahd;

-- dynamic partitions: curated tables are PARTITIONED BY (year, month)
SET hive.exec.dynamic.partition=true;
SET hive.exec.dynamic.partition.mode=nonstrict;
SET hive.exec.max.dynamic.partitions=2000;
SET hive.exec.max.dynamic.partitions.pernode=500;

-- curated tables are CLUSTERED BY (mrn) INTO 8 BUCKETS (same design as Member 4)
SET hive.enforce.bucketing=true;

-- read raw files whether they sit flat in /datalake/raw/<source>/ (hadoop fs -put)
-- or in dt=YYYY-MM-DD sub-folders (Member 1's DailyIngest)
SET mapreduce.input.fileinputformat.input.dir.recursive=true;
SET hive.mapred.supports.subdirectories=true;
