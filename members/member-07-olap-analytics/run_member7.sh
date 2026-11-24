#!/usr/bin/env bash
# Reproducible standalone Hive 4 execution on the supplied sample or full data.
set -euo pipefail
if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <source-data-root> <sample|full>" >&2
  exit 2
fi
source_root=$(cd "$1" && pwd)
label=$2
if [[ "$label" != sample && "$label" != full ]]; then
  echo "Second argument must be sample or full" >&2
  exit 2
fi
script_dir=$(cd "$(dirname "$0")" && pwd)
workspace=$(cd "$script_dir/../.." && pwd)
stage="$workspace/work/member7_${label}_stage"
logs="$script_dir/evidence/$label"
mkdir -p "$stage" "$logs"
python3 "$script_dir/prepare_hive.py" --input "$source_root" --out "$stage"
container="member7-hive-${label}-$(date +%s)"
docker run -d --name "$container" --rm \
  -e SERVICE_NAME=hiveserver2 -e DB_DRIVER=derby \
  -v "$stage:/data/stage:ro" -v "$script_dir:/data/hql:ro" \
  apache/hive:4.0.1 >/dev/null
echo "Hive container: $container"
ready=0
for attempt in $(seq 1 30); do
  if docker exec "$container" /opt/hive/bin/beeline \
      -u jdbc:hive2://localhost:10000/default -n hive \
      --silent=true --showHeader=false --outputformat=tsv2 \
      -e 'select 1;' >"$logs/connection.log" 2>&1 \
      && rg -q '^1$' "$logs/connection.log"; then
    ready=1; break
  fi
  sleep 5
done
if [[ $ready -ne 1 ]]; then
  echo "HiveServer2 did not become ready. See $logs/connection.log" >&2
  exit 1
fi
run_hql() {
  local name=$1
  docker exec "$container" /opt/hive/bin/beeline \
    -u jdbc:hive2://localhost:10000/default -n hive \
    --showHeader=false --outputformat=tsv2 \
    --hivevar ROOT=file:///data/stage \
    -f "/data/hql/$name.hql" >"$logs/$name.log" 2>&1
  if rg -q 'Error:|FAILED:' "$logs/$name.log"; then
    echo "Hive reported an error in $name; see $logs/$name.log" >&2
    exit 1
  fi
  echo "$name: $(rg -o '[0-9]+ rows selected' "$logs/$name.log" | tail -1)"
}
run_hql 00_tables
for name in 01_winter_beds 02_ed_crowding 03_heart_failure \
            04_coding_denials 05_payer_authorisation 06_drug_stockouts \
            07_icu_deterioration 08_billing_feedback; do
  run_hql "$name"
done
echo "Complete. Logs: $logs"
echo "Container remains available for genuine screenshots: $container"
