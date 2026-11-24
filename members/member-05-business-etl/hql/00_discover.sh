#!/bin/bash
# Member 5 - step 0: look at the raw files BEFORE running the HQL.
# Prints what the HQL assumes (field names, XML tags, CSV header) so you can fix the few
# lines marked "-- VERIFY" in 01/02/03 and cross-check against README.md. Raw zone is only READ.
H=${HADOOP_HOME:-/usr/share/hadoop-2.7.3}/bin/hadoop
RAW=${1:-/datalake/raw}

first() { $H fs -ls -R "$RAW/$1" | awk '{print $NF}' | grep -E "$2" | head -1; }

echo "=== pharmacy_api: first line of a 2024 file (v1) and a 2025 file (v2) ==="
for yr in 2024 2025; do
  f=$(first pharmacy_api "dispense_${yr}-.*jsonl$"); echo "--- $f"
  $H fs -cat "$f" | head -2
done
echo; echo "=== pharmacy_api: distinct JSON key sets (first 2000 lines of each year) ==="
for yr in 2024 2025; do
  f=$(first pharmacy_api "dispense_${yr}-.*jsonl$")
  $H fs -cat "$f" | head -2000 | python3 -c '
import sys, json, collections
c = collections.Counter()
def keys(o, p=""):
    for k, v in o.items():
        if isinstance(v, dict): yield from keys(v, p + k + ".")
        else: yield p + k
for l in sys.stdin:
    try: c[",".join(sorted(keys(json.loads(l))))] += 1
    except Exception: c["<not json>"] += 1
for k, n in c.most_common(5): print(n, k)'
done

echo; echo "=== erp_oracle: first 12 lines of one inventory file ==="
f=$(first erp_oracle "inventory_.*xml$"); echo "--- $f"; $H fs -cat "$f" | head -12

echo; echo "=== billing_oracle: header and 3 rows of claims.csv ==="
f=$(first billing_oracle "claims.csv$"); echo "--- $f"; $H fs -cat "$f" | head -4

echo; echo "=== how the raw files are laid out (flat put or dt= folders) ==="
$H fs -ls -R "$RAW/pharmacy_api" | head -5
