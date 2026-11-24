# Member 2 — MapReduce pipelines for labs and text (ISIT312 AHD data lake)

All data is synthetic, modelled on AHD's systems.

## Contents
```
src/ahd/mr/
  Hl7ParserDriver.java          Job 1 driver (ToolRunner, map-only, "\n\n" record delimiter)
  Hl7ParserMapper.java          Job 1 mapper: HL7 -> lab_results CSV + data-quality counters
  NonSplittableTextInputFormat  one monthly HL7 file = one mapper (exact duplicate removal)
  AbnormalResultsDriver.java    Job 2 driver (Combiner, PanelPartitioner, 7 reducers)
  AbnormalResultsMapper.java    Job 2 mapper: (panel, test, H/L/N) -> 1
  PanelPartitioner.java         CBC=0 BMP=1 LIPID=2 HBA1C=3 TROP=4 CRP=5 LACT=6
  SumReducer.java               Combiner + Reducer for Jobs 2 and 3a
  FeedbackWordCountDriver.java  Job 3 driver: 3a word count -> 3b ranking (chained)
  FeedbackTokenMapper.java      CSV parse, complaint filter, normalise, stop words
  LanguagePartitioner.java      3a: English -> reducer 0, Arabic -> reducer 1
  RankMapper / RankReducer      3b: (count, word), decreasing sort, rank per language
  RankLanguagePartitioner.java  3b: language read from the value
  TextUtil.java                 CSV parser, Arabic normalisation, stop words
build.sh                        javac + jar  (screenshot this)
run_member2.sh                  runs all jobs on YARN and prints outputs
hive/member2_tables.hql         Hive external tables over the three outputs
```

## Run on the VM
```
cd ~/member2_mapreduce
./build.sh
./run_member2.sh            # or: ./run_member2.sh hl7 | abnormal | feedback | seasons
hive -f hive/member2_tables.hql
```
Inputs: `/datalake/raw/lis_hl7`, `/datalake/raw/feedback` (sub-folders such as dt=YYYY-MM-DD are read too).
Outputs: `/datalake/curated/lab_results`, `/lab_abnormal_counts`, `/feedback_words/{counts,ranked}`.

Options (put before the paths):
`-D feedback.max.rating=3`, `-D feedback.include.unrated=true`,
`-D feedback.from=2025-01-01 -D feedback.to=2025-02-28`, `-D rank.top.n=25`.

## Expected numbers (regenerated full dataset, seed 312; the zip's totals differ slightly)
| Counter | Full size |
| --- | --- |
| MESSAGES_READ | 976,644 |
| TRUNCATED_SKIPPED | 2,948 (0.30%) |
| DUPLICATE_SKIPPED | 7,732 (0.79%) |
| GLUCOSE_CONVERTED | 25,883 (9.9% of glucose) |
| FLAG_DERIVED | 56,970 (2.0%) |
| RESULT_BEFORE_ORDER | 2,953 messages |
| RESULTS_WRITTEN | 2,844,031 |
| Job 2 combine in → out | 2,844,031 → 984 |
| Job 3 complaints used | 33,880 |

Tested: compiled with `--release 8` (Java 8 compatible) against Hadoop 3 client jars and run in Hadoop
local mode on both the 2% sample and the full dataset.
