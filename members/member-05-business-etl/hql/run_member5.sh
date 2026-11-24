#!/bin/bash
# Member 5 - runs the whole business-data ETL in dependency order and times each step.
# Usage:  ./run_member5.sh [RAW_PATH] [CURATED_PATH]   defaults /datalake/raw /datalake/curated
# Logs go to ./logs/ (keep them: the report needs the commands and the output).
set -u
RAW=${1:-/datalake/raw}
CURATED=${2:-/datalake/curated}
HIVE=${HIVE:-hive}
H=${HADOOP_HOME:-/usr/share/hadoop-2.7.3}/bin/hadoop
cd "$(dirname "$0")"; mkdir -p logs

# control task 1: raw files exist
for s in pharmacy_api erp_oracle billing_oracle; do
  $H fs -test -d "$RAW/$s" || { echo "MISSING raw folder $RAW/$s - ask Member 1"; exit 1; }
done

run() {   # run <script.hql>
  local t0=$(date +%s)
  echo "=== $1 ($(date +%T)) ==="
  $HIVE --hivevar RAW="$RAW" --hivevar CURATED="$CURATED" -f "$1" > "logs/${1%.hql}.log" 2>&1 \
    || { echo "FAILED: $1 - see logs/${1%.hql}.log"; tail -15 "logs/${1%.hql}.log"; exit 1; }
  echo "done in $(( $(date +%s) - t0 )) s"
}

run 00_setup.hql
run 01_inventory.hql       # reference table first
run 02_pharmacy.hql        # looks drug codes up in cur_inventory
run 03_claims.hql
run 04_reconcile.hql
echo; echo "Reconciliation:"; grep -E "pharmacy|inventory|claims" logs/04_reconcile.log | tail -8
