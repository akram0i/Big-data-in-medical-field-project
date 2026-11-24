#!/usr/bin/env bash
# Member 2 - run the three MapReduce pipelines on YARN, then show the output files.
# Usage:  ./run_member2.sh            (all jobs)
#         ./run_member2.sh hl7 | abnormal | feedback | seasons
# Paths follow the brief: raw zone in /datalake/raw, results in /datalake/curated.
set -e
cd "$(dirname "$0")"

RAW=${RAW:-/datalake/raw}        # override: RAW=/datalake/sample_raw ./run_member2.sh
CUR=${CUR:-/datalake/curated}
JAR=ahd-mr.jar
STEP=${1:-all}

if [[ $STEP == all || $STEP == hl7 ]]; then
  echo "=== Job 1: HL7 -> lab_results (map-only)"
  hadoop fs -rm -r -f $CUR/lab_results
  hadoop jar $JAR ahd.mr.Hl7ParserDriver $RAW/lis_hl7 $CUR/lab_results
  hadoop fs -ls $CUR/lab_results | head -8
  hadoop fs -cat $CUR/lab_results/part-m-00000 | head -5
  hadoop fs -cat $CUR/lab_results/part-m-* | grep GLU_MMOL_CONVERTED | head -2
fi

if [[ $STEP == all || $STEP == abnormal ]]; then
  echo "=== Job 2: abnormal results per test (Combiner + PanelPartitioner, 7 reducers)"
  hadoop fs -rm -r -f $CUR/lab_abnormal_counts
  hadoop jar $JAR ahd.mr.AbnormalResultsDriver $CUR/lab_results $CUR/lab_abnormal_counts
  hadoop fs -ls $CUR/lab_abnormal_counts
  for i in 0 1 2 3 4 5 6; do
    echo "--- part-r-0000$i"; hadoop fs -cat $CUR/lab_abnormal_counts/part-r-0000$i
  done
fi

if [[ $STEP == all || $STEP == feedback ]]; then
  echo "=== Job 3: complaint word count + ranking (LanguagePartitioner, 2 reducers)"
  hadoop fs -rm -r -f $CUR/feedback_words
  hadoop jar $JAR ahd.mr.FeedbackWordCountDriver $RAW/feedback $CUR/feedback_words
  hadoop fs -ls $CUR/feedback_words/counts $CUR/feedback_words/ranked
  echo "--- English ranking (part-r-00000)"; hadoop fs -cat $CUR/feedback_words/ranked/part-r-00000 | head -25
  echo "--- Arabic ranking (part-r-00001)";  hadoop fs -cat $CUR/feedback_words/ranked/part-r-00001
fi

if [[ $STEP == all || $STEP == seasons ]]; then
  echo "=== Job 3 again: winter (Jan-Feb 2025) vs summer (Jul-Aug 2025) complaints"
  hadoop fs -rm -r -f $CUR/feedback_words_winter25 $CUR/feedback_words_summer25
  # -D options must come BEFORE the input/output paths (ToolRunner reads them).
  hadoop jar $JAR ahd.mr.FeedbackWordCountDriver -D feedback.from=2025-01-01 -D feedback.to=2025-02-28 \
         $RAW/feedback $CUR/feedback_words_winter25
  hadoop jar $JAR ahd.mr.FeedbackWordCountDriver -D feedback.from=2025-07-01 -D feedback.to=2025-08-31 \
         $RAW/feedback $CUR/feedback_words_summer25
  for p in winter25 summer25; do
    echo "--- $p: ED-wait words"
    hadoop fs -cat $CUR/feedback_words_$p/counts/part-r-* | grep -wE "emergency|packed|الطوارئ"
  done
fi
