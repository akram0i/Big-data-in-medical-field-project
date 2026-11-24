#!/usr/bin/env python3
"""Builds Member5_Hive_ETL_Business_ISIT312.docx in the same layout as the Member 1 and 3 documents.
Yellow-highlighted text = something only the person running the jobs can fill in."""
import re, sys
from docx import Document
from docx.shared import Pt, Inches, RGBColor, Emu
from docx.enum.text import WD_COLOR_INDEX, WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

ROOT = "/home/claude/member5"
OUT = sys.argv[1] if len(sys.argv) > 1 else f"{ROOT}/Member5_Hive_ETL_Business_ISIT312.docx"
FONT = "Arial"

doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Emu(11906 * 635), Emu(16838 * 635)       # A4, as in the other members' files
for m in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
    setattr(sec, m, Inches(1))

st = doc.styles
st["Normal"].font.name = FONT
st["Normal"].font.size = Pt(10.5)
st["Normal"].element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
st["Normal"].paragraph_format.space_after = Pt(6)
for name, size, before in (("Heading 1", 16, 16), ("Heading 2", 13, 12), ("Heading 3", 11, 8)):
    h = st[name]
    h.font.name, h.font.size, h.font.bold = FONT, Pt(size), True
    h.font.color.rgb = RGBColor(0x1F, 0x1F, 0x1F)
    h.element.rPr.rFonts.set(qn("w:eastAsia"), FONT); h.element.rPr.rFonts.set(qn("w:ascii"), FONT); h.element.rPr.rFonts.set(qn("w:hAnsi"), FONT)
    h.paragraph_format.space_before, h.paragraph_format.space_after = Pt(before), Pt(6)
    h.paragraph_format.keep_with_next = True


def shade(cell_or_par, fill):
    el = cell_or_par._tc.get_or_add_tcPr() if hasattr(cell_or_par, "_tc") else cell_or_par._p.get_or_add_pPr()
    s = OxmlElement("w:shd"); s.set(qn("w:val"), "clear"); s.set(qn("w:color"), "auto"); s.set(qn("w:fill"), fill)
    el.append(s)


def runs(p, text, size=None, italic=False, mono=False):
    """**bold**, `code`, [[fill-in]] (yellow highlight)."""
    for tok in re.split(r"(\*\*.+?\*\*|`.+?`|\[\[.+?\]\])", text):
        if not tok:
            continue
        if tok.startswith("**"):
            r = p.add_run(tok[2:-2]); r.bold = True
        elif tok.startswith("`"):
            r = p.add_run(tok[1:-1]); r.font.name = "Courier New"; r.font.size = Pt(9.5)
        elif tok.startswith("[["):
            r = p.add_run("[" + tok[2:-2] + "]"); r.font.highlight_color = WD_COLOR_INDEX.YELLOW
        else:
            r = p.add_run(tok)
        if italic: r.italic = True
        if size and not tok.startswith("`"): r.font.size = Pt(size)
        if mono: r.font.name = "Courier New"; r.font.size = Pt(8.5)
    return p


def para(text, italic=False, size=None, align=None, after=None):
    p = doc.add_paragraph()
    runs(p, text, size=size, italic=italic)
    if align: p.alignment = align
    if after is not None: p.paragraph_format.space_after = Pt(after)
    return p


def bullets(items):
    for t in items:
        p = doc.add_paragraph(style="List Bullet"); runs(p, t); p.paragraph_format.space_after = Pt(3)


def code(text, size=7.5):
    for line in text.rstrip("\n").split("\n"):
        line = re.sub(r"(?<=\S) {3,}", "  ", line)
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(0); p.paragraph_format.left_indent = Inches(0.1)
        shade(p, "F3F3F1")
        r = p.add_run(line if line else " "); r.font.name = "Courier New"; r.font.size = Pt(size)
        r._element.rPr.rFonts.set(qn("w:eastAsia"), "Courier New")
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def table(rows, widths, header=True, size=9.5):
    t = doc.add_table(rows=len(rows), cols=len(rows[0]))
    t.style = "Table Grid"; t.alignment = WD_TABLE_ALIGNMENT.CENTER; t.autofit = False
    for i, row in enumerate(rows):
        for j, txt in enumerate(row):
            c = t.cell(i, j); c.width = Inches(widths[j])
            c.paragraphs[0].paragraph_format.space_after = Pt(2)
            runs(c.paragraphs[0], ("**%s**" % txt) if (header and i == 0) else txt, size=size)
            if header and i == 0: shade(c, "EDEDE8")
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


FIG = [0]


def caption(text):
    FIG[0] += 1
    p = doc.add_paragraph(); runs(p, "Figure %d -- %s" % (FIG[0], text), size=9.5, italic=True)
    p.paragraph_format.space_after = Pt(10)


def figure(path, text, width=5.6):
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next = True
    p.add_run().add_picture(path, width=Inches(width))
    caption(text)


def shot(text, what):
    """Placeholder box for a screenshot only the person on the VM can take."""
    t = doc.add_table(rows=1, cols=1); t.style = "Table Grid"; t.alignment = WD_TABLE_ALIGNMENT.CENTER
    c = t.cell(0, 0); c.width = Inches(6.2); shade(c, "FFF9D6")
    runs(c.paragraphs[0], "[[SCREENSHOT TO INSERT]] " + what, size=9.5)
    c.paragraphs[0].paragraph_format.keep_with_next = True
    sp = doc.add_paragraph(); sp.paragraph_format.space_after = Pt(0); sp.paragraph_format.keep_with_next = True
    caption(text)


def steps(fname, nums):
    """Return the numbered blocks ('-- N. ...') of a script as text."""
    s = open(f"{ROOT}/hql/{fname}").read()
    parts = re.split(r"(?m)^(?=-- \d\. )", s)
    out = [p.rstrip() for p in parts if re.match(r"-- (\d)\. ", p) and int(p[3]) in nums]
    return "\n\n".join(out)


# ------------------------------------------------------------------ title block
p = para("ISIT312 Big Data Management · AHD Data Lake project (Group of 8)", size=9.5)
p.runs[0].font.color.rgb = RGBColor(0x6B, 0x6B, 0x6B)
doc.add_heading("Hive ETL for business data and BPMN", level=0).runs[0].font.name = FONT
para("**Member 5: Kebar** [[surname]] ([[student ID]]) · Implementation evidence for report part v (ETL design and pipelines)")
para("All data used is synthetic, modelled on AHD's systems, because real patient data cannot be shared. "
     "No real AHD patient or staff data appears in this document.", italic=True)
para("Yellow text marks what only the person running the jobs can fill in: screenshots, row counts and the lessons paragraph. "
     "Delete this line and all yellow before submitting.", italic=True, size=9)

# ------------------------------------------------------------------ 1 summary
doc.add_heading("1. Summary", level=1)
para("This document shows the Member 5 work: Hive ETL that turns three raw business sources (pharmacy dispensing JSON, "
     "Oracle inventory XML and Oracle claims CSV) into clean curated tables, a reject table with a reason for every dropped row, "
     "and the whole ETL drawn in BPMN.")
table([
    ["Deliverable", "Result", "Evidence"],
    ["Pharmacy JSON", "Hive external table over the raw JSON; v1 (2024) and v2 (2025) schemas merged with `get_json_object`; epoch milliseconds converted to Dubai time. Raw [[n]] rows, curated [[n]], rejected [[n]].", "Figures 5, 6, 7"],
    ["Inventory XML", "Hive external table over the raw XML; fields read with `xpath_string`; Oracle dates fixed; duplicate IDs resolved. Raw [[n]], curated [[n]], rejected [[n]].", "Figures 5, 8"],
    ["Claims", "Quoted CSV read with OpenCSVSerde; amounts like \"AED 1,234.50\" converted; blanks kept as NULL; resubmission links checked. Raw [[n]], curated [[n]], rejected [[n]].", "Figures 5, 9"],
    ["Reject table", "`rej_business` holds every rejected row with its reason; raw rows = curated + rejected for all three sources.", "Figures 12, 13, 14"],
    ["BPMN", "Control flow (parallel loads, lookup tables first) and the data tasks for each source.", "Figures 1 to 4"],
], [1.2, 4.1, 1.0])

# ------------------------------------------------------------------ 2 environment
doc.add_heading("2. Environment", level=1)
bullets([
    "Course BigData VM, Hadoop 2.7.3 in pseudo-distributed mode (set up by Member 1). Hive version: [[output of hive --version]].",
    "Hive database `ahd`. Raw zone `/datalake/raw/<source>/` is only read, never edited. Curated tables are written to `/datalake/curated/<table>/`.",
    "Raw layout used for the run: [[flat folders from hadoop fs -put, or dt=YYYY-MM-DD folders from DailyIngest]]. "
    "Both work because the scripts set `mapreduce.input.fileinputformat.input.dir.recursive=true`.",
    "Data: 2% sample for development, full dataset for the final run: [[state which one each figure uses]].",
    "Everything is run by one script, `run_member5.sh`, which runs `00_setup.hql` to `04_reconcile.hql` in order and writes a log for each.",
])

# ------------------------------------------------------------------ 3 design
doc.add_heading("3. ETL design", level=1)
doc.add_heading("3.1 How data moves", level=2)
para("Each source goes through the same five steps. Nothing in the raw zone changes: every fix is made on the way to the curated zone.")
table([
    ["Source (raw zone)", "1. Raw table", "2. Staging", "3. Check and de-duplicate", "4. Curated", "5. Rejects"],
    ["pharmacy_api (JSON lines)", "raw_pharmacy_json", "stg_pharmacy", "chk_pharmacy", "cur_dispense", "rej_pharmacy"],
    ["erp_oracle (XML)", "raw_inventory_xml", "stg_inventory", "chk_inventory", "cur_inventory", "rej_inventory"],
    ["billing_oracle (CSV)", "raw_claims_csv", "stg_claims", "chk_claims", "cur_claims", "rej_claims"],
], [1.3, 1.1, 0.95, 1.1, 0.95, 0.9], size=8.5)
para("`rej_business` joins the three reject tables at the end. In every `chk_` table each row gets one reason, or none. "
     "Rows with no reason go to the curated table; rows with a reason go to the reject table. That is why raw rows always equal curated plus rejected.")

doc.add_heading("3.2 Rules", level=2)
para("**Fixed and kept** means the row stays in the curated table. **Rejected** means it goes to `rej_business` with the reason shown. "
     "The first rule that fails sets the reason.")
table([
    ["Source", "Rule", "Check", "Action"],
    ["Pharmacy", "P1 MISSING_ID", "no dispense_id", "Rejected"],
    ["", "P2 MISSING_DRUG_CODE", "no drug code", "Rejected"],
    ["", "P3 MISSING_MRN", "no patient MRN", "Rejected"],
    ["", "P4 BAD_QUANTITY", "quantity missing, not a number or 0 or less", "Rejected"],
    ["", "P5 BAD_TIMESTAMP", "time missing or outside Jan 2024 to Dec 2025", "Rejected"],
    ["", "P6 DUPLICATE_ID", "same dispense_id again (first valid copy kept)", "Rejected"],
    ["", "P7 schema", "v1 and v2 field names differ", "Fixed: merged into one layout, `schema_ver` records which"],
    ["", "P8 time", "epoch milliseconds", "Fixed: converted to Dubai time (UTC+4)"],
    ["", "P9 drug not in stock table", "drug_code not in cur_inventory", "Kept, flagged `drug_in_inventory = false`"],
    ["Inventory", "I1 MISSING_ID / I2 MISSING_DRUG_CODE", "no record_id or no drug_code", "Rejected"],
    ["", "I3 BAD_DATE", "snapshot date will not parse", "Rejected"],
    ["", "I4 BAD_QUANTITY", "quantity missing or negative", "Rejected"],
    ["", "I5 DUPLICATE_ID", "same record_id again (latest update kept)", "Rejected"],
    ["", "I6 date", "Oracle format DD-MON-YY", "Fixed: converted to DATE"],
    ["Claims", "C1 MISSING_ID", "no claim_id", "Rejected"],
    ["", "C2 BAD_DATE", "submitted date will not parse", "Rejected"],
    ["", "C3 BAD_AMOUNT / C4 NEGATIVE_AMOUNT", "amount text is not a number, or below 0", "Rejected"],
    ["", "C5 DUPLICATE_ID", "same claim_id again", "Rejected"],
    ["", "C6 amount", "\"AED 1,234.50\"", "Fixed: converted to DECIMAL(12,2)"],
    ["", "C7 blank amount", "no amount", "Kept as NULL, flagged `amount_missing`"],
    ["", "C8 diagnosis code", "lower-case, no dot, missing or invalid", "Fixed to upper-case with dot; kept, flagged `dx_valid`"],
    ["", "C9 resubmission link", "points to a claim_id that does not exist", "Kept; link set to NULL, `resub_link_ok = false`"],
], [0.8, 1.85, 2.25, 1.4], size=8.5)
para("Blank amounts, invalid diagnosis codes and unlinked resubmissions are kept on purpose. They are exactly the claims that "
     "business problems 4 and 5 (coding errors and denials) need to find, so dropping them would hide the evidence.")

doc.add_heading("3.3 Curated tables for Members 6 and 7", level=2)
table([
    ["Table", "Columns", "Layout"],
    ["cur_dispense", "dispense_id, encounter_id, mrn, drug_code, drug_name, qty, unit_price, dispensed_ts, schema_ver, drug_in_inventory", "PARTITIONED BY (year, month); CLUSTERED BY (mrn) INTO 8 BUCKETS"],
    ["cur_inventory", "record_id, drug_code, drug_name, qty_on_hand, reorder_level, unit_cost, snapshot_date, last_updated", "PARTITIONED BY (year, month)"],
    ["cur_claims", "claim_id, encounter_id, mrn, payer, department, diagnosis_code, dx_valid, claim_amount, amount_missing, status, denial_reason, submitted_date, original_claim_id, is_resubmission, resub_link_ok", "PARTITIONED BY (year, month); CLUSTERED BY (mrn) INTO 8 BUCKETS"],
    ["rej_business", "source, reason, record_key, raw_record, source_file", "one table for all three sources"],
], [1.1, 3.6, 1.6], size=8.5)
para("MRN buckets and monthly partitions match Member 4's clinical tables, so joins on `mrn` and `encounter_id` line up.")

# ------------------------------------------------------------------ 4 BPMN
doc.add_heading("4. ETL drawn in BPMN", level=1)
para("The diagrams follow Tutorial 5 Task 3.1: **control tasks** show the order of the jobs and which can run side by side, "
     "and **data tasks** show what happens to the data inside each job.")
doc.add_heading("4.1 Control flow", level=2)
figure(f"{ROOT}/bpmn/bpmn_control.png", "BPMN control flow of the Member 5 ETL.", width=5.5)
bullets([
    "**Check raw files** first. If a source folder is missing the ETL stops before any table is touched.",
    "**The three parsing jobs run in parallel** (first parallel gateway). They read different sources and do not depend on each other.",
    "**Inventory is loaded first**, before anything that needs it. `cur_inventory` is the reference table, like a dimension in a star schema.",
    "**Dispense and claims are loaded last, in parallel.** Dispense looks drug codes up in the inventory table; claims look up the original claim for each resubmission. This is the Tutorial 5 rule of dimensions first, facts last.",
    "**Rejects are collected, then counts are reconciled.** If raw rows do not equal curated plus rejected, the ETL ends in an error event; if they match, it completes.",
])
doc.add_heading("4.2 Data tasks", level=2)
figure(f"{ROOT}/bpmn/bpmn_pharmacy.png", "Data tasks for the pharmacy JSON.", width=6.2)
figure(f"{ROOT}/bpmn/bpmn_inventory.png", "Data tasks for the inventory XML.", width=6.2)
figure(f"{ROOT}/bpmn/bpmn_claims.png", "Data tasks for the claims CSV.", width=6.2)
para("Blue shapes are data (raw table, curated table, reject table). Rounded boxes are the data tasks: conversion, "
     "de-duplication and lookups. The exclusive gateway at the bottom of each diagram sends a row to the curated table or the reject table, never both.")

# ------------------------------------------------------------------ 5 raw look
doc.add_heading("5. Checking the raw files first", level=1)
para("`00_discover.sh` only reads the raw zone. It prints a line from each pharmacy schema version, the key names found in each version, "
     "the first XML records and the claims header. The field names in the three scripts come from this output and from the dataset README.")
shot("Output of 00_discover.sh: JSON lines (v1 and v2), XML records and claims header.",
     "Run `./00_discover.sh` and screenshot the pharmacy v1 and v2 lines, the XML records and the claims header.")

# ------------------------------------------------------------------ 6 pharmacy
doc.add_heading("6. Pipeline 1: pharmacy JSON", level=1)
para("The pharmacy API changed its schema in 2025. In v1 the patient and drug fields are at the top level; in v2 they are different names or nested. "
     "The raw table keeps each JSON line as one text column. `get_json_object` reads each key, and `COALESCE` takes whichever name the row has, "
     "so both versions come out in one layout. `schema_ver` keeps which version the row came from.")
para("Timestamps are epoch milliseconds (for example `1704067200000`). The job divides by 1,000 to get seconds, casts to a timestamp "
     "and converts from UTC to Asia/Dubai.")
code(steps("02_pharmacy.hql", {2}))
para("Rows are then checked and de-duplicated. A valid row always wins over an invalid row with the same `dispense_id`, "
     "so a good record is not lost because a bad copy came first.")
code(steps("02_pharmacy.hql", {3}))
para("The curated table is partitioned by month and has 8 buckets by MRN. The left outer join flags drugs that are not in the stock table instead of dropping the dispense.")
code(steps("02_pharmacy.hql", {4}))
shot("Pharmacy job running (Hive log with the YARN application, or the ResourceManager page).", "Screenshot of 02_pharmacy.hql running.")
shot("cur_dispense: rows from both schema versions with converted timestamps.", "Screenshot of the `schema_ver` summary query and the 5 sample rows from 04_reconcile.hql.")
table([
    ["", "Raw rows", "Curated", "Rejected", "Expected from README"],
    ["2% sample", "[[n]]", "[[n]]", "[[n]]", "about 2% of the full count"],
    ["Full dataset", "[[n]]", "[[n]]", "[[n]]", "1,011,013 raw rows"],
], [1.3, 1.2, 1.2, 1.2, 1.6])
para("Findings: [[2 or 3 sentences from your own numbers: which rule rejected most rows, how many v1 and v2 rows, how many drugs were not in the stock table]].")

# ------------------------------------------------------------------ 7 inventory
doc.add_heading("7. Pipeline 2: inventory XML", level=1)
para("Hive has no XML reader in its basic setup, so each XML record is read as one line of text and `xpath_string` pulls out each field. "
     "The filter `line RLIKE '<item[ >]'` keeps record lines and drops the XML header and wrapper tags. "
     "Oracle writes dates as DD-MON-YY (for example `15-JAN-24`), which `unix_timestamp` with the pattern `dd-MMM-yy` converts.")
code(steps("01_inventory.hql", {2}))
para("Some record IDs appear twice. The check keeps one row per `record_id`: a valid row first, then the one updated last.")
code(steps("01_inventory.hql", {3}))
shot("Inventory job running.", "Screenshot of 01_inventory.hql running.")
shot("cur_inventory: converted dates and one row per record.", "Screenshot of the inventory sample query from 04_reconcile.hql.")
table([
    ["", "Raw rows", "Curated", "Rejected", "Expected from README"],
    ["2% sample", "[[n]]", "[[n]]", "[[n]]", "about 2% of the full count"],
    ["Full dataset", "[[n]]", "[[n]]", "[[n]]", "99,299 raw rows"],
], [1.3, 1.2, 1.2, 1.2, 1.6])
para("Findings: [[how many duplicate IDs, how many bad dates, anything unexpected in the XML]].")

# ------------------------------------------------------------------ 8 claims
doc.add_heading("8. Pipeline 3: claims", level=1)
para("Claim amounts such as `\"AED 1,234.50\"` contain a comma inside quotes. A plain comma-separated Hive table would split that value into two columns, "
     "so the raw table uses `OpenCSVSerde`, which respects the quotes. It returns every column as text, so the ETL converts the types itself.")
code(steps("03_claims.hql", {1, 2}))
para("Rows are checked next. Blank amounts and invalid diagnosis codes are kept and flagged, not rejected. "
     "Resubmissions are linked to the original claim with `LEFT OUTER JOIN ... IS NULL` (Hive has no MINUS): "
     "if the original does not exist, the link is set to NULL and `resub_link_ok` is false.")
code(steps("03_claims.hql", {3, 4}))
shot("Claims job running.", "Screenshot of 03_claims.hql running.")
shot("cur_claims: cleaned amounts, flags and the flag counts query.", "Screenshot of the claims sample query and the flag-counts query from 04_reconcile.hql.")
table([
    ["", "Raw rows", "Curated", "Rejected", "Blank amounts", "Invalid or missing diagnosis code", "Resubmissions"],
    ["2% sample", "[[n]]", "[[n]]", "[[n]]", "[[n]]", "[[n]]", "[[n]]"],
    ["Full dataset", "[[n]]", "[[n]]", "[[n]]", "[[n]]", "[[n]]", "[[n]]"],
], [1.0, 0.8, 0.8, 0.8, 0.9, 1.2, 0.9], size=8.5)
para("Raw rows for the full dataset should be 735,391 (README). Findings: [[share of claims with a missing or invalid diagnosis code, compared with the 53% denial figure in problem 4 of the brief]].")

# ------------------------------------------------------------------ 9 rejects
doc.add_heading("9. Reject table and reconciliation", level=1)
para("`04_reconcile.hql` builds `rej_business` from the three reject tables and counts rows per source and reason. "
     "It then checks that raw rows equal curated plus rejected for each source. If any line shows `balanced = false`, a row was lost or counted twice and the ETL is not finished.")
code(steps("04_reconcile.hql", {1, 3}))
shot("Rejected rows per source and reason.", "Screenshot of the reject counts query result.")
shot("Reconciliation: etl_counts with balanced = true for pharmacy, inventory and claims.", "Screenshot of `SELECT * FROM etl_counts`.")
shot("Curated zone: partition folders and bucket files in HDFS.", "Screenshot of `hadoop fs -ls -R /datalake/curated/cur_dispense | head -30` and `SHOW PARTITIONS cur_dispense`.")
table([
    ["Source", "Reason", "Rows rejected"],
    ["[[source]]", "[[reason]]", "[[n]]"],
    ["[[source]]", "[[reason]]", "[[n]]"],
], [1.6, 2.6, 1.6])

# ------------------------------------------------------------------ 10 notes
doc.add_heading("10. Notes for the rest of the team", level=1)
bullets([
    "**Member 1:** the scripts read both the flat layout and the `dt=` layout. Curated tables are written to `/datalake/curated/cur_dispense`, `cur_inventory` and `cur_claims`.",
    "**Member 4:** if any of your CSV files has quoted values with commas, use `OpenCSVSerde` as in `03_claims.hql`; `ROW FORMAT DELIMITED` splits them. I also used 8 buckets by `mrn` so our tables match.",
    "**Member 6:** use the curated tables in section 3.3 for the star schema. `cur_inventory.drug_code` is the key between dispenses and stock; `cur_claims.encounter_id` and `mrn` link claims to Member 4's encounters.",
    "**Member 7:** the flags answer business problems directly: `dx_valid = false` (problem 4), `status` and `payer` (problem 5), `drug_in_inventory` and the stock table against dispense quantities (problem 6).",
    "**Member 8:** my lessons-learned paragraph and the limitations below are ready for the report.",
])

# ------------------------------------------------------------------ 11 limits
doc.add_heading("11. Limitations", level=1)
bullets([
    "Synthetic data modelled on AHD's systems; the numbers are not AHD's real records.",
    "Single-node pseudo-distributed cluster: Hive jobs run as MapReduce on one machine, so run times say nothing about a real cluster.",
    "Time zone: epoch milliseconds are treated as UTC and shown in Dubai time. If the README says otherwise, only the conversion line in `02_pharmacy.hql` changes.",
    "Inventory XML is read one record per line. A record that spans several lines would need a pre-processing step on the way to the curated zone (not in the raw zone).",
    "Rows are rejected by fixed rules written by us; AHD has not reviewed the rules.",
])

# ------------------------------------------------------------------ 12 lessons
doc.add_heading("12. Lessons learned (150 to 200 words)", level=1)
para("[[Write this yourself after the full run, in your own words, 150 to 200 words. The spec asks what you learned from the practical work compared with the lectures and tutorials. "
     "Things worth covering if they happened to you: a Hive error and how you fixed it; one data problem you did not expect; what OpenCSVSerde, xpath or the reconciliation check taught you; "
     "what you would change on a real cluster, for example faster file formats or a check that runs on every load.]]")

# ------------------------------------------------------------------ appendix
doc.add_page_break()
doc.add_heading("Appendix A. Code", level=1)
para("All files are in the shared folder `member5/hql`. Run `./run_member5.sh` to execute them in order.")
for f in ["run_member5.sh", "00_discover.sh", "00_setup.hql", "01_inventory.hql", "02_pharmacy.hql", "03_claims.hql", "04_reconcile.hql"]:
    doc.add_heading(f, level=3)
    code(open(f"{ROOT}/hql/{f}").read(), size=7)

# footer page numbers
fp = sec.footer.paragraphs[0]; fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = fp.add_run("Member 5 · ISIT312 AHD Data Lake · page "); r.font.size = Pt(8)
for t, txt in (("begin", None), (None, "PAGE"), ("end", None)):
    r2 = fp.add_run(); r2.font.size = Pt(8)
    if t:
        e = OxmlElement("w:fldChar"); e.set(qn("w:fldCharType"), t); r2._r.append(e)
    else:
        e = OxmlElement("w:instrText"); e.set(qn("xml:space"), "preserve"); e.text = txt; r2._r.append(e)

doc.save(OUT)
print("saved", OUT)
