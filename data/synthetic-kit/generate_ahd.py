#!/usr/bin/env python3
"""
Synthetic data generator for an American Hospital Dubai (AHD) style data lake.
Prepared by: AHD employee

ALL DATA IS SYNTHETIC. No real patient, staff or payer data is used.
Insurance payer names are fictional. Systems are modelled on AHD's publicly
reported stack (Cerner EHR, Oracle Cloud ERP) but every record is invented.

Usage:
    python3 generate_ahd.py --out ahd_data            # full size (~12.6M rows)
    python3 generate_ahd.py --out sample --scale 0.02  # small sample

The output is deterministic for a given --seed and --scale.
"""
import argparse
import csv
import heapq
import json
import math
import os
import random
from datetime import datetime, timedelta

import numpy as np

START = datetime(2024, 1, 1)
NDAYS = 731                                   # 2024-01-01 .. 2025-12-31
END_MIN = NDAYS * 1440
VITALS_START_MIN = (datetime(2025, 7, 1) - START).days * 1440
DRIFT_START_MIN = (datetime(2025, 10, 1) - START).days * 1440
SCHEMA_V2_MIN = (datetime(2025, 1, 1) - START).days * 1440
LEGACY_END_MIN = (datetime(2024, 7, 1) - START).days * 1440


def d2m(y, m, d):
    return (datetime(y, m, d) - START).days * 1440


# ---------------------------------------------------------------- reference data
DEPTS = ["CARD", "ONC", "ORTH", "OBGY", "PED", "GIM", "GSURG", "NEUR", "ENDO", "BARI", "DERM", "ED", "ICU"]
DEPT_VARIANTS = {
    "CARD": ["Cardiology", "CARDIO", "cardiology"], "ONC": ["Oncology", "ONCO", "oncology"],
    "ORTH": ["Orthopaedics", "Orthopedics", "ORTHO"], "OBGY": ["Obstetrics & Gynaecology", "OB/GYN", "OBGYN"],
    "PED": ["Paediatrics", "Pediatrics", "PAEDS"], "GIM": ["Internal Medicine", "General Internal Medicine", "IM"],
    "GSURG": ["General Surgery", "Gen Surgery", "SURG"], "NEUR": ["Neurology", "NEURO", "neurology"],
    "ENDO": ["Endocrinology", "Endo", "ENDOCRINE"], "BARI": ["Bariatric Surgery", "Bariatrics", "BARIATRIC"],
    "DERM": ["Dermatology", "Derma", "DERMA"], "ED": ["Emergency", "Emergency Department", "ER"],
    "ICU": ["Intensive Care", "ICU ", "Critical Care"],
}
OP_DEPT_P = {"CARD": .10, "ONC": .05, "ORTH": .12, "OBGY": .12, "PED": .14, "GIM": .20, "GSURG": .06,
             "NEUR": .06, "ENDO": .10, "BARI": .03, "DERM": .02}
DAY_DEPT_P = {"ONC": .35, "GSURG": .20, "ORTH": .15, "BARI": .10, "CARD": .10, "OBGY": .10}
IP_DEPT_P = {"CARD": .18, "GIM": .25, "GSURG": .14, "ORTH": .12, "OBGY": .12, "PED": .07, "ONC": .05,
             "NEUR": .04, "BARI": .03}
IP_LOS_MEDIAN = {"CARD": 3.5, "GIM": 3.2, "GSURG": 2.5, "ORTH": 3.0, "OBGY": 2.0, "PED": 2.0, "ONC": 4.5,
                 "NEUR": 4.0, "BARI": 2.5}

DX = {
    "CARD": [("I50.9", "Heart failure, unspecified"), ("I10", "Essential (primary) hypertension"),
             ("I21.4", "Non-ST elevation myocardial infarction"), ("I48.91", "Atrial fibrillation, unspecified"),
             ("I25.10", "Atherosclerotic heart disease of native coronary artery"), ("R07.9", "Chest pain, unspecified")],
    "ONC": [("C50.919", "Malignant neoplasm of breast, unspecified"), ("Z51.11", "Encounter for antineoplastic chemotherapy"),
            ("C18.9", "Malignant neoplasm of colon, unspecified"), ("C34.90", "Malignant neoplasm of lung, unspecified"),
            ("C61", "Malignant neoplasm of prostate")],
    "ORTH": [("M17.11", "Primary osteoarthritis, right knee"), ("M54.5", "Low back pain"),
             ("S72.001A", "Fracture of neck of right femur, initial encounter"), ("M75.100", "Rotator cuff tear, unspecified shoulder"),
             ("S82.201A", "Fracture of shaft of right tibia, initial encounter")],
    "OBGY": [("Z34.90", "Supervision of normal pregnancy, unspecified"), ("O80", "Encounter for full-term uncomplicated delivery"),
             ("N92.0", "Excessive and frequent menstruation"), ("O24.419", "Gestational diabetes mellitus in pregnancy"),
             ("D25.9", "Leiomyoma of uterus, unspecified")],
    "PED": [("J06.9", "Acute upper respiratory infection, unspecified"), ("A09", "Infectious gastroenteritis and colitis"),
            ("R50.9", "Fever, unspecified"), ("J45.909", "Unspecified asthma, uncomplicated"), ("H66.90", "Otitis media, unspecified")],
    "GIM": [("E11.9", "Type 2 diabetes mellitus without complications"), ("I10", "Essential (primary) hypertension"),
            ("J18.9", "Pneumonia, unspecified organism"), ("N39.0", "Urinary tract infection, site not specified"),
            ("K21.9", "Gastro-oesophageal reflux disease without oesophagitis"), ("E78.5", "Hyperlipidaemia, unspecified")],
    "GSURG": [("K35.80", "Unspecified acute appendicitis"), ("K80.20", "Calculus of gallbladder without obstruction"),
              ("K40.90", "Unilateral inguinal hernia"), ("L02.91", "Cutaneous abscess, unspecified")],
    "NEUR": [("G43.909", "Migraine, unspecified"), ("I63.9", "Cerebral infarction, unspecified"),
             ("G40.909", "Epilepsy, unspecified"), ("G35", "Multiple sclerosis")],
    "ENDO": [("E11.9", "Type 2 diabetes mellitus without complications"), ("E11.65", "Type 2 diabetes mellitus with hyperglycaemia"),
             ("E03.9", "Hypothyroidism, unspecified"), ("E66.01", "Morbid (severe) obesity due to excess calories"),
             ("E05.90", "Thyrotoxicosis, unspecified")],
    "BARI": [("E66.01", "Morbid (severe) obesity due to excess calories"), ("Z98.84", "Bariatric surgery status"),
             ("K21.9", "Gastro-oesophageal reflux disease without oesophagitis")],
    "DERM": [("L20.9", "Atopic dermatitis, unspecified"), ("L70.0", "Acne vulgaris"), ("L40.0", "Psoriasis vulgaris")],
    "ED": [("R07.9", "Chest pain, unspecified"), ("R10.9", "Unspecified abdominal pain"), ("J06.9", "Acute upper respiratory infection, unspecified"),
           ("R51.9", "Headache, unspecified"), ("S09.90XA", "Unspecified injury of head, initial encounter"),
           ("T78.40XA", "Allergy, unspecified, initial encounter"), ("S61.409A", "Open wound of hand, initial encounter")],
    "ICU": [("A41.9", "Sepsis, unspecified organism"), ("J96.00", "Acute respiratory failure"),
            ("I21.4", "Non-ST elevation myocardial infarction"), ("J18.9", "Pneumonia, unspecified organism"),
            ("I63.9", "Cerebral infarction, unspecified"), ("S06.9X0A", "Unspecified intracranial injury, initial encounter"),
            ("I46.9", "Cardiac arrest, cause unspecified")],
}
COMORB = [("I10", "Essential (primary) hypertension"), ("E11.9", "Type 2 diabetes mellitus without complications"),
          ("E78.5", "Hyperlipidaemia, unspecified"), ("K21.9", "Gastro-oesophageal reflux disease without oesophagitis"),
          ("E66.9", "Obesity, unspecified"), ("F41.9", "Anxiety disorder, unspecified"),
          ("Z87.891", "Personal history of nicotine dependence"), ("J45.909", "Unspecified asthma, uncomplicated")]
INVALID_CODES = ["R99X", "000", "I5O.9", "E11..9", "UNKNOWN", "Z00"]

PAYERS = ["Gulf Shield Insurance", "Emirates CarePlus", "Oasis Health Assurance", "Falcon Medical Cover",
          "Desert Rose Insurance", "Global Expat Health", "Self-pay"]
PAYER_P = [.22, .20, .16, .14, .10, .10, .08]
PAYER_PREFIX = ["GSI", "ECP", "OHA", "FMC", "DRI", "GEH", ""]
PAYER_LAG = [32, 45, 38, 61, 52, 28, 0]   # mean days to payment
DENIALS = {
    "DX-003": "Diagnosis code missing or invalid",
    "AUTH-002": "Prior authorisation not obtained",
    "MN-001": "Medical necessity not established",
    "ELIG-005": "Member not eligible on date of service",
    "DUP-004": "Duplicate claim submission",
}

NATIONALITIES = [("Emirati", "arab", .17), ("Indian", "south_asian", .20), ("Pakistani", "south_asian", .07),
                 ("Egyptian", "arab", .06), ("Filipino", "filipino", .08), ("British", "western", .07),
                 ("Jordanian", "arab", .04), ("Lebanese", "arab", .04), ("Syrian", "arab", .03),
                 ("American", "western", .03), ("Russian", "russian", .03), ("Iranian", "persian", .03),
                 ("Sudanese", "arab", .02), ("Bangladeshi", "south_asian", .03), ("Canadian", "western", .02),
                 ("Saudi", "arab", .02), ("Sri Lankan", "south_asian", .02), ("Other", "western", .04)]
EMIRATI_VARIANTS = ["Emirati", "UAE", "United Arab Emirates", "AE"]
NAMES = {
    "arab": (["Mohammed", "Ahmed", "Omar", "Khalid", "Saeed", "Hamad", "Rashid", "Youssef", "Ali", "Hassan", "Fatima",
              "Mariam", "Aisha", "Noora", "Layla", "Huda", "Sara", "Reem", "Amna", "Shamma", "Salma", "Yara"],
             ["Al Mansoori", "Al Hashimi", "Al Suwaidi", "Al Mazrouei", "Haddad", "Khoury", "Nasser", "Saleh",
              "Abdullah", "Hamdan", "Al Falasi", "Al Marri", "Mahmoud", "Ibrahim", "Youssef", "Farouk"]),
    "south_asian": (["Rahul", "Arjun", "Vikram", "Imran", "Faisal", "Sanjay", "Ravi", "Anil", "Priya", "Ananya",
                     "Deepa", "Ayesha", "Sana", "Kavya", "Meera", "Nadia", "Farhan", "Tariq"],
                    ["Sharma", "Patel", "Nair", "Menon", "Khan", "Iqbal", "Reddy", "Iyer", "Chowdhury", "Hussain",
                     "Pillai", "Qureshi", "Das", "Fernando", "Perera"]),
    "filipino": (["Jose", "Mark", "John Paul", "Carlo", "Maria", "Angelica", "Kristine", "Joy", "Rowena", "Jericho"],
                 ["Santos", "Reyes", "Cruz", "Bautista", "Garcia", "Mendoza", "Dela Cruz", "Ramos", "Villanueva"]),
    "western": (["James", "Oliver", "Thomas", "Daniel", "Michael", "Emma", "Sophie", "Charlotte", "Hannah",
                 "Olivia", "Jack", "Chloe", "Lucas", "Grace"],
                ["Smith", "Johnson", "Brown", "Taylor", "Wilson", "Clarke", "Walker", "Evans", "Martin", "Thompson",
                 "White", "Hughes"]),
    "russian": (["Dmitri", "Sergei", "Alexei", "Ivan", "Olga", "Natalia", "Anastasia", "Elena"],
                ["Ivanov", "Petrov", "Smirnov", "Volkov", "Sokolov", "Popov"]),
    "persian": (["Reza", "Ali", "Mehdi", "Darius", "Shirin", "Leila", "Parisa", "Neda"],
                ["Rahimi", "Hosseini", "Karimi", "Tehrani", "Moradi", "Jafari"]),
}
FEMALE_FIRST = {"Fatima", "Mariam", "Aisha", "Noora", "Layla", "Huda", "Sara", "Reem", "Amna", "Shamma", "Salma", "Yara",
                "Priya", "Ananya", "Deepa", "Ayesha", "Sana", "Kavya", "Meera", "Nadia", "Maria", "Angelica",
                "Kristine", "Joy", "Rowena", "Emma", "Sophie", "Charlotte", "Hannah", "Olivia", "Chloe", "Grace",
                "Olga", "Natalia", "Anastasia", "Elena", "Shirin", "Leila", "Parisa", "Neda"}
EMIRATES = (["Dubai", "Sharjah", "Ajman", "Abu Dhabi", "Ras Al Khaimah", "Umm Al Quwain"], [.78, .14, .04, .02, .01, .01])

LAB_PANELS = {  # code: (name, [(test, name, unit, lo, hi, mean, sd)])
    "CBC": ("Complete blood count", [("HGB", "Haemoglobin", "g/dL", 12.0, 16.5, 13.8, 1.4),
                                     ("WBC", "White blood cells", "10^9/L", 4.0, 11.0, 7.2, 2.0),
                                     ("PLT", "Platelets", "10^9/L", 150, 400, 260, 60)]),
    "BMP": ("Basic metabolic panel", [("NA", "Sodium", "mmol/L", 135, 145, 139, 3),
                                      ("K", "Potassium", "mmol/L", 3.5, 5.1, 4.2, 0.4),
                                      ("CREAT", "Creatinine", "umol/L", 53, 106, 80, 18),
                                      ("GLU", "Glucose", "mg/dL", 70, 100, 98, 18)]),
    "LIPID": ("Lipid panel", [("CHOL", "Total cholesterol", "mg/dL", 0, 200, 190, 35),
                              ("LDL", "LDL cholesterol", "mg/dL", 0, 130, 118, 30),
                              ("HDL", "HDL cholesterol", "mg/dL", 40, 100, 48, 11),
                              ("TRIG", "Triglycerides", "mg/dL", 0, 150, 140, 50)]),
    "HBA1C": ("Haemoglobin A1c", [("HBA1C", "HbA1c", "%", 4.0, 5.6, 5.5, 0.5)]),
    "TROP": ("Troponin I (high sensitivity)", [("TROPI", "Troponin I", "ng/L", 0, 34, 8, 6)]),
    "CRP": ("C-reactive protein", [("CRP", "C-reactive protein", "mg/L", 0, 5, 4, 5)]),
    "LACT": ("Lactate", [("LACT", "Lactate", "mmol/L", 0.5, 2.2, 1.3, 0.5)]),
}

DRUGS = [  # code, name, dose value, unit, route
    ("RX001", "Paracetamol", 1000, "mg", "PO"), ("RX002", "Ibuprofen", 400, "mg", "PO"),
    ("RX003", "Amoxicillin-Clavulanate", 625, "mg", "PO"), ("RX004", "Ceftriaxone", 1000, "mg", "IV"),
    ("RX005", "Enoxaparin", 40, "mg", "SC"), ("RX006", "Metformin", 500, "mg", "PO"),
    ("RX007", "Insulin glargine", 10, "units", "SC"), ("RX008", "Atorvastatin", 40, "mg", "PO"),
    ("RX009", "Furosemide", 40, "mg", "IV"), ("RX010", "Bisoprolol", 5, "mg", "PO"),
    ("RX011", "Aspirin", 81, "mg", "PO"), ("RX012", "Clopidogrel", 75, "mg", "PO"),
    ("RX013", "Pantoprazole", 40, "mg", "IV"), ("RX014", "Ondansetron", 4, "mg", "IV"),
    ("RX015", "Morphine", 2, "mg", "IV"), ("RX016", "Salbutamol", 2.5, "mg", "NEB"),
    ("RX017", "Prednisolone", 20, "mg", "PO"), ("RX018", "Levothyroxine", 50, "mcg", "PO"),
    ("RX019", "Oxytocin", 10, "units", "IV"), ("RX020", "Piperacillin-Tazobactam", 4500, "mg", "IV"),
    ("RX021", "Vancomycin", 1000, "mg", "IV"), ("RX022", "Sodium chloride 0.9%", 1000, "mL", "IV"),
    ("RX023", "Cetirizine", 10, "mg", "PO"), ("RX024", "Omeprazole", 20, "mg", "PO"),
    ("RX025", "Amlodipine", 5, "mg", "PO"), ("RX026", "Heparin", 5000, "units", "SC"),
    ("RX027", "Noradrenaline", 4, "mg", "IV"), ("RX028", "Propofol", 200, "mg", "IV"),
    ("RX029", "Dexamethasone", 8, "mg", "IV"), ("RX030", "Tramadol", 50, "mg", "PO"),
]
DRUG_IDX = {d[0]: i for i, d in enumerate(DRUGS)}
DEPT_DRUGS = {
    "CARD": ["RX011", "RX012", "RX008", "RX010", "RX009", "RX005", "RX025"],
    "ONC": ["RX014", "RX029", "RX001", "RX015", "RX005", "RX022"],
    "ORTH": ["RX001", "RX002", "RX030", "RX005", "RX004", "RX015"],
    "OBGY": ["RX001", "RX019", "RX004", "RX002", "RX005"],
    "PED": ["RX001", "RX003", "RX016", "RX023", "RX017"],
    "GIM": ["RX006", "RX007", "RX004", "RX013", "RX024", "RX005", "RX008", "RX025"],
    "GSURG": ["RX004", "RX020", "RX015", "RX013", "RX005", "RX001"],
    "NEUR": ["RX001", "RX011", "RX008", "RX029", "RX005"],
    "ENDO": ["RX006", "RX007", "RX018", "RX008"],
    "BARI": ["RX013", "RX014", "RX005", "RX001", "RX024"],
    "DERM": ["RX023", "RX017"],
    "ED": ["RX001", "RX002", "RX014", "RX015", "RX022", "RX004", "RX023"],
    "ICU": ["RX027", "RX028", "RX020", "RX021", "RX004", "RX005", "RX013", "RX022", "RX015", "RX026"],
}
STOCKOUTS = [("RX005", d2m(2025, 2, 3), d2m(2025, 2, 24), "RX026"),     # enoxaparin -> heparin
             ("RX004", d2m(2024, 11, 10), d2m(2024, 11, 25), "RX020"),  # ceftriaxone -> pip-taz
             ("RX004", d2m(2025, 9, 1), d2m(2025, 9, 15), "RX020")]


# ---------------------------------------------------------------- helpers
def ts_str(m, fmt="iso"):
    dt = START + timedelta(minutes=float(m))
    if fmt == "iso":
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    if fmt == "dmy":
        return dt.strftime("%d/%m/%Y %H:%M")
    if fmt == "isotz":
        return dt.strftime("%Y-%m-%dT%H:%M:%S") + "+04:00"
    if fmt == "hl7":
        return dt.strftime("%Y%m%d%H%M%S")
    if fmt == "oracle":
        return dt.strftime("%d-%b-%Y %H:%M").upper()
    if fmt == "date":
        return dt.strftime("%Y-%m-%d")
    raise ValueError(fmt)


def ts_vec(minutes):
    secs = np.round(np.asarray(minutes, dtype=np.float64) * 60).astype("int64")
    dt = np.datetime64("2024-01-01T00:00:00") + secs.astype("timedelta64[s]")
    return np.char.replace(np.datetime_as_string(dt, unit="s"), "T", " ")


def season(d):
    """Return (op, ed, ip) multipliers for day index d."""
    date = START + timedelta(days=int(d))
    doy = date.timetuple().tm_yday
    s = 1 + 0.12 * math.cos(2 * math.pi * (doy - 20) / 365.25)
    op, ed, ip = s, s, s
    wd = date.weekday()  # Mon=0 .. Sun=6 ; UAE weekend Sat/Sun
    if wd == 5:
        op *= 0.75
    elif wd == 6:
        op *= 0.55
    if wd in (5, 6):
        ed *= 1.10
    if datetime(2024, 3, 11) <= date <= datetime(2024, 4, 9) or datetime(2025, 3, 1) <= date <= datetime(2025, 3, 29):
        op *= 0.80
        ed *= 0.90
    if date.month in (7, 8):
        op *= 0.85
        ip *= 0.90
    if datetime(2025, 1, 5) <= date <= datetime(2025, 2, 28):   # winter respiratory surge
        ip *= 1.16
        ed *= 1.20
    return op, ed, ip


class Gen:
    def __init__(self, out, scale, seed):
        self.out = out
        self.scale = scale
        self.rng = np.random.default_rng(seed)
        random.seed(seed)
        self.counts = {}
        os.makedirs(out, exist_ok=True)

    def path(self, *p):
        full = os.path.join(self.out, *p)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        return full

    # ------------------------------------------------------------ patients
    def make_patients(self):
        rng = self.rng
        n = max(2000, int(160000 * self.scale))
        self.n_pat = n
        nat_p = np.array([x[2] for x in NATIONALITIES]); nat_p /= nat_p.sum()
        nat = rng.choice(len(NATIONALITIES), n, p=nat_p)
        band = rng.choice(5, n, p=[.18, .03, .55, .18, .06])
        lo = np.array([0, 15, 18, 46, 66])[band]; hi = np.array([15, 18, 46, 66, 91])[band]
        age_days = rng.uniform(lo * 365.25, hi * 365.25)
        self.dob_min = -age_days * 1440                 # minutes relative to START
        self.age = age_days / 365.25
        self.nat = nat
        sex = np.empty(n, dtype=object)
        first = np.empty(n, dtype=object); last = np.empty(n, dtype=object)
        for i in range(n):
            grp = NATIONALITIES[nat[i]][1]
            fn = random.choice(NAMES[grp][0]); ln = random.choice(NAMES[grp][1])
            first[i] = fn; last[i] = ln
            sex[i] = "F" if fn in FEMALE_FIRST else "M"
        self.first, self.last, self.sex = first, last, sex
        self.payer = rng.choice(len(PAYERS), n, p=PAYER_P)
        self.mrn = np.array([f"AHD{1000000 + i:07d}" for i in range(n)])
        w = rng.lognormal(0, 1.0, n)
        self.w_all = w / w.sum()
        kids = np.where(self.age < 15)[0]
        women = np.where((sex == "F") & (self.age >= 18) & (self.age <= 45))[0]
        adults = np.where(self.age >= 15)[0]
        self.pools = {"kids": kids, "women": women, "adults": adults, "all": np.arange(n)}
        self.pool_w = {k: w[v] / w[v].sum() for k, v in self.pools.items()}

    def pick_patients(self, depts):
        out = np.empty(len(depts), dtype=np.int64)
        for d in set(depts.tolist()):
            idx = np.where(depts == d)[0]
            pool = "kids" if d == "PED" else "women" if d == "OBGY" else "all" if d == "ED" else "adults"
            out[idx] = self.rng.choice(self.pools[pool], len(idx), p=self.pool_w[pool])
        return out

    # ------------------------------------------------------------ encounters
    def make_encounters(self):
        rng, sc = self.rng, self.scale
        cols = {k: [] for k in ["etype", "dept", "admit", "disc", "pat"]}

        def add(etype, dept, admit, disc, pat):
            cols["etype"].append(np.full(len(admit), etype)); cols["dept"].append(dept)
            cols["admit"].append(admit); cols["disc"].append(disc); cols["pat"].append(pat)

        days = np.arange(NDAYS)
        mult = np.array([season(d) for d in days])
        n_op = rng.poisson(870 * sc * mult[:, 0]); n_ed = rng.poisson(190 * sc * mult[:, 1])
        n_day = rng.poisson(60 * sc * mult[:, 0]); n_ip = rng.poisson(53 * sc * mult[:, 2])

        def day_times(counts, hours, hw):
            d = np.repeat(days, counts)
            h = rng.choice(hours, len(d), p=hw / hw.sum())
            return d * 1440 + h * 60 + rng.uniform(0, 60, len(d))

        # outpatient
        a = day_times(n_op, np.arange(8, 21), np.array([6, 9, 10, 10, 8, 7, 8, 9, 9, 8, 7, 5, 3], float))
        dep = rng.choice(list(OP_DEPT_P), len(a), p=list(OP_DEPT_P.values()))
        add("OP", dep, a, a + rng.uniform(15, 60, len(a)), self.pick_patients(dep))
        # day case
        a = day_times(n_day, np.arange(7, 13), np.ones(6))
        dep = rng.choice(list(DAY_DEPT_P), len(a), p=list(DAY_DEPT_P.values()))
        add("DAY", dep, a, a + rng.uniform(240, 540, len(a)), self.pick_patients(dep))

        # inpatient ward stays (+ readmissions) -------------------------
        hw = np.array([2, 1.5, 1, 1, 1, 1, 1.5, 2.5, 4, 5, 5, 5, 4.5, 4, 4, 4, 4, 4, 4, 4, 3.5, 3, 3, 2.5])
        a = day_times(n_ip, np.arange(24), hw)
        dep = rng.choice(list(IP_DEPT_P), len(a), p=list(IP_DEPT_P.values()))
        pat = self.pick_patients(dep)
        med = np.array([IP_LOS_MEDIAN[d] for d in dep])
        los = np.maximum(0.3, rng.lognormal(np.log(med), 0.6)) * 1440
        prim = self.pick_primary(dep)
        hf = np.array([p == "I50.9" for p in prim])
        readm = rng.random(len(a)) < np.where(hf, 0.24, 0.07)
        ra = a[readm] + los[readm] + rng.uniform(2, 30, readm.sum()) * 1440
        keep = ra < END_MIN - 1440
        ra = ra[keep]; rdep = dep[readm][keep]; rpat = pat[readm][keep]; rprim = prim[readm][keep]
        rmed = np.array([IP_LOS_MEDIAN[d] for d in rdep])
        rlos = np.maximum(0.3, rng.lognormal(np.log(rmed) + 0.15, 0.6)) * 1440
        ip_a = np.concatenate([a, ra]); ip_dep = np.concatenate([dep, rdep]); ip_pat = np.concatenate([pat, rpat])
        ip_d = np.concatenate([a + los, ra + rlos]); ip_prim = np.concatenate([prim, rprim])
        ip_readmit = np.concatenate([np.zeros(len(a), bool), np.ones(len(ra), bool)])

        # bed assignment on ward beds; no free bed -> OVERFLOW (boarded)
        n_beds = max(8, int(round(228 * min(1, sc) if sc < 1 else 228)))
        beds = [f"W{1 + b // 29}-{b % 29 + 1:02d}" for b in range(n_beds)]
        heap = [(0.0, b) for b in beds]; heapq.heapify(heap)
        order = np.argsort(ip_a)
        ip_bed = np.empty(len(ip_a), dtype=object)
        for i in order:
            free_at, b = heap[0]
            if free_at <= ip_a[i]:
                heapq.heapreplace(heap, (ip_d[i], b)); ip_bed[i] = b
            else:
                ip_bed[i] = "OVERFLOW"
        # daily midnight census -> occupancy
        diff = np.zeros(NDAYS + 2)
        s_day = np.floor(ip_a / 1440).astype(int) + 1; e_day = np.floor(ip_d / 1440).astype(int) + 1
        np.add.at(diff, np.clip(s_day, 0, NDAYS + 1), 1); np.add.at(diff, np.clip(e_day, 0, NDAYS + 1), -1)
        census = np.cumsum(diff)[:NDAYS]
        self.occupancy = census / n_beds
        self.ward_beds = n_beds

        # ED, waits depend on ward occupancy (boarding blocks the ED)
        a = day_times(n_ed, np.arange(24), np.array([3, 2.5, 2, 1.5, 1.2, 1.2, 1.5, 2, 3, 4, 4.5, 4.5, 4.5, 4.5,
                                                     4.5, 4.5, 5, 5.5, 6, 6.5, 6.5, 6, 5, 4], float))
        dep = np.full(len(a), "ED")
        occ = self.occupancy[np.minimum((a // 1440).astype(int), NDAYS - 1)]
        triage = rng.choice([1, 2, 3, 4, 5], len(a), p=[.02, .12, .45, .31, .10])
        crowd = 1 + 2.2 * np.clip(occ - 0.85, 0, 0.2) / 0.15
        wait = rng.gamma(2.0, 18.0 * crowd) * np.where(triage <= 2, 0.15, 1.0)
        dur = rng.uniform(60, 360, len(a)) + wait
        self.ed_extra = {"triage": triage, "wait": np.round(wait).astype(int)}
        add("ED", dep, a, a + dur, self.pick_patients(dep))

        # ICU timeline (beds x stays) -----------------------------------
        n_icu = max(2, int(round(24 * sc))) if sc < 1 else 24
        icu = {k: [] for k in ["admit", "disc", "bed", "event_min", "event_type", "deceased"]}
        for b in range(n_icu):
            t = rng.uniform(0, 1440)
            while t < END_MIN - 1440:
                los = max(0.4, rng.lognormal(np.log(3.0), 0.7)) * 1440
                d = min(t + los, END_MIN - 1)
                ev, et, dec = -1.0, "", False
                if d > VITALS_START_MIN and (d - t) > 12 * 60 and rng.random() < 0.12:
                    lo_e = max(t + 360, VITALS_START_MIN + 360)
                    if lo_e < d - 60:
                        ev = rng.uniform(lo_e, d - 60)
                        et = rng.choice(["RAPID_RESPONSE", "INTUBATION", "CARDIAC_ARREST"], p=[.6, .25, .15])
                        dec = (et == "CARDIAC_ARREST" and rng.random() < 0.4)
                        if dec:
                            d = ev + 30
                icu["admit"].append(t); icu["disc"].append(d); icu["bed"].append(f"ICU-{b + 1:02d}")
                icu["event_min"].append(ev); icu["event_type"].append(et); icu["deceased"].append(dec)
                t = d + rng.exponential(0.6 * 1440)
        icu = {k: np.array(v) for k, v in icu.items()}
        icu_dep = np.full(len(icu["admit"]), "ICU")
        icu_pat = self.rng.choice(self.pools["adults"], len(icu_dep), p=self.pool_w["adults"])
        self.icu = icu

        # combine ----------------------------------------------------------
        etype = np.concatenate(cols["etype"] + [np.full(len(ip_a), "IP"), np.full(len(icu_dep), "IP")])
        dept = np.concatenate(cols["dept"] + [ip_dep, icu_dep])
        admit = np.concatenate(cols["admit"] + [ip_a, icu["admit"]])
        disc = np.concatenate(cols["disc"] + [ip_d, icu["disc"]])
        pat = np.concatenate(cols["pat"] + [ip_pat, icu_pat])
        n = len(admit)
        bed = np.full(n, "", dtype=object); triage = np.zeros(n, int); wait = np.full(n, -1)
        readmit = np.zeros(n, bool); icu_idx = np.full(n, -1)
        off = sum(len(x) for x in cols["admit"][:2])       # OP + DAY
        n_ed_ = len(cols["admit"][2])
        triage[off:off + n_ed_] = self.ed_extra["triage"]; wait[off:off + n_ed_] = self.ed_extra["wait"]
        off_ip = off + n_ed_
        bed[off_ip:off_ip + len(ip_a)] = ip_bed; readmit[off_ip:off_ip + len(ip_a)] = ip_readmit
        off_icu = off_ip + len(ip_a)
        bed[off_icu:] = icu["bed"]; icu_idx[off_icu:] = np.arange(len(icu_dep))
        prim = np.empty(n, dtype=object)
        prim[off_ip:off_ip + len(ip_a)] = ip_prim
        rest = np.ones(n, bool); rest[off_ip:off_ip + len(ip_a)] = False
        prim[rest] = self.pick_primary(dept[rest])

        o = np.argsort(admit, kind="stable")
        E = {"etype": etype[o], "dept": dept[o], "admit": admit[o], "disc": disc[o], "pat": pat[o], "bed": bed[o],
             "triage": triage[o], "wait": wait[o], "readmit": readmit[o], "icu_idx": icu_idx[o], "prim": prim[o]}
        E["id"] = np.array([f"ENC{100000000 + i:09d}" for i in range(n)])
        disp = rng.choice(["HOME", "HOME_HEALTH", "TRANSFER", "LEFT_AMA", "REHAB", "DECEASED"], n,
                          p=[.86, .04, .03, .02, .035, .015])
        disp = np.where(E["etype"] == "IP", disp, np.where(E["etype"] == "ED",
                        rng.choice(["DISCHARGED", "ADMITTED", "LEFT_WITHOUT_BEING_SEEN"], n, p=[.82, .14, .04]), "COMPLETED"))
        icu_rows = np.where(E["icu_idx"] >= 0)[0]
        dec = self.icu["deceased"][E["icu_idx"][icu_rows]]
        icu_disp = np.where(dec, "DECEASED", rng.choice(["TRANSFER_TO_WARD", "HOME", "DECEASED"], len(icu_rows),
                                                        p=[.82, .08, .10]))
        disp[icu_rows] = icu_disp
        E["disp"] = disp
        # ED patients who leave without being seen are the long waits
        E["disp"][(E["etype"] == "ED") & (E["wait"] > 240) & (rng.random(n) < 0.5)] = "LEFT_WITHOUT_BEING_SEEN"
        n_att = {d: max(3, int(12 * min(1, sc * 5))) for d in DEPTS}
        E["attending"] = np.array([f"DR{DEPTS.index(d) * 100 + rng.integers(1, n_att[d] + 1):04d}" for d in E["dept"]])
        # MRN as written by each source (duplicate-patient and legacy problems)
        self.E = E
        self.n_enc = n

    def pick_primary(self, depts):
        out = np.empty(len(depts), dtype=object)
        for d in set(depts.tolist()):
            idx = np.where(depts == d)[0]
            codes = DX[d]
            w = np.array([1 / (1 + 0.45 * i) for i in range(len(codes))]); w /= w.sum()
            out[idx] = np.array([c[0] for c in codes], dtype=object)[self.rng.choice(len(codes), len(idx), p=w)]
        return out

    # ------------------------------------------------------------ duplicate patients / MRNs
    def make_mrn_views(self):
        rng, E = self.rng, self.E
        n = self.n_pat
        dup = rng.random(n) < 0.03
        self.dup_of = np.where(dup)[0]
        self.dup_mrn = {int(i): f"AHD{2000000 + k:07d}" for k, i in enumerate(self.dup_of)}
        mrn_enc = self.mrn[E["pat"]].astype(object)
        use_dup = np.array([int(p) in self.dup_mrn for p in E["pat"]]) & (rng.random(self.n_enc) < 0.35)
        for i in np.where(use_dup)[0]:
            mrn_enc[i] = self.dup_mrn[int(E["pat"][i])]
        E["mrn"] = mrn_enc
        E["legacy"] = (E["admit"] < LEGACY_END_MIN) & (rng.random(self.n_enc) < 0.06)

    # ------------------------------------------------------------ diagnoses
    def write_diagnoses(self):
        rng, E = self.rng, self.E
        n = self.n_enc
        missing = rng.random(n) < 0.03
        n_sec = rng.poisson(np.where(E["etype"] == "IP", 1.3, np.where(E["etype"] == "ED", 0.5, 0.7)))
        desc = {c: dsc for lst in DX.values() for c, dsc in lst}
        desc.update({c: dsc for c, dsc in COMORB})
        invalid = np.zeros(n, bool)
        rows = 0
        with open(self.path("ehr_cerner", "diagnoses.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["encounter_id", "seq", "icd10_code", "description", "dx_type", "recorded_at"])
            for i in range(n):
                seq = 1
                codes = []
                if not missing[i]:
                    codes.append((E["prim"][i], "PRIMARY"))
                for c in rng.choice(len(COMORB), n_sec[i], replace=False) if n_sec[i] <= len(COMORB) else []:
                    codes.append((COMORB[c][0], "SECONDARY"))
                for code, typ in codes:
                    r = rng.random()
                    out_code, d = code, desc.get(code, "")
                    if r < 0.06:
                        out_code = code.replace(".", "")
                    elif r < 0.08:
                        out_code = code.lower()
                    elif r < 0.087:
                        out_code = random.choice(INVALID_CODES); d = ""
                        if typ == "PRIMARY":
                            invalid[i] = True
                    w.writerow([E["id"][i], seq, out_code, d, typ, ts_str(E["admit"][i] + rng.uniform(5, 240))])
                    seq += 1; rows += 1
        E["dx_missing"] = missing; E["dx_invalid"] = invalid
        self.counts["ehr_cerner/diagnoses.csv"] = rows

    # ------------------------------------------------------------ encounters + patients CSV
    def write_encounters(self):
        rng, E = self.rng, self.E
        n = self.n_enc
        admit_iso = ts_vec(E["admit"]); disc_iso = ts_vec(E["disc"])
        fmt_r = rng.random(n)
        dept_dirty = rng.random(n) < 0.08
        bad_order = (rng.random(n) < 0.003)
        open_ip = (E["etype"] == "IP") & (rng.random(n) < 0.01)
        dup_rows = rng.random(n) < 0.004
        rows = 0
        with open(self.path("ehr_cerner", "encounters.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["encounter_id", "mrn", "encounter_type", "department", "attending_id", "admit_ts",
                        "discharge_ts", "bed_id", "triage_level", "ed_wait_minutes", "discharge_disposition",
                        "readmission_flag", "source_system"])
            for i in range(n):
                a, d = admit_iso[i], disc_iso[i]
                if fmt_r[i] < 0.05:
                    a, d = ts_str(E["admit"][i], "dmy"), ts_str(E["disc"][i], "dmy")
                elif fmt_r[i] < 0.08:
                    a, d = ts_str(E["admit"][i], "isotz"), ts_str(E["disc"][i], "isotz")
                if bad_order[i]:
                    d = ts_str(E["admit"][i] - rng.uniform(30, 600))
                if open_ip[i]:
                    d = ""
                dep = random.choice(DEPT_VARIANTS[E["dept"][i]]) if dept_dirty[i] else E["dept"][i]
                mrn = E["mrn"][i]
                src = "CERNER"
                if E["legacy"][i]:
                    mrn = mrn[3:]; src = "LEGACY_PAS"
                row = [E["id"][i], mrn, E["etype"][i], dep, E["attending"][i], a, d, E["bed"][i],
                       E["triage"][i] if E["triage"][i] else "", E["wait"][i] if E["wait"][i] >= 0 else "",
                       E["disp"][i], "Y" if E["readmit"][i] else "N", src]
                w.writerow(row); rows += 1
                if dup_rows[i]:
                    w.writerow(row); rows += 1
        self.counts["ehr_cerner/encounters.csv"] = rows

    def write_patients(self):
        rng = self.rng
        first_seen = np.full(self.n_pat, np.inf)
        np.minimum.at(first_seen, self.E["pat"], self.E["admit"])
        reg = np.where(np.isfinite(first_seen),
                       np.minimum(first_seen - rng.uniform(0, 5 * 365, self.n_pat) * 1440 * (rng.random(self.n_pat) < .7),
                                  first_seen),
                       rng.uniform(-10 * 365, NDAYS, self.n_pat) * 1440)

        def phone():
            digits = f"5{rng.integers(0, 9)}{rng.integers(1000000, 9999999)}"
            r = rng.random()
            if r < .6:
                return f"+971 {digits[:2]} {digits[2:5]} {digits[5:]}"
            if r < .9:
                return "0" + digits
            if r < .98:
                return f"971-{digits[:2]}-{digits[2:]}"
            return ""

        def nat_str(k):
            name = NATIONALITIES[k][0]
            return random.choice(EMIRATI_VARIANTS) if name == "Emirati" else name

        rows = 0
        with open(self.path("ehr_cerner", "patients.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["mrn", "first_name", "last_name", "gender", "date_of_birth", "nationality", "emirate",
                        "mobile", "insurance_payer", "policy_number", "registration_date"])
            for i in range(self.n_pat):
                dob = ts_str(self.dob_min[i], "date")
                r = rng.random()
                if r < 0.05:
                    dob = (START + timedelta(minutes=float(self.dob_min[i]))).strftime("%d/%m/%Y")
                elif r < 0.06:
                    dob = ""
                p = self.payer[i]
                pol = f"{PAYER_PREFIX[p]}-{rng.integers(10000000, 99999999)}" if PAYERS[p] != "Self-pay" else ""
                em = rng.choice(EMIRATES[0], p=EMIRATES[1])
                row = [self.mrn[i], self.first[i], self.last[i], self.sex[i], dob, nat_str(self.nat[i]), em,
                       phone(), PAYERS[p], pol, ts_str(reg[i], "date")]
                w.writerow(row); rows += 1
                if i in self.dup_mrn:
                    fn, ln = self.first[i], self.last[i]
                    v = rng.random()
                    if v < .3:
                        ln = ln.upper()
                    elif v < .55:
                        fn, ln = ln, fn
                    elif v < .8:
                        fn = fn + " "
                    else:
                        ln = ln.replace("Al ", "Al-") if ln.startswith("Al ") else ln + "e"
                    dob2 = (START + timedelta(minutes=float(self.dob_min[i]))).strftime("%d/%m/%Y")
                    w.writerow([self.dup_mrn[i], fn, ln, self.sex[i], dob2, nat_str(self.nat[i]), em, phone(),
                                PAYERS[p], pol, ts_str(reg[i] + rng.uniform(30, 400) * 1440, "date")])
                    rows += 1
        self.counts["ehr_cerner/patients.csv"] = rows

    # ------------------------------------------------------------ labs (HL7 v2 ORU^R01)
    def write_labs(self):
        rng, E = self.rng, self.E
        files, msgs, results = {}, 0, 0
        ctrl = 0
        late_buf = []

        def fh(month):
            if month not in files:
                files[month] = open(self.path("lis_hl7", f"oru_{month}.hl7"), "w")
            return files[month]

        for i in range(self.n_enc):
            et, dep = E["etype"][i], E["dept"][i]
            if et == "OP" and rng.random() > 0.35:
                continue
            if et == "ED" and rng.random() > 0.70:
                continue
            if et == "DAY" and rng.random() > 0.60:
                continue
            a, dsc = E["admit"][i], E["disc"][i]
            prim = str(E["prim"][i])
            if et == "IP":
                n_days = max(1, int((dsc - a) / 1440))
                times = [a + 60] + [np.floor(a / 1440 + k) * 1440 + 300 + rng.uniform(0, 120) for k in range(1, n_days + 1)]
                times = [t for t in times if t < dsc] or [a + 60]
                panels_per = 2 if dep == "ICU" else 1
            else:
                times = [a + rng.uniform(5, 40)]
                panels_per = 3 if et == "ED" else 2
            sick = dep in ("ICU", "ED") or et == "IP"
            for t in times:
                if dep == "ICU":
                    choices = ["CBC", "BMP", "LACT", "CRP"]
                elif prim.startswith("I21") or (et == "ED" and prim == "R07.9"):
                    choices = ["TROP", "CBC", "BMP"]
                elif prim.startswith("E11") or dep == "ENDO":
                    choices = ["HBA1C", "BMP", "LIPID"]
                elif dep == "CARD":
                    choices = ["LIPID", "BMP", "TROP"]
                else:
                    choices = ["CBC", "BMP", "CRP", "LIPID"]
                k = min(len(choices), max(1, rng.poisson(panels_per)))
                for pc in rng.choice(choices, k, replace=False):
                    ctrl += 1
                    res_t = t + rng.uniform(30, 240)
                    if rng.random() < 0.003:
                        res_t = t - rng.uniform(5, 60)       # result before order (clock problem)
                    p = E["pat"][i]
                    lines = [
                        f"MSH|^~\\&|AHD_LIS|AHD_LAB|CERNER_EHR|AHD|{ts_str(res_t, 'hl7')}||ORU^R01|LAB{ctrl:010d}|P|2.5.1",
                        f"PID|1||{E['mrn'][i]}^^^AHD^MR||{str(self.last[p]).upper()}^{self.first[p]}||"
                        f"{ts_str(self.dob_min[p], 'hl7')[:8]}|{self.sex[p]}",
                        f"PV1|1|{'I' if et == 'IP' else 'E' if et == 'ED' else 'O'}|{dep}|||||{E['attending'][i]}|||||||||||"
                        f"{E['id'][i]}",
                        f"OBR|1|ORD{ctrl:010d}|FIL{ctrl:010d}|{pc}^{LAB_PANELS[pc][0]}^L|||{ts_str(t, 'hl7')}|||||||||||||||"
                        f"{ts_str(res_t, 'hl7')}|||F",
                    ]
                    for j, (code, name, unit, lo, hi, mean, sd) in enumerate(LAB_PANELS[pc][1], 1):
                        v = rng.normal(mean, sd * (1.6 if sick else 1.0))
                        if code == "TROPI" and prim.startswith("I21"):
                            v = rng.uniform(80, 2500)
                        if code == "HBA1C" and prim.startswith("E11"):
                            v = rng.normal(8.2, 1.3)
                        if code == "LACT" and dep == "ICU" and rng.random() < .25:
                            v = rng.uniform(2.5, 8)
                        if code == "GLU" and prim.startswith("E11"):
                            v = rng.normal(185, 45)
                        v = max(v, 0.1)
                        u, rlo, rhi = unit, lo, hi
                        if code == "GLU" and rng.random() < 0.10:      # unit inconsistency
                            v, u, rlo, rhi = v / 18.0, "mmol/L", 3.9, 5.6
                        flag = "H" if v > rhi else "L" if v < rlo else "N"
                        if rng.random() < 0.02:
                            flag = ""
                        dec = 2 if v < 10 else 1 if v < 100 else 0
                        lines.append(f"OBX|{j}|NM|{code}^{name}^L||{v:.{dec}f}|{u}|{rlo}-{rhi}|{flag}|||F|||"
                                     f"{ts_str(res_t, 'hl7')}")
                        results += 1
                    if rng.random() < 0.003:                  # truncated message
                        lines = lines[:5]
                        lines[-1] = lines[-1][: len(lines[-1]) // 2]
                    msg = "\n".join(lines) + "\n\n"
                    month = ts_str(res_t, "date")[:7]
                    if rng.random() < 0.01 and month < "2025-12":  # arrives late, lands in next month's file
                        y, m = int(month[:4]), int(month[5:])
                        month = f"{y + (m == 12)}-{(m % 12) + 1:02d}"
                    fh(month).write(msg); msgs += 1
                    if rng.random() < 0.008:                  # resent duplicate
                        fh(month).write(msg); msgs += 1
        for f in files.values():
            f.close()
        self.counts["lis_hl7/*.hl7 (messages)"] = msgs
        self.counts["lis_hl7/*.hl7 (OBX results)"] = results

    # ------------------------------------------------------------ pharmacy (JSON lines, schema drift)
    def write_pharmacy(self):
        rng, E = self.rng, self.E
        files = {}
        rows = 0
        self.disp_day, self.disp_drug, self.disp_store, self.disp_ok = [], [], [], []
        did = 0
        for i in range(self.n_enc):
            et, dep = E["etype"][i], E["dept"][i]
            a, dsc = E["admit"][i], E["disc"][i]
            if et == "IP":
                k = rng.poisson(max(1, (dsc - a) / 1440) * (4.5 if dep == "ICU" else 2.6))
            elif et == "ED":
                k = rng.poisson(1.2)
            elif et == "DAY":
                k = rng.poisson(2.0)
            else:
                k = rng.poisson(0.55)
            if k == 0:
                continue
            store = 1 if dep == "ICU" else 2 if et == "ED" else 0
            drugs = DEPT_DRUGS[dep]
            for _ in range(k):
                did += 1
                code = drugs[rng.integers(len(drugs))]
                t = a + rng.uniform(0, max(30, dsc - a))
                status, delay, sub = "DISPENSED", 0, None
                for scode, s0, s1, subst in STOCKOUTS:
                    if code == scode and s0 <= t < s1:
                        r = rng.random()
                        if r < .55:
                            status, delay = "DELAYED_STOCKOUT", int(rng.uniform(120, 720))
                        elif r < .85:
                            status, sub = "SUBSTITUTED", subst
                give = sub or code
                dcode, dname, dose, unit, route = DRUGS[DRUG_IDX[give]]
                qty = int(rng.integers(1, 4))
                t_out = t + delay
                month = ts_str(t_out, "date")[:7]
                if t_out < SCHEMA_V2_MIN:
                    rec = {"dispense_id": f"D{did:09d}", "mrn": E["mrn"][i], "encounter_id": E["id"][i],
                           "drug_code": dcode, "drug_name": dname,
                           "dose_mg": dose if unit == "mg" and rng.random() > .01 else None,
                           "route": route if rng.random() > .02 else None, "qty": qty,
                           "dispensed_at": ts_str(t_out), "pharmacist_id": f"PH{rng.integers(1, 40):03d}",
                           "status": status}
                    if unit != "mg":
                        rec["dose_note"] = f"{dose} {unit}"
                    if delay:
                        rec["delay_minutes"] = delay
                    if sub:
                        rec["substituted_for"] = code
                else:
                    ts_val = int((START + timedelta(minutes=float(t_out)) - datetime(1970, 1, 1)).total_seconds() * 1000) - 4 * 3600 * 1000 \
                        if rng.random() < .7 else ts_str(t_out, "isotz")
                    rec = {"id": f"D{did:09d}", "schema_version": 2,
                           "patient": {"mrn": E["mrn"][i], "encounter": E["id"][i]},
                           "drug": {"code": dcode, "name": dname},
                           "dose": {"value": dose, "unit": unit} if rng.random() > .01 else None,
                           "route": route if rng.random() > .02 else None, "quantity": qty,
                           "timestamp": ts_val, "pharmacist": f"PH{rng.integers(1, 40):03d}",
                           "status": status, "delay_minutes": delay or None,
                           "substituted_for": code if sub else None}
                if month not in files:
                    files[month] = open(self.path("pharmacy_api", f"dispense_{month}.jsonl"), "w")
                files[month].write(json.dumps(rec, ensure_ascii=False) + "\n"); rows += 1
                self.disp_day.append(int(t_out // 1440)); self.disp_drug.append(DRUG_IDX[give])
                self.disp_store.append(store); self.disp_ok.append(qty)
        for f in files.values():
            f.close()
        self.counts["pharmacy_api/*.jsonl"] = rows

    # ------------------------------------------------------------ ERP inventory (XML)
    def write_inventory(self):
        rng = self.rng
        stores = ["MAIN_PHARMACY", "ICU_SATELLITE", "ED_SATELLITE"]
        dd = np.array(self.disp_day); dg = np.array(self.disp_drug); ds = np.array(self.disp_store)
        dq = np.array(self.disp_ok)
        use = np.zeros((NDAYS + 2, len(DRUGS), 3))
        np.add.at(use, (np.minimum(dd, NDAYS + 1), dg, ds), dq)
        cost = {d[0]: round(float(rng.uniform(1.5, 180)), 2) for d in DRUGS}
        txn = 0
        rows = 0
        files = {}

        def out(month):
            if month not in files:
                f = open(self.path("erp_oracle", f"inventory_{month}.xml"), "w")
                f.write('<?xml version="1.0" encoding="UTF-8"?>\n<InventoryTransactions source="ORACLE_CLOUD_SCM" '
                        f'facility="AHD" period="{month}">\n')
                files[month] = f
            return files[month]

        def emit(m, item, store, typ, qty, unit_cost=True):
            nonlocal txn, rows
            txn += 1
            tid = f"INV{txn:09d}"
            if rng.random() < 0.005:
                tid = f"INV{max(1, txn - 1):09d}"                 # duplicate id
            ts = ts_str(m, "oracle") if rng.random() < 0.15 else ts_str(m, "isotz")
            code, name = DRUGS[item][0], DRUGS[item][1]
            uc = f'<UnitCost currency="AED">{cost[code]}</UnitCost>' if unit_cost and rng.random() > .01 else "<UnitCost/>"
            out(ts_str(m, "date")[:7]).write(
                f'  <Txn id="{tid}"><ItemCode>{code}</ItemCode><ItemName>{name}</ItemName><Type>{typ}</Type>'
                f'<Qty>{qty}</Qty>{uc}<Store>{stores[store]}</Store><Timestamp>{ts}</Timestamp></Txn>\n')
            rows += 1

        for d in range(NDAYS):
            for s in range(3):
                for g in np.nonzero(use[d, :, s])[0]:
                    q = int(use[d, g, s])
                    parts = rng.multinomial(q, [.4, .35, .25])
                    for sh, pq in enumerate(parts):
                        if pq:
                            emit(d * 1440 + 480 * sh + rng.uniform(0, 470), g, s, "ISSUE", int(pq), unit_cost=False)
            if (START + timedelta(days=d)).weekday() == 6:      # Sunday receipts
                for g in range(len(DRUGS)):
                    code = DRUGS[g][0]
                    blocked = any(code == sc and s0 - 7 * 1440 <= d * 1440 < s1 for sc, s0, s1, _ in STOCKOUTS)
                    if blocked:
                        continue
                    for s in range(3):
                        need = use[max(0, d - 7):d, g, s].sum()
                        if need <= 0:
                            continue
                        q = int(need * rng.uniform(1.0, 1.25)) + 1
                        if rng.random() < 0.003:
                            q = -q
                        emit(d * 1440 + rng.uniform(420, 720), g, s, "RECEIPT", q)
            if (START + timedelta(days=d)).day == 28:              # monthly stock count
                for g in range(len(DRUGS)):
                    for s in range(3):
                        if rng.random() < 0.3:
                            emit(d * 1440 + 1200, g, s, "ADJUSTMENT", int(rng.integers(-6, 7)))
        for f in files.values():
            f.write("</InventoryTransactions>\n"); f.close()
        self.counts["erp_oracle/*.xml (transactions)"] = rows

    # ------------------------------------------------------------ claims (Oracle billing CSV)
    def write_claims(self):
        rng, E = self.rng, self.E
        n = self.n_enc
        payer = self.payer[E["pat"]]
        base = {"OP": (300, 1200), "ED": (800, 4000), "DAY": (3000, 12000)}
        cid = 0
        rows = 0
        denied_enc = np.zeros(n, bool)
        today = END_MIN
        with open(self.path("billing_oracle", "claims.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["claim_id", "encounter_id", "mrn", "payer", "submitted_date", "total_amount", "status",
                        "denial_code", "denial_reason", "paid_amount", "paid_date", "resubmission_of"])

            def amount_str(x):
                r = rng.random()
                if r < .10:
                    return f"AED {x:,.2f}"
                if r < .12:
                    return ""
                return f"{x:.2f}"

            for i in range(n):
                p = payer[i]
                if PAYERS[p] == "Self-pay":
                    continue
                et, dep = E["etype"][i], E["dept"][i]
                if et == "IP":
                    los = (E["disc"][i] - E["admit"][i]) / 1440
                    amt = (rng.uniform(40000, 250000) if dep == "ICU" else rng.uniform(6000, 15000) * max(1, los))
                else:
                    amt = rng.uniform(*base[et])
                amt = round(amt, 2)
                sub = E["disc"][i] + rng.uniform(1, 12) * 1440
                if sub >= today:
                    continue
                pd = 0.05
                code = None
                if E["dx_missing"][i] or E["dx_invalid"][i]:
                    pd, code = 0.65, "DX-003"
                elif PAYERS[p] == "Falcon Medical Cover" and dep in ("ORTH", "BARI") and et in ("IP", "DAY"):
                    pd, code = 0.38, "AUTH-002"
                status, dcode, paid, pdate = "PAID", "", amt, ""
                if rng.random() < pd:
                    status = "DENIED"
                    dcode = code or rng.choice(["MN-001", "ELIG-005", "AUTH-002"], p=[.5, .3, .2])
                    paid = 0.0
                    denied_enc[i] = True
                elif rng.random() < 0.06:
                    status, paid = "PARTIAL", round(amt * rng.uniform(.5, .9), 2)
                pay_t = sub + rng.exponential(PAYER_LAG[p]) * 1440
                if status != "DENIED" and pay_t >= today:
                    status, paid = "PENDING", ""
                elif status != "DENIED":
                    pdate = ts_str(pay_t, "date")
                cid += 1
                enc_id = E["id"][i] if rng.random() > 0.008 else f"ENC{rng.integers(900000000, 999999999)}"
                w.writerow([f"CLM{cid:09d}", enc_id, E["mrn"][i], PAYERS[p], ts_str(sub, "date"), amount_str(amt),
                            status, dcode, DENIALS.get(dcode, ""), paid, pdate, ""]); rows += 1
                first_id = f"CLM{cid:09d}"
                if rng.random() < 0.01:                              # accidental duplicate submission
                    cid += 1
                    w.writerow([f"CLM{cid:09d}", E["id"][i], E["mrn"][i], PAYERS[p], ts_str(sub + 1440, "date"),
                                amount_str(amt), "DENIED", "DUP-004", DENIALS["DUP-004"], 0.0, "", ""]); rows += 1
                if status == "DENIED" and rng.random() < 0.4:        # corrected resubmission
                    rs = sub + rng.uniform(15, 45) * 1440
                    if rs < today:
                        cid += 1
                        ok = rng.random() < 0.8
                        pt = rs + rng.exponential(PAYER_LAG[p]) * 1440
                        st = "PAID" if ok and pt < today else "PENDING" if ok else "DENIED"
                        w.writerow([f"CLM{cid:09d}", E["id"][i], E["mrn"][i], PAYERS[p], ts_str(rs, "date"),
                                    amount_str(amt), st, "" if ok else dcode, "" if ok else DENIALS[dcode],
                                    amt if st == "PAID" else (0.0 if st == "DENIED" else ""),
                                    ts_str(pt, "date") if st == "PAID" else "", first_id]); rows += 1
        E["denied"] = denied_enc
        self.counts["billing_oracle/claims.csv"] = rows

    # ------------------------------------------------------------ ICU vitals stream + events
    def write_vitals(self):
        rng, E, icu = self.rng, self.E, self.icu
        enc_of_icu = np.full(len(icu["admit"]), -1)
        rows_icu = np.where(E["icu_idx"] >= 0)[0]
        enc_of_icu[E["icu_idx"][rows_icu]] = rows_icu
        chunks = []
        with open(self.path("icu_monitors", "icu_events.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["event_id", "bed_id", "mrn", "encounter_id", "event_ts", "event_type", "outcome"])
            ev_id = 0
            for k in range(len(icu["admit"])):
                a, d = icu["admit"][k], icu["disc"][k]
                s, e = max(a, VITALS_START_MIN), min(d, END_MIN)
                if e - s < 1:
                    continue
                m = np.arange(np.ceil(s), e, 1.0)
                nmin = len(m)
                base = np.array([rng.normal(88, 10), rng.normal(96.5, 1.2), rng.normal(18, 2.5),
                                 rng.normal(122, 12), rng.normal(70, 8), rng.normal(37.1, 0.3)])
                noise_sd = np.array([4, 0.8, 1.5, 6, 4, 0.08])
                v = base[None, :] + rng.normal(0, 1, (nmin, 6)) * noise_sd
                kern = np.ones(9) / 9
                for c in range(6):
                    v[:, c] = base[c] + np.convolve(v[:, c] - base[c], kern, mode="same") * 2.2
                evm = icu["event_min"][k]
                if evm > 0:
                    frac = np.clip((m - (evm - 240)) / 240, 0, 1) ** 1.5
                    v[:, 0] += 38 * frac; v[:, 1] -= 9 * frac; v[:, 2] += 12 * frac
                    v[:, 3] -= 30 * frac; v[:, 4] -= 12 * frac; v[:, 5] += 1.0 * frac
                    rec = np.clip((m - evm) / 720, 0, 1)
                    after = m >= evm
                    v[after, 0] -= 38 * rec[after]; v[after, 1] += 9 * rec[after]; v[after, 2] -= 12 * rec[after]
                    v[after, 3] += 30 * rec[after]; v[after, 4] += 12 * rec[after]; v[after, 5] -= 1.0 * rec[after]
                    ev_id += 1
                    ei = enc_of_icu[k]
                    w.writerow([f"EVT{ev_id:06d}", icu["bed"][k], E["mrn"][ei], E["id"][ei], ts_str(evm, "isotz"),
                                icu["event_type"][k], "DECEASED" if icu["deceased"][k] else "SURVIVED"])
                v[:, 1] = np.minimum(v[:, 1], 100)
                bed_no = int(icu["bed"][k][-2:])
                chunks.append((m, np.full(nmin, bed_no, np.int16), np.full(nmin, enc_of_icu[k]), v.astype(np.float32)))
            self.counts["icu_monitors/icu_events.csv"] = ev_id
        if not chunks:
            return
        M = np.concatenate([c[0] for c in chunks]); B = np.concatenate([c[1] for c in chunks])
        EI = np.concatenate([c[2] for c in chunks]); V = np.concatenate([c[3] for c in chunks])
        o = np.lexsort((B, M))
        M, B, EI, V = M[o], B[o], EI[o], V[o]
        drift = ((B == 7) | (B == 15)) & (M >= DRIFT_START_MIN)
        Mout = M + np.where(drift, 7, 0)
        null_mask = rng.random(V.shape) < 0.01
        spike = rng.random(len(M)) < 0.0005
        dup = rng.random(len(M)) < 0.002
        day = (M // 1440).astype(int)
        rows = 0
        mrn = E["mrn"]
        fmt_cols = ["hr", "spo2", "rr", "sbp", "dbp", "temp"]
        for dd in np.unique(day):
            idx = np.where(day == dd)[0]
            lines = []
            tsv = np.datetime_as_string(np.datetime64("2024-01-01T00:00") + Mout[idx].astype("int64").astype("timedelta64[m]"), unit="s")
            for j, r in enumerate(idx):
                vals = V[r]
                parts = []
                for c, name in enumerate(fmt_cols):
                    if null_mask[r, c]:
                        parts.append(f'"{name}":null')
                    elif c == 5:
                        parts.append(f'"{name}":{vals[c]:.1f}')
                    else:
                        parts.append(f'"{name}":{int(round(vals[c]))}')
                if spike[r]:
                    parts[0] = f'"hr":{rng.choice([0, 300, 350])}'
                    parts[1] = f'"spo2":{rng.integers(101, 128)}'
                line = (f'{{"device_id":"MON-ICU{B[r]:02d}","bed_id":"ICU-{B[r]:02d}","mrn":"{mrn[EI[r]]}",'
                        f'"ts":"{tsv[j]}+04:00",' + ",".join(parts) + "}")
                lines.append(line)
                if dup[r]:
                    lines.append(line)
            nl = len(lines)
            for _ in range(int(nl * 0.005)):                   # out-of-order arrivals
                x = rng.integers(0, nl); y = min(nl - 1, x + rng.integers(1, 50))
                lines[x], lines[y] = lines[y], lines[x]
            date = (START + timedelta(days=int(dd))).strftime("%Y-%m-%d")
            with open(self.path("icu_monitors", "vitals_stream", f"vitals_{date}.jsonl"), "w") as f:
                f.write("\n".join(lines) + "\n")
            rows += nl
        self.counts["icu_monitors/vitals_stream/*.jsonl"] = rows

    # ------------------------------------------------------------ unstructured: notes + feedback
    def write_notes(self):
        rng, E = self.rng, self.E
        desc = {c: dsc for lst in DX.values() for c, dsc in lst}
        courses = ["Treated with IV fluids and analgesia, responded well.",
                   "Started on IV antibiotics; inflammatory markers trended down.",
                   "Underwent uneventful procedure under general anaesthesia.",
                   "Monitored on telemetry, no further events.",
                   "Diuresed with IV furosemide with good effect, weight down 3 kg.",
                   "Glucose control optimised, insulin regimen adjusted.",
                   "Physiotherapy commenced day 1, mobilising independently at discharge.",
                   "Required supplemental oxygen for 48h, weaned to room air."]
        plans = ["Continue home medications.", "Review results in clinic.", "Wound check in 7 days.",
                 "Repeat bloods in 1 week.", "Dietitian referral made.", "Return to ED if symptoms worsen."]
        rows = 0
        with open(self.path("ehr_cerner", "clinical_notes.jsonl"), "w") as f:
            for i in range(self.n_enc):
                et = E["etype"][i]
                if not (et == "IP" or (et == "ED" and rng.random() < .25)):
                    continue
                p = E["pat"][i]
                age = int(self.age[p] + E["admit"][i] / 1440 / 365.25)
                sex = "female" if self.sex[p] == "F" else "male"
                dx = desc.get(str(E["prim"][i]), "undifferentiated symptoms")
                if et == "IP":
                    dname = DEPT_VARIANTS[E["dept"][i]][0].strip()
                    course = " ".join(random.sample(courses, 2 if rng.random() < .4 else 1))
                    follow = ("Care handed over to the ward team." if E["dept"][i] == "ICU"
                              else f"Follow up in {dname} clinic in {rng.integers(1, 7)} weeks.")
                    txt = (f"DISCHARGE SUMMARY. {age}yo {sex} admitted under {dname} with {dx.lower()}. {course} "
                           f"Discharge disposition: {str(E['disp'][i]).lower().replace('_', ' ')}. "
                           f"Plan: {random.choice(plans)} {follow}")
                    ntype = "DISCHARGE_SUMMARY"
                else:
                    txt = (f"ED NOTE. {age} y/o {sex} presenting with {dx.lower()}. Triage cat {E['triage'][i]}. "
                           f"Seen after {E['wait'][i]} min wait. {random.choice(plans)}")
                    ntype = "ED_NOTE"
                if rng.random() < .05:
                    txt = txt.replace("admitted", "admited").replace("with", "w/")
                f.write(json.dumps({"note_id": f"N{rows + 1:08d}", "encounter_id": E["id"][i], "mrn": E["mrn"][i],
                                    "note_type": ntype, "author_id": E["attending"][i],
                                    "created_at": ts_str(E["disc"][i] if et == "IP" else E["admit"][i] + 30, "isotz"),
                                    "text": " ".join(txt.split())}, ensure_ascii=False) + "\n")
                rows += 1
        self.counts["ehr_cerner/clinical_notes.jsonl"] = rows

    def write_feedback(self):
        rng, E = self.rng, self.E
        T = {
            "wait": (["Waited {w} minutes in the emergency department before seeing a doctor. Unacceptable.",
                      "ER was packed, no beds, my father waited hours on a chair.",
                      "Very long wait in emergency, staff said the wards were full.",
                      "الانتظار في الطوارئ كان طويلاً جداً"], [1, 2]),
            "billing": (["Insurance claim was rejected and nobody explained why.",
                         "Billing department asked me to pay because the insurer denied the claim.",
                         "Still waiting for the hospital to resubmit my insurance claim.",
                         "مشكلة في موافقة التأمين ولم يتم حلها"], [1, 2, 3]),
            "praise": (["Excellent care from Dr {d} and the nursing team.",
                        "Very clean hospital and professional staff.",
                        "Smooth appointment, doctor explained everything clearly.",
                        "الطاقم الطبي ممتاز وشكراً للدكتور", "خدمة ممتازة ونظافة عالية"], [4, 5]),
            "parking": (["Parking is a nightmare, took 20 minutes to find a space.",
                         "المواقف قليلة وصعب الوصول"], [2, 3]),
            "appointment": (["Could not get an appointment for three weeks.",
                             "The app kept cancelling my booking.",
                             "Clinic ran 45 minutes late."], [2, 3]),
            "pharmacy": (["Pharmacy said the medicine was out of stock and I had to come back.",
                          "Had to wait for a substitute injection, pharmacy had none."], [2, 3]),
        }
        stockout_days = set()
        for _, s0, s1, _ in STOCKOUTS:
            stockout_days.update(range(int(s0 // 1440), int(s1 // 1440)))
        rows = 0
        with open(self.path("feedback", "patient_feedback.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["feedback_id", "submitted_at", "channel", "encounter_id", "rating", "comment"])
            for i in range(self.n_enc):
                if rng.random() > 0.12:
                    continue
                et = E["etype"][i]
                pw = {"praise": 5, "parking": 1, "appointment": 1.2 if et == "OP" else 0.2, "wait": 0.3,
                      "billing": 0.3, "pharmacy": 0.1}
                if et == "ED" and E["wait"][i] > 120:
                    pw["wait"] = 8
                if E.get("denied") is not None and E["denied"][i]:
                    pw["billing"] = 9
                if int(E["admit"][i] // 1440) in stockout_days and et == "IP":
                    pw["pharmacy"] = 2
                topics = list(pw); pr = np.array(list(pw.values())); pr /= pr.sum()
                tp = topics[rng.choice(len(topics), p=pr)]
                txt = random.choice(T[tp][0]).format(w=E["wait"][i] if E["wait"][i] > 0 else 90,
                                                     d=random.choice(["Ahmed", "Sharma", "Smith", "Haddad"]))
                rating = int(rng.choice(T[tp][1]))
                enc = E["id"][i] if rng.random() > 0.15 else ""
                sub = E["disc"][i] + rng.uniform(60, 7 * 1440)
                if sub >= END_MIN:
                    continue
                w.writerow([f"FB{rows + 1:07d}", ts_str(sub), rng.choice(["SMS_SURVEY", "MOBILE_APP", "EMAIL", "WEBSITE"],
                                                                            p=[.45, .3, .15, .1]),
                            enc, rating if rng.random() > .03 else "", txt])
                rows += 1
        self.counts["feedback/patient_feedback.csv"] = rows

    def run(self):
        steps = [("patients", self.make_patients), ("encounters", self.make_encounters),
                 ("mrn views", self.make_mrn_views), ("diagnoses", self.write_diagnoses),
                 ("encounters csv", self.write_encounters), ("patients csv", self.write_patients),
                 ("labs", self.write_labs), ("pharmacy", self.write_pharmacy), ("inventory", self.write_inventory),
                 ("claims", self.write_claims), ("notes", self.write_notes), ("feedback", self.write_feedback),
                 ("vitals", self.write_vitals)]
        for name, fn in steps:
            t0 = datetime.now()
            fn()
            print(f"  {name:<15} done in {(datetime.now() - t0).total_seconds():.0f}s", flush=True)
        with open(self.path("manifest.json"), "w") as f:
            json.dump({"generator": "generate_ahd.py", "scale": self.scale, "period": "2024-01-01..2025-12-31",
                       "synthetic": True, "row_counts": self.counts,
                       "total_rows": sum(v for k, v in self.counts.items() if "(messages)" not in k)}, f, indent=2)
        print(json.dumps(self.counts, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="ahd_data")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=312)
    args = ap.parse_args()
    Gen(args.out, args.scale, args.seed).run()
