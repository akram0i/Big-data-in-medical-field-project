# Answer key — planted problems in the synthetic AHD dataset

Use this to check your findings. All figures are from the full-size dataset (seed 312).

## A. Business problems your data lake should reveal

| # | Problem | Where it shows | What you should find |
| --- | --- | --- | --- |
| 1 | **Winter bed crunch** | `encounters.csv` (`bed_id = OVERFLOW`, IP census) | Ward occupancy rises every winter; in Jan–Feb 2025 (respiratory surge) about 300–400 admissions a month get no ward bed. Almost none in summer. |
| 2 | **ED crowding caused by full wards** | `encounters.csv` (`ed_wait_minutes`, `LEFT_WITHOUT_BEING_SEEN`), feedback | Median ED wait about 25–35 min in summer vs about 90–100 min in Jan–Feb 2025; patients leaving without being seen rise from about 4% to about 10%; "wait" complaints nearly double. ED waits track ward occupancy, not ED volume alone. |
| 3 | **Heart-failure readmissions** | `encounters.csv` (`readmission_flag`) + `diagnoses.csv` | 30-day readmission about 19% for primary dx I50.9 vs about 6% for all other inpatients. |
| 4 | **Claim denials from bad coding** | `claims.csv` + `diagnoses.csv` | About 8% of first submissions denied. Encounters with **no or invalid primary diagnosis** are denied about 53% of the time (DX-003) vs about 6% otherwise. |
| 5 | **One payer's prior-authorisation denials** | `claims.csv` + `encounters.csv` | "Falcon Medical Cover" denies about 38% of ORTH and BARI inpatient/day-case claims (AUTH-002). |
| 6 | **Drug stockouts** | `pharmacy_api` (`status`), `erp_oracle` (no RECEIPTs) | Enoxaparin (RX005) 3–23 Feb 2025; Ceftriaxone (RX004) 10–24 Nov 2024 and 1–14 Sep 2025. Dispenses become DELAYED_STOCKOUT or SUBSTITUTED (heparin RX026 / pip-taz RX020); ERP shows no receipts in the week before and during each window; pharmacy complaints appear in feedback. |
| 7 | **ICU deterioration is predictable** | `icu_monitors/vitals_stream` + `icu_events.csv` | In the 4 hours before an event, heart rate climbs (about 89 → 120+), SpO₂ falls (about 96 → 89), resp. rate rises, blood pressure drops. A streaming early-warning job could alert before the event. |
| 8 | **Billing frustration** | `feedback` + `claims.csv` | Patients whose claims were denied are far more likely to leave billing/insurance complaints. |

## B. Data-quality issues (for ETL and "potential issues")

| Source | Issue | Approx. size |
| --- | --- | --- |
| patients | **Duplicate patients** under a second MRN (`AHD2xxxxxx`): name case changed, first/last swapped, trailing space, "Al " → "Al-", DOB in another format, different phone format | 3% (4,697) |
| patients | Nationality written 4 ways for Emiratis: Emirati / UAE / United Arab Emirates / AE | all Emiratis |
| patients | DOB in DD/MM/YYYY instead of YYYY-MM-DD; DOB missing | 5% / 1% |
| patients | Mobile in 3 formats (+971 5x xxx xxxx, 05xxxxxxxx, 971-5x-xxxxxxx); missing | 2% missing |
| encounters | Encounters filed under the duplicate MRN (patient history split) | about 35% of a duplicate patient's visits |
| encounters | **Legacy PAS rows**: MRN without the `AHD` prefix (e.g. `1001122`), source_system = LEGACY_PAS, Jan–Jun 2024 only | about 12,000 rows |
| encounters | Mixed timestamp formats: `YYYY-MM-DD HH:MM:SS`, `DD/MM/YYYY HH:MM`, ISO with `+04:00` | 5% / 3% |
| encounters | Department as name/variant instead of code (e.g. "Cardiology", "CARDIO", "ICU " with a trailing space) | 8% |
| encounters | Exact duplicate rows | 0.4% |
| encounters | Discharge before admit | 0.3% |
| encounters | Inpatient with blank discharge_ts | 1% of IP |
| diagnoses | ICD-10 code without the dot (`I509`), lower case (`i50.9`), invalid (`R99X`, `I5O.9`, `UNKNOWN`…) | 6% / 2% / 0.7% |
| diagnoses | Encounter has no PRIMARY diagnosis at all | 3% of encounters |
| HL7 labs | Glucose reported in **mmol/L** instead of mg/dL (with matching range) | 10% of glucose results |
| HL7 labs | Truncated messages (cut mid-segment) | 0.3% |
| HL7 labs | Duplicate (resent) messages with the same control ID | 0.8% |
| HL7 labs | Late arrivals: message stored in the next month's file | 1% |
| HL7 labs | Result time earlier than order time | 0.3% |
| HL7 labs | Missing abnormal flag | 2% of results |
| pharmacy | **Schema drift** on 1 Jan 2025: flat v1 → nested v2 with renamed fields | all 2025 files |
| pharmacy | v2 timestamp is epoch milliseconds (UTC) 70% of the time, ISO with `+04:00` 30% | 2025 |
| pharmacy | Null route / null dose | 2% / 1% |
| inventory | Two timestamp formats (ISO vs Oracle `05-MAR-2024 10:15`) | 15% Oracle format |
| inventory | Duplicate transaction IDs | 0.5% |
| inventory | Negative quantity on a RECEIPT | 0.3% of receipts |
| inventory | Missing UnitCost on receipts; ISSUE rows carry no cost by design | 1% of receipts |
| claims | Amount as text `AED 1,234.50`, or blank | 10% / 2% |
| claims | **Orphan claims**: encounter_id not in encounters | about 0.8% |
| claims | Duplicate submissions denied as DUP-004; resubmissions linked by `resubmission_of` | 1% / 40% of denials |
| vitals | Null readings (sensor dropout) | 1% per field |
| vitals | Impossible values: HR 0/300/350, SpO₂ > 100 | 0.05% of readings |
| vitals | **Clock drift**: monitors on ICU-07 and ICU-15 run 7 minutes fast from 1 Oct 2025 | 2 devices |
| vitals | Duplicate readings; out-of-order lines within a file | 0.2% / 0.5% |
| notes | Typos and abbreviations ("admited", "w/") | 5% |
| feedback | Arabic-language comments; missing rating; no encounter_id | about 8% / 3% / 15% |

## C. Why these matter for tool choice (course link)

- **Vitals stream (problem 7)** needs low-latency processing of continuous data. **MapReduce is batch-only**: it reads complete files from HDFS and writes results at the end, so it cannot raise an alert minutes before a deterioration. Use MapReduce/Hive for the historical analysis and a streaming tool for live alerts.
- **Hive** suits the batch questions (problems 1–6, 8): partition encounters and claims by month, use ROLLUP/CUBE for occupancy and denial reports.
- **HBase** suits fast single-patient lookups (latest vitals, latest labs by MRN), which Hive's full-scan queries handle poorly.
- **Mixed formats (CSV, JSON, HL7, XML, free text)** and **schema drift** are why a data lake (schema on read) fits better than loading everything into one relational warehouse first.
