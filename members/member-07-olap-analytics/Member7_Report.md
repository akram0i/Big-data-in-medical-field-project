# Member 7 OLAP Analytics and Business Intelligence

**ISIT312 American Hospital Dubai synthetic data lake project**  
**Contribution for report Section v, solution implementation, and Aspect 3 lessons learned**  
**Data status:** all records and results below are synthetic. They are modelled on American Hospital Dubai systems and are not measurements of the hospital's actual operations.

## Scope and provenance

I implemented eight business reports, one per problem on page 11 of the group brief. The 2% kit was used for development, and the supplied 182 MB full-data archive `byh5kn.zip` was used for the final run. Its manifest matches the README: 780,371 encounters, 1,296,906 diagnoses, 735,391 claims, 1,011,013 dispensings, 99,299 inventory transactions, 92,593 feedback records, 126 ICU events, and 5,510,388 vital lines. All final results, charts and Hive logs below refer to those supplied files.

The final team-artifact audit included Member 6's updated hand-off. Its repaired `06_member4_views.hql` now reads Member 4's actual `default.curated_patients`, `default.curated_encounters`, `default.curated_diagnoses`, and `mrn_map(std_mrn, master_mrn)` outputs, aliasing the MRN fields to the names expected by the warehouse. Member 6's team guide also records a successful full-data rebuild using those tables. Member 5's v5 report records a completed full-data ETL, while Member 6's patched copy retains the stockout and denial fields needed by OLAP. A billing denial code must still not be treated as a clinical diagnosis, so Problem 4 joins claims to the clinical primary diagnosis by `encounter_id`. I retained the isolated `ahd_member7` reporting schema over source-preserving normalized landing files as a separately reproducible evidence path; it does not replace the team's curated or warehouse layers.

## Implementation and analytical grains

`prepare_hive.py` reads the actual source CSV, JSONL, and XML files, normalizes department variants and dates, joins no facts, and writes headerless tab-separated files. It handles both pharmacy JSON versions, converts epoch milliseconds to Dubai time, and corrects the documented seven-minute clock drift on ICU-07 and ICU-15. It marks invalid or missing primary diagnoses without treating claim denial codes as diagnoses. The nine external Hive tables in `00_tables.hql` expose those files. The raw kit remains untouched.

| Problem | Report grain | Measures | Dimensions and source join |
| --- | --- | --- | --- |
| 1 Winter beds | admission month × department | inpatient admissions, overflow admissions, ward bed days | encounters × calendar months |
| 2 ED crowding | ED month, with year and all-year totals | visits, median wait, left-without-being-seen rate, ward occupancy | ED encounters × inpatient monthly census |
| 3 Heart-failure readmission | primary diagnosis cohort × department | discharges, 30-day readmissions, rate | inpatient encounters × primary diagnoses |
| 4 Coding denials | coding validity cohort | first claims, denied claims, denial rate, DX-003 count | claims × encounters × primary diagnoses |
| 5 Prior authorisation | payer × department × claim year | first claims, denied claims, AUTH-002 denials and rates | claims × inpatient/day-case encounters |
| 6 Drug stockouts | requested drug × dispense month | delayed, substituted, affected dispenses, no-recent-receipt count | dispenses × ERP receipt transactions by drug and preceding seven days |
| 7 ICU deterioration | hour before recorded event | event count, readings, mean HR, SpO₂, respiratory rate and systolic BP | corrected vitals × ICU events by bed, MRN and time window |
| 8 Billing feedback | feedback year × first-claim outcome | linked feedback, billing complaint count/rate, mean rating | feedback × encounters × first claim |

The HQL uses `WITH ROLLUP` for month and department in Problem 1, `GROUPING SETS` for ED and feedback summaries, `WITH CUBE` for payer × department × year, and window functions for department `RANK`, a drug running total, and an ICU moving average. `GROUPING__ID` labels subtotal rows. Measures are calculated after de-duplicating encounter IDs; first claims exclude resubmissions and `DUP-004` duplicate submissions. For the occupancy denominator, a ward has 228 physical beds and an open inpatient stay is assigned one day rather than projected indefinitely. Census is estimated from date-overlap bed days, not observed midnight bed checks.

The following excerpt is from the executed coding query; the complete query is in `04_coding_denials.hql`:

```sql
FROM first_claim c
JOIN encounters e ON c.encounter_id = e.encounter_id
LEFT JOIN primary_dx d ON e.encounter_id = d.encounter_id
-- missing/invalid is based on primary diagnosis, not c.denial_code
```

## OLAP algebra

Let **E**, **Dx**, **C**, **P**, **I**, **V**, **Ev**, and **F** denote encounter, diagnosis, claim, dispense, inventory transaction, vital, ICU event, and feedback fact sets. `SLICE` fixes a dimension value; `DICE` restricts several dimensions; `ROLLUP+` moves up a hierarchy; `DRILLACROSS` combines compatible facts at a shared grain. Rates are derived after their numerator and denominator are aggregated, so rates themselves are never summed.

1. **Winter beds:** `ROLLUP+_{Department→All, Day→Month→All}(SLICE_{E.type=IP}(E ⋈ Month), Σ admissions, Σ overflow, Σ bed_days)`.
2. **ED crowding:** `DRILLACROSS_{Month}(ROLLUP+_{Day→Month}(SLICE_{E.type=ED}(E), median(wait), Σ LWBS), ROLLUP+_{Day→Month}(SLICE_{E.type=IP}(E), Σ bed_days))`; `DICE_{Jan–Feb 2025}` isolates the surge.
3. **Readmission:** `ROLLUP+_{Diagnosis→ICD cohort, Department→All}(DICE_{E.type=IP, Dx.type=PRIMARY}(E ⋈ Dx), Σ readmissions / Σ discharges)`; `RANK` orders departments inside each cohort.
4. **Coding denial:** `DRILLACROSS_{Encounter}(SLICE_{first}(C), SLICE_{PRIMARY}(Dx), E)` followed by `ROLLUP+_{Dx validity→All}(Σ denied / Σ first_claims)`.
5. **Authorisation:** `CUBE_{Payer, Department, Year}(DICE_{E.type∈{IP,DAY}, first claim}(C ⋈ E), Σ AUTH-002 / Σ first_claims)`; `SLICE_{Payer=Falcon}` identifies the planted pattern.
6. **Stockouts:** `DRILLACROSS_{Drug×Day}(DICE_{P.status∈{DELAYED_STOCKOUT,SUBSTITUTED}}(P), SLICE_{I.type=RECEIPT}(I))`, then `ROLLUP+_{Day→Month}(Σ affected, Σ no_recent_receipt)` and a running total.
7. **ICU:** `ROLLUP+_{Minute→Hour-before-event}(DICE_{Ev.time−4h≤V.time<Ev.time}(V ⋈_{bed,MRN} Ev), AVG(valid vitals))`; a two-hour moving average smooths the hourly means.
8. **Billing feedback:** `DRILLACROSS_{Encounter}(F, SLICE_{first}(C), E)` followed by `ROLLUP+_{Year→All, Claim outcome→All}(Σ billing complaints / Σ linked feedback)`.

## Supplied full data results

| Problem | Measured finding | Answer-key check |
| --- | --- | --- |
| 1 | Jan and Feb 2025 had **311** and **400** overflow admissions; estimated ward occupancy was **96.72%** and **97.32%**. | Matches the planted winter 300–400/month pattern. |
| 2 | Exact reference medians were **90** and **102** minutes in Jan and Feb 2025, with **9.53%** and **9.82%** leaving without being seen. Hive's `percentile_approx` returned **89.06** and **101.06** minutes; August's exact median was 26 minutes and 4.26% left unseen. | Matches the winter-versus-summer pattern; association does not prove causation. |
| 3 | I50.9 inpatients: **448/2,384 = 18.79%** readmitted; other inpatients: **2,475/42,784 = 5.78%**. | Matches about 19% versus 6%. |
| 4 | Missing/invalid primary diagnosis: **16,873/25,877 = 65.20%** denied; valid primary: **34,343/677,044 = 5.07%**. | The valid group is close to the key's ~6%, but the bad-coding group conflicts with its ~53%. The supplied generator sets a 0.65 denial probability for this group; the observed 65.20% is consistent with that code. Do not replace it with the answer-key number. |
| 5 | Falcon Medical Cover's ORTH/BARI inpatient/day-case first claims had **788/2,250 = 35.02%** `AUTH-002` denials; **836/2,250 = 37.16%** were denied for any reason. | The overall denial rate is consistent with the planted ~38% prior-authorisation issue; diagnosis-quality denials take precedence in the generator, so the AUTH-002-only share is lower. |
| 6 | Affected dispenses: RX004 **1,712** in Nov 2024 and **1,353** in Sep 2025; RX005 **3,511** in Feb 2025. All **6,576** had no ERP receipt for the requested drug in the preceding seven days. | Matches the three planted periods and absent receipts. This is a transaction check, not a computed stock balance. |
| 7 | Across **126** events, mean HR went from **90.35** to **119.49 bpm** and mean SpO₂ from **95.97%** to **89.04%** from the fourth to the final hour before an event. | Matches the deterioration direction and approximate values. Historical aggregation is distinct from Member 3's streaming replay. |
| 8 | Billing complaints occurred in **2,861/5,216 = 54.85%** of feedback linked to a denied first claim versus **2,583/66,347 = 3.89%** for other first claims. | Matches the planted strong association. |

Figures in `charts/` show the winter bed pressure, ED crowding, comparative risks, three stockout periods, the four-hour ICU trend, and the Falcon payer gap. All are derived from `results_full/` CSVs by `make_charts.py`. The `results_sample/` CSVs are development checks only: the 2% sample does not reproduce full bed pressure, so its low overflow and wait figures must not appear as final findings.

## Execution evidence and integration

Hive 4.0.1 ran in an isolated Docker container on the Mac. The external tables were pointed first at the 2% sample and all eight HQL files returned rows. The container was then loaded with landing files normalized from the supplied full-data archive. Independent DuckDB checks ran on both sample and full files; they are labelled as reference calculations, not Hive evidence. Terminal logs in `evidence/` record the actual Hive commands, Tez progress and output rows. The full-Hive log status is recorded in `evidence/STATUS.md`.

The group can map Problems 1–6 onto the updated Member 6 star schema through its repaired Member 4 adapter and retained business fields. `Claim` must retain `denial_code`, `Dispense` must retain `status` and `substituted_for`, `Inventory` must retain transaction type, and clinical diagnoses must be joined by `encounter_id`. Problems 7 and 8 remain historical joins over vitals/events and feedback/claims, as Member 6's design places them outside the star. This isolated Hive run does not claim that the eight Member 7 HQL files ran unchanged on Member 1's course VM HDFS or the integrated Member 6 warehouse.

**Screenshots for the final group report:** `member7_01_code.png` shows the HQL and command, `member7_02_running.png` shows live Hive/Tez progress, and `member7_03_output.png` shows the four-row result. They are genuine captures from this Mac and are labelled as an isolated Docker Hive run over the supplied full synthetic dataset.

## Limitations and evaluation

The analysis uses synthetic, generated records from the supplied full-data archive. Bed-day occupancy estimates depend on date-granularity intervals; missing discharge dates are assigned one day. The ED and feedback analyses show associations, not causal effects. Billing complaints are detected using a transparent English/Arabic keyword rule; it can miss paraphrases or classify unrelated text. Diagnosis validity uses code shape plus a nonempty description, not a complete clinical code dictionary. The 30-day readmission measure uses the synthetic encounter flag. The ICU history describes event-linked averages, not patient-level warning sensitivity, prospective clinical validation, or real-time latency. The isolated Hive run is not a multi-node performance benchmark. No company evaluation or stakeholder opinion was provided; one must not be invented for Aspect 3.

## Lessons learned (Member 7, 190 words)

I learned that an OLAP result is only as trustworthy as its grain and join keys. My first occupancy calculation counted open admissions through later months; assigning a one-day interval to missing discharges fixed an inflated census. The claims analysis exposed a different risk: a denial code describes the billing decision and cannot serve as a diagnosis. I joined claims to the clinical primary diagnosis instead. I also found that resubmissions and duplicate claims change denominators, so I defined first submissions before calculating rates. Hive's ROLLUP, CUBE and GROUPING SETS made the requested summary levels explicit, while window functions showed rankings and trends that ordinary totals hide. Running the same measures on the small sample and supplied full data taught me why a sample is suitable for testing syntax but not for checking a winter capacity pattern. The most useful validation was finding a conflict between the answer key's 53% coding-denial figure and the generator's 65% probability. I reported the measured 65.20% and its source instead of forcing a match. Before any real hospital use, I would validate code sets, feedback themes and alert thresholds with clinical and billing staff.
