# Member 6: how to run the star schema on the VM and take the screenshots

There are two runs:
- **Test run, possible now.** Uses stand-in curated tables built from the 2% sample, so you don't have to wait for Members 4 and 5.
- **Final run.** Uses Members 4 and 5's real curated tables on the full data. These are the screenshots that go in the report.

Hive commands follow Lab 4 (beeline). Paths assume the VM user `bigdata`.

## 0. Copy the files to the VM

Through the shared folder (as in Lab 5), copy these into `~/m6/` on the VM:
- `member6_star_schema.hql`
- the folder `member6_test/` (contains `standin/*.tsv`, `load_standin.hql` and `expected_results.txt`)

```bash
mkdir -p ~/m6 && cp -r /media/sf_shared/m6/* ~/m6/   # adjust to where your shared folder is mounted
```

## 1. Start the services (Lab 4)

Start Hadoop as usual, then, in `$HIVE_HOME/bin`:

```bash
./hive --service metastore &
./hiveserver2 &
./beeline
!connect jdbc:hive2://localhost:10000
```

Check the Hive version: `SELECT version();` (Hive 2.1+), or `hive --version` in a terminal.
- **Hive 1.x:** uncomment `SET hive.enforce.bucketing=true;` near the top of `member6_star_schema.hql`.
- **Hive 2 or 3:** leave it commented. The setting no longer exists there and would cause an error.

## 2. Test run with the stand-in tables

Upload the stand-in files to HDFS (terminal):

```bash
cd ~/m6/member6_test
for t in patients mrn_map encounters diagnoses claims dispense inventory; do
  hadoop fs -mkdir -p /user/bigdata/m6_standin/$t
  hadoop fs -put -f standin/$t.tsv /user/bigdata/m6_standin/$t/
done
```

Make a copy of the build script that points at the test database:

```bash
sed 's/curated\./curated_test./g' ~/m6/member6_star_schema.hql > ~/m6/m6_test_run.hql
```

Then in beeline:

```
!record /home/bigdata/m6/test_run.log
!run /home/bigdata/m6/member6_test/load_standin.hql
!run /home/bigdata/m6/m6_test_run.hql
!record
```

`load_standin.hql` should print 15973 / 14996 / 23921 / 32911. The build runs about 30 Hive jobs, so expect it to take a while on the VM.

**Compare with `member6_test/expected_results.txt`.** The check queries at the end should match it exactly:

| Check | Expected (stand-in) |
|---|---|
| fact rows | 15973 / 14996 / 23921 / 32911, each equal to its source |
| missing / invalid primary dx | 479 / 86 |
| problem 4 denial rate | INVALID 0.564, MISSING 0.629, UNKNOWN 0.050, VALID 0.059 |

Also check problem 3:

```sql
SELECT dg.icd10_code = 'I50.9' AS hf, ROUND(AVG(f.readmit_30d_flag), 3) AS rate, COUNT(*) AS stays
FROM dw.fact_encounter f JOIN dw.dim_diagnosis dg ON f.primary_diagnosis_key = dg.diagnosis_key
WHERE f.encounter_type = 'IP' GROUP BY dg.icd10_code = 'I50.9';
-- expected on the stand-in: true 0.135 (37 stays), false 0.072
```

If a number differs, paste the output into Claude.

## 3. Final run (after Members 4 and 5 have loaded `curated` on the full data)

1. Check their table and column names match the contract at the top of `member6_star_schema.hql`. Run `SHOW TABLES IN curated;` and `DESCRIBE curated.encounters;`. If anything differs, edit the names in the script, not their tables.
2. In beeline: `!record /home/bigdata/m6/final_run.log`, then `!run /home/bigdata/m6/member6_star_schema.hql`.
3. Check the problem 4 result against `ANSWER_KEY.md` (about 53% vs 6%) and the HF readmission against it (about 19% vs 6%).
4. Fill the [brackets] in `Member6_Report_Section_iv.md` with the real numbers.

## 4. Screenshots for the report (from the final run)

The brief asks each builder for the command, the job running, and the output.

| # | What | How |
|---|---|---|
| S1 | The command | beeline showing `!run …member6_star_schema.hql` and the first statements running |
| S2 | Jobs running on YARN | http://localhost:8088 during the fact loads (the INSERT … fact_encounter job) |
| S3 | Tables built | `SHOW TABLES IN dw;` |
| S4 | Partitions + buckets | `SHOW PARTITIONS dw.fact_claim;` and `hadoop fs -ls /user/hive/warehouse/dw.db/fact_claim/year=2025/month=1` (8 bucket files) |
| S5 | Partition pruning | the `EXPLAIN EXTENDED` output: only the `year=2025/month=1` path is listed |
| S6 | Row-count check | first check query: each fact equals its curated source |
| S7 | Problem 4 from the star | the coding_status denial-rate query |
| S8 | Summary table | `SELECT * FROM dw.agg_daily_occupancy WHERE census_date LIKE '2025-01%' LIMIT 20;` |
| S9 | Problem 3 from the star | `m6_check_p3.hql` (heart failure I50.9 vs others, 30-day readmission) |

## 5. If something fails

| Error | Cause / fix |
|---|---|
| `ParseException … cannot recognize input near '<EOF>'` | beeline splits statements at every `;`, even inside a `--` comment at the end of a line. Never put `;` (or an unpaired `'`) in an inline comment. Whole-line comments are fine |
| A query hangs forever (e.g. at `Loading data to table … partition (year=null, month=null)`) and YARN shows no running job | HiveServer2 was started with `./hiveserver2 &` and the terminal has **stopped** it: the shell prints `[n]+ Stopped ./hiveserver2`. Start it with `nohup ./hiveserver2 > ~/hs2.log 2>&1 &` instead (same for the metastore), or give it its own terminal tab |
| `return code 2 from MapRedTask` at `fact_encounter` on the full data; container log says `OutOfMemoryError: GC overhead limit exceeded` | Hive turned a join into a map join that loads the 754k-row primary-dx table into each map task. The default task heap is too small. The `SET mapreduce.map.memory.mb=2048` / `java.opts=-Xmx1536m` lines at the top of the script fix it. (Container logs are in `$HADOOP_HOME/logs/userlogs/<application id>/`) |
| Fact INSERT fails, container log says `could only be replicated to 0 nodes instead of minReplication (=1)` although `df -h` shows GBs free | HDFS reserves a full block (128 MB) for every open file. Dynamic partitions keep about 25 files open per reducer, times several reducers, which is more than the VM's free space. `SET dfs.blocksize=33554432;` (32 MB) at the top of the script fixes it |
| `hive.enforce.bucketing does not exist` | Hive 2+ (the VM runs **Hive 2.1.1**): keep that SET line commented |
| `Invalid table alias or column reference` | a curated column has a different name: edit the script |
| `Dynamic partition strict mode requires…` | the two `SET hive.exec.dynamic.partition…` lines didn't run: run them, then the INSERT again |
| `Invalid function date_format` | Hive older than 1.2: replace `date_format(d,'EEEE')` with `from_unixtime(unix_timestamp(d,'yyyy-MM-dd'),'EEEE')` (same for `'MMMM'`) |
| `Another instance of Derby may have already booted` | see the ISIT312 VM notes: stale `metastore_db/*.lck` or spark-shell still running |
| One statement fails mid-file | fix it, then run from that statement onward. Every table is `DROP … IF EXISTS` + `CREATE`, so re-running is safe |
