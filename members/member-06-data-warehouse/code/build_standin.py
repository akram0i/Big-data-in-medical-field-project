"""STAND-IN curated tables for testing Member 6's star schema before Members 4 and 5 finish.

This is NOT the project's ETL (that's Members 4 and 5, in Hive). It does a quick Python clean of the
2% sample so member6_star_schema.hql can be run and checked on the VM right away.
It also prints the results the .hql check queries should return on this data (expected_results.txt).

Run:  python build_standin.py <path to sample_2pct or full ahd_data> [output folder]
Output: standin/<table>.tsv (tab-separated, \\N = NULL) + expected_results.txt
"""
import glob, json, os, re, sys
import xml.etree.ElementTree as ET
import pandas as pd

SRC = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "standin")
os.makedirs(OUT, exist_ok=True)


def ts(s):
    """3 source formats -> 'yyyy-MM-dd HH:mm:ss' (Dubai local time)."""
    s = s.fillna("").str.strip().str.replace(r"\+04:00$", "", regex=True).str.replace(r"(\d)T(\d)", r"\1 \2", regex=True)  # not the T in OCT
    a = pd.to_datetime(s, format="%Y-%m-%d %H:%M:%S", errors="coerce")
    b = pd.to_datetime(s, format="%d/%m/%Y %H:%M", errors="coerce")
    c = pd.to_datetime(s.str.title(), format="%d-%b-%Y %H:%M", errors="coerce")  # Oracle 01-JAN-2024 00:43
    return a.fillna(b).fillna(c).dt.strftime("%Y-%m-%d %H:%M:%S")


def save(df, name):
    df.to_csv(os.path.join(OUT, name + ".tsv"), sep="\t", header=False, index=False, na_rep="\\N",
              lineterminator="\n")  # Hive would keep a Windows \r in the last column
    return df


DEPT = {"BARIATRIC": "BARI", "BARIATRIC SURGERY": "BARI", "BARIATRICS": "BARI", "CARDIO": "CARD",
        "CARDIOLOGY": "CARD", "CRITICAL CARE": "ICU", "INTENSIVE CARE": "ICU", "DERMA": "DERM",
        "DERMATOLOGY": "DERM", "ER": "ED", "EMERGENCY": "ED", "EMERGENCY DEPARTMENT": "ED",
        "ENDOCRINE": "ENDO", "ENDOCRINOLOGY": "ENDO", "GEN SURGERY": "GSURG", "GENERAL SURGERY": "GSURG",
        "SURG": "GSURG", "GENERAL INTERNAL MEDICINE": "GIM", "IM": "GIM", "INTERNAL MEDICINE": "GIM",
        "NEURO": "NEUR", "NEUROLOGY": "NEUR", "OB/GYN": "OBGY", "OBGYN": "OBGY",
        "OBSTETRICS & GYNAECOLOGY": "OBGY", "ONCO": "ONC", "ONCOLOGY": "ONC", "ORTHO": "ORTH",
        "ORTHOPAEDICS": "ORTH", "ORTHOPEDICS": "ORTH", "PAEDS": "PED", "PAEDIATRICS": "PED", "PEDIATRICS": "PED"}

# --- patients + mrn_map (duplicates AHD2xxxxxx matched on DOB + name tokens)
p = pd.read_csv(f"{SRC}/ehr_cerner/patients.csv", dtype=str)
dob = pd.to_datetime(p.date_of_birth, format="%Y-%m-%d", errors="coerce").fillna(
    pd.to_datetime(p.date_of_birth, format="%d/%m/%Y", errors="coerce"))
p["date_of_birth"] = dob.dt.strftime("%Y-%m-%d")
name = (p.first_name.fillna("") + " " + p.last_name.fillna("")).str.lower().str.replace("al-", "al ")
p["k"] = name.str.split().map(lambda t: " ".join(sorted(t))) + "|" + p.date_of_birth.fillna("")
canon = p[~p.mrn.str.startswith("AHD2")].drop_duplicates("k").set_index("k").mrn
dups = p[p.mrn.str.startswith("AHD2")]
mrn_map = pd.DataFrame({"mrn": dups.mrn, "canonical_mrn": dups.k.map(canon)}).dropna()
save(p[["mrn", "first_name", "last_name", "gender", "date_of_birth", "nationality", "emirate"]], "patients")
save(mrn_map, "mrn_map")

# --- encounters
e = pd.read_csv(f"{SRC}/ehr_cerner/encounters.csv", dtype=str).drop_duplicates()
e["mrn"] = e.mrn.where(e.mrn.str.startswith("AHD"), "AHD" + e.mrn)          # legacy PAS MRNs
d = e.department.str.strip().str.upper()
e["department"] = d.map(DEPT).fillna(d)
e["admit_ts"], e["discharge_ts"] = ts(e.admit_ts), ts(e.discharge_ts)
enc = save(e[["encounter_id", "mrn", "encounter_type", "department", "attending_id", "admit_ts", "discharge_ts",
              "bed_id", "triage_level", "ed_wait_minutes", "discharge_disposition", "readmission_flag",
              "source_system"]], "encounters")

# --- diagnoses: upper case, trim, put the dot back
dx = pd.read_csv(f"{SRC}/ehr_cerner/diagnoses.csv", dtype=str)
code = dx.icd10_code.fillna("").str.strip().str.upper()
dotless = code.str.fullmatch(r"[A-Z][0-9][0-9A-Z][0-9A-Z]{1,4}")
dx["icd10_code"] = code.where(~dotless, code.str[:3] + "." + code.str[3:]).replace("", None)
save(dx[["encounter_id", "seq", "icd10_code", "description", "dx_type", "recorded_at"]], "diagnoses")

# --- claims: "AED 1,234.50" -> 1234.50
cl = pd.read_csv(f"{SRC}/billing_oracle/claims.csv", dtype=str)
for col in ("total_amount", "paid_amount"):
    cl[col] = pd.to_numeric(cl[col].str.replace(r"[^0-9.]", "", regex=True), errors="coerce")
save(cl[["claim_id", "encounter_id", "mrn", "payer", "submitted_date", "total_amount", "status", "denial_code",
         "denial_reason", "paid_amount", "paid_date", "resubmission_of"]], "claims")

# --- dispense: merge schema v1 (2024) and v2 (2025)
rows = []
for f in sorted(glob.glob(f"{SRC}/pharmacy_api/*.jsonl")):
    for line in open(f, encoding="utf-8"):
        r = json.loads(line)
        if r.get("schema_version") == 2:
            t = r["timestamp"]
            t = (pd.to_datetime(t, unit="ms", utc=True).tz_convert("Asia/Dubai").strftime("%Y-%m-%d %H:%M:%S")
                 if isinstance(t, (int, float)) else t)
            rows.append(dict(dispense_id=r["id"], mrn=r["patient"]["mrn"], encounter_id=r["patient"]["encounter"],
                             drug_code=r["drug"]["code"], drug_name=r["drug"]["name"], qty=r["quantity"],
                             dispensed_at=t, status=r["status"], delay_minutes=r.get("delay_minutes"),
                             substituted_for=r.get("substituted_for")))
        else:
            rows.append(dict(dispense_id=r["dispense_id"], mrn=r["mrn"], encounter_id=r["encounter_id"],
                             drug_code=r["drug_code"], drug_name=r["drug_name"], qty=r["qty"],
                             dispensed_at=r["dispensed_at"], status=r["status"],
                             delay_minutes=r.get("delay_minutes"), substituted_for=r.get("substituted_for")))
ds = pd.DataFrame(rows)
ds["dispensed_at"] = ts(ds.dispensed_at.astype(str))
ds["delay_minutes"] = pd.to_numeric(ds.delay_minutes, errors="coerce").astype("Int64")
save(ds, "dispense")

# --- inventory XML
rows = []
for f in sorted(glob.glob(f"{SRC}/erp_oracle/*.xml")):
    for t in ET.parse(f).getroot().iter("Txn"):
        g = lambda tag: (t.findtext(tag) or None)
        rows.append(dict(txn_id=t.get("id"), item_code=g("ItemCode"), item_name=g("ItemName"), txn_type=g("Type"),
                         qty=g("Qty"), unit_cost=g("UnitCost"), store=g("Store"), txn_ts=g("Timestamp")))
inv = pd.DataFrame(rows).drop_duplicates("txn_id")
inv["txn_ts"] = ts(inv.txn_ts)
save(inv, "inventory")

# ---------------- expected results of the .hql CHECKS section ----------------
VALID = r"[A-Z][0-9]{2}(\.[0-9][0-9A-Z]{0,3})?"
dx["valid"] = dx.icd10_code.fillna("").str.fullmatch(VALID)
prim = dx[dx.dx_type == "PRIMARY"].sort_values("seq").drop_duplicates("encounter_id").set_index("encounter_id").valid
canon_of = dict(zip(mrn_map.mrn, mrn_map.canonical_mrn))
pat_mrns = set(p.mrn) - set(mrn_map.mrn)
enc["cmrn"] = enc.mrn.map(lambda m: canon_of.get(m, m))
codes = {"CARD", "ONC", "ORTH", "OBGY", "PED", "GIM", "GSURG", "NEUR", "ENDO", "BARI", "DERM", "ED", "ICU"}

def coding(eid):
    if eid not in prim.index:
        return "MISSING"
    return "VALID" if prim[eid] else "INVALID"

out = []
out.append("Row counts (each fact must equal its source):")
for n, df in [("encounters", enc), ("claims", cl), ("dispense", ds), ("inventory", inv)]:
    out.append(f"  {n:<12} {len(df)}")
out.append("\nfact_encounter placeholder hits:")
out.append(f"  unknown_patient     {(~enc.cmrn.isin(pat_mrns)).sum()}")
out.append(f"  unknown_department  {(~enc.department.isin(codes)).sum()}")
st = enc.encounter_id.map(coding)
out.append(f"  missing_primary_dx  {(st == 'MISSING').sum()}")
out.append(f"  invalid_primary_dx  {(st == 'INVALID').sum()}")
enc_ids = set(enc.encounter_id)
cl["coding"] = cl.encounter_id.map(lambda x: coding(x) if x in enc_ids else "UNKNOWN")
first = cl[cl.resubmission_of.isna()]
t = first.groupby("coding").status.agg(claims="size", denial_rate=lambda s: round((s == "DENIED").mean(), 3))
out.append("\nProblem 4 check (first submissions by coding_status):\n" + t.to_string())
ip = enc[enc.encounter_type == "IP"].copy()
ip["a"], ip["d"] = pd.to_datetime(ip.admit_ts), pd.to_datetime(ip.discharge_ts)
ip = ip.sort_values(["cmrn", "a"])
ip["nxt"] = ip.groupby("cmrn").a.shift(-1)
ip["r30"] = ((ip.nxt.dt.normalize() - ip.d.dt.normalize()).dt.days.between(0, 30)).astype(int)  # = Hive datediff
pc = dx[dx.dx_type == "PRIMARY"].drop_duplicates("encounter_id").set_index("encounter_id").icd10_code
ip["hf"] = ip.encounter_id.map(pc).eq("I50.9")
out.append("\nProblem 3 (readmit_30d_flag on IP stays, heart failure I50.9 vs others):")
out.append(f"  I50.9: {ip[ip.hf].r30.mean():.3f} of {ip.hf.sum()} stays;  others: {ip[~ip.hf].r30.mean():.3f}")
out.append(f"\nmrn_map: {len(mrn_map)} duplicate MRNs matched of {p.mrn.str.startswith('AHD2').sum()} AHD2 patients")
txt = "\n".join(out)
print(txt)
open(os.path.join(os.path.dirname(OUT), "expected_results.txt"), "w", encoding="utf-8").write(txt + "\n")
