# Synthetic American Hospital Dubai (AHD) dataset

**Prepared by:** AHD employee

**All data in this folder is synthetic.** No real patient, staff, insurer or financial data is included. Names, MRNs, phone numbers, policy numbers and insurer names are invented. The structure is modelled on AHD's publicly reported systems (Cerner EHR, Oracle Cloud ERP, an in-house ICU/AI data lab, DHA's NABIDH exchange). The volumes are a realistic estimate for a 252-bed private hospital.

- **Period:** 1 Jan 2024 – 31 Dec 2025 (ICU monitor stream: 1 Jul – 31 Dec 2025)
- **Total:** about 12.6 million rows / 1.9 GB across 7 source systems and 5 formats
- **Regenerate:** `python3 generate_ahd.py --out ahd_data` (seed 312, about 3 minutes, needs Python 3.8+ and numpy). Use `--scale 0.02` for a small test copy.

## 1. Source systems

| Folder | Simulated source system | Format | Rows | Arrives as |
| --- | --- | --- | --- | --- |
| `ehr_cerner/patients.csv` | Cerner EHR – patient master | CSV | 164,697 | Nightly batch export |
| `ehr_cerner/encounters.csv` | Cerner EHR + legacy PAS – visits/admissions | CSV | 780,371 | Nightly batch export |
| `ehr_cerner/diagnoses.csv` | Cerner EHR – ICD-10 coding | CSV | 1,296,906 | Nightly batch export |
| `ehr_cerner/clinical_notes.jsonl` | Cerner EHR – discharge summaries, ED notes | JSON lines (free text) | 81,514 | Nightly batch export |
| `lis_hl7/oru_YYYY-MM.hl7` | Laboratory information system → EHR interface | HL7 v2.5.1 ORU^R01 | 978,256 messages / 2,857,672 results | Real-time messages, archived monthly |
| `pharmacy_api/dispense_YYYY-MM.jsonl` | Pharmacy dispensing system REST API | JSON lines | 1,011,013 | API pull, hourly |
| `erp_oracle/inventory_YYYY-MM.xml` | Oracle Cloud SCM – drug inventory | XML | 99,299 | Daily file export |
| `billing_oracle/claims.csv` | Oracle billing – insurance claims | CSV | 735,391 | Daily batch export |
| `icu_monitors/vitals_stream/vitals_YYYY-MM-DD.jsonl` | Bedside ICU monitors (24 beds, 1 reading/min) | JSON lines | 5,510,388 | **Continuous stream** |
| `icu_monitors/icu_events.csv` | ICU rapid-response / arrest log | CSV | 126 | Manual entry |
| `feedback/patient_feedback.csv` | Patient experience surveys (SMS, app, email, web) | CSV (English + Arabic text) | 92,593 | Daily batch |

## 2. Schemas

**patients.csv** — `mrn, first_name, last_name, gender, date_of_birth, nationality, emirate, mobile, insurance_payer, policy_number, registration_date`

**encounters.csv** — `encounter_id, mrn, encounter_type (OP|ED|DAY|IP), department, attending_id, admit_ts, discharge_ts, bed_id, triage_level (ED 1–5), ed_wait_minutes (ED), discharge_disposition, readmission_flag (Y/N), source_system (CERNER|LEGACY_PAS)`
- Department codes: CARD, ONC, ORTH, OBGY, PED, GIM, GSURG, NEUR, ENDO, BARI, DERM, ED, ICU.
- `bed_id`: ward beds `W1-01`…`W8-25` (228 beds), ICU beds `ICU-01`…`ICU-24`; `OVERFLOW` = admitted with no ward bed free (boarded in ED/corridor).

**diagnoses.csv** — `encounter_id, seq, icd10_code, description, dx_type (PRIMARY|SECONDARY), recorded_at`

**clinical_notes.jsonl** — `note_id, encounter_id, mrn, note_type, author_id, created_at, text`

**HL7 lab messages** — one message per lab panel; segments on separate lines, a blank line between messages.
- `MSH-7` message time, `MSH-10` control ID
- `PID-3` MRN, `PID-5` name, `PID-7` DOB, `PID-8` sex
- `PV1-2` class (I/E/O), `PV1-3` department, `PV1-19` encounter ID
- `OBR-4` panel (CBC, BMP, LIPID, HBA1C, TROP, CRP, LACT), `OBR-7` order time, `OBR-22` result time
- `OBX-3` test code, `OBX-5` value, `OBX-6` unit, `OBX-7` reference range, `OBX-8` flag (H/L/N)

**pharmacy dispense JSON** — two schema versions (see answer key):
- v1 (2024): `dispense_id, mrn, encounter_id, drug_code, drug_name, dose_mg, route, qty, dispensed_at, pharmacist_id, status` (+ `dose_note`, `delay_minutes`, `substituted_for` when relevant)
- v2 (2025): `id, schema_version, patient{mrn, encounter}, drug{code, name}, dose{value, unit}, route, quantity, timestamp, pharmacist, status, delay_minutes, substituted_for`
- `status`: DISPENSED, DELAYED_STOCKOUT, SUBSTITUTED

**inventory XML** — `<Txn id><ItemCode><ItemName><Type>RECEIPT|ISSUE|ADJUSTMENT</Type><Qty><UnitCost currency="AED"><Store>MAIN_PHARMACY|ICU_SATELLITE|ED_SATELLITE</Store><Timestamp></Txn>`

**claims.csv** — `claim_id, encounter_id, mrn, payer, submitted_date, total_amount, status (PAID|PARTIAL|DENIED|PENDING), denial_code, denial_reason, paid_amount, paid_date, resubmission_of`

**vitals JSON** — `device_id, bed_id, mrn, ts, hr, spo2, rr, sbp, dbp, temp` (one reading per bed per minute)

**icu_events.csv** — `event_id, bed_id, mrn, encounter_id, event_ts, event_type (RAPID_RESPONSE|INTUBATION|CARDIAC_ARREST), outcome`

**patient_feedback.csv** — `feedback_id, submitted_at, channel, encounter_id, rating (1–5), comment`

## 3. Joining the sources

| Key | Links |
| --- | --- |
| `encounter_id` | encounters ↔ diagnoses, clinical notes, HL7 `PV1-19`, pharmacy, claims, ICU events, feedback |
| `mrn` | patients ↔ every other source (watch for duplicate and legacy MRNs) |
| `drug_code` / `ItemCode` | pharmacy ↔ inventory |
| `bed_id` + time | vitals ↔ ICU encounters and ICU events |

## 4. Loading into HDFS (lab VM)

```
hadoop fs -mkdir -p /datalake/raw
hadoop fs -put ehr_cerner billing_oracle erp_oracle pharmacy_api lis_hl7 feedback icu_monitors /datalake/raw/
hadoop fs -ls -R /datalake/raw | head
```

Keep `/datalake/raw` untouched (raw zone), write cleaned tables to `/datalake/curated`, and build Hive tables over each zone.

## 5. Notes for the report

- Say clearly that the data is **synthetic and modelled on AHD's systems**, generated because real patient data cannot be shared.
- `ANSWER_KEY.md` lists every planted data-quality issue and business problem. Read it after you have explored the data if you want to "discover" them yourselves.
