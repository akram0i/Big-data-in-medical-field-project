#!/usr/bin/env python3
"""Draws the Member 5 BPMN figures as SVG, then renders PNG with Playwright."""
import os, sys
from xml.sax.saxutils import escape

OUT = sys.argv[1] if len(sys.argv) > 1 else "bpmn"
os.makedirs(OUT, exist_ok=True)

INK, MUTED, FILL, ACC, ACC_FILL = "#2b2b2b", "#6b6b6b", "#ffffff", "#1f5f9e", "#e8f1fa"
FONT = "Arial, Helvetica, sans-serif"


class Svg:
    def __init__(self, w, h):
        self.w, self.h, self.p = w, h, []

    def add(self, s):
        self.p.append(s)

    def text(self, x, y, lines, size=16, anchor="middle", color=INK, weight="normal", style="normal", lh=None):
        lh = lh or size * 1.25
        if isinstance(lines, str):
            lines = [lines]
        y0 = y - (len(lines) - 1) * lh / 2
        for i, l in enumerate(lines):
            self.add(f'<text x="{x}" y="{y0 + i * lh + size * 0.35:.1f}" text-anchor="{anchor}" font-family="{FONT}" '
                     f'font-size="{size}" fill="{color}" font-weight="{weight}" font-style="{style}">{escape(l)}</text>')

    def task(self, cx, cy, w, h, lines, kind="task"):
        # BPMN task: rounded rectangle. kind=="data" gets the accent colour.
        f, s = (ACC_FILL, ACC) if kind == "data" else (FILL, INK)
        self.add(f'<rect x="{cx - w / 2}" y="{cy - h / 2}" width="{w}" height="{h}" rx="12" fill="{f}" stroke="{s}" stroke-width="2"/>')
        self.text(cx, cy, lines, size=16)

    def event(self, cx, cy, kind, label=None, label_dx=0, label_dy=34):
        if kind == "start":
            self.add(f'<circle cx="{cx}" cy="{cy}" r="17" fill="{FILL}" stroke="{INK}" stroke-width="2"/>')
        elif kind == "end":
            self.add(f'<circle cx="{cx}" cy="{cy}" r="17" fill="{FILL}" stroke="{INK}" stroke-width="5"/>')
        elif kind == "error":
            self.add(f'<circle cx="{cx}" cy="{cy}" r="17" fill="{FILL}" stroke="{INK}" stroke-width="5"/>')
            self.add(f'<path d="M{cx - 7},{cy + 8} L{cx - 3},{cy - 8} L{cx + 3},{cy + 2} L{cx + 7},{cy - 8}" fill="none" stroke="{INK}" stroke-width="2.5"/>')
        if label:
            self.text(cx + label_dx, cy + label_dy, label, size=14, color=MUTED)

    def gateway(self, cx, cy, kind="and", label=None, label_dx=34, label_dy=-24):
        r = 24
        self.add(f'<path d="M{cx},{cy - r} L{cx + r},{cy} L{cx},{cy + r} L{cx - r},{cy} Z" fill="{FILL}" stroke="{INK}" stroke-width="2"/>')
        if kind == "and":
            self.add(f'<path d="M{cx - 11},{cy} H{cx + 11} M{cx},{cy - 11} V{cy + 11}" stroke="{INK}" stroke-width="3.5"/>')
        else:
            self.add(f'<path d="M{cx - 9},{cy - 9} L{cx + 9},{cy + 9} M{cx + 9},{cy - 9} L{cx - 9},{cy + 9}" stroke="{INK}" stroke-width="3.5"/>')
        if label:
            self.text(cx + label_dx, cy + label_dy, label, size=14, color=MUTED, anchor="start")

    def store(self, cx, cy, w, h, lines):
        # BPMN data store: cylinder
        x, y, e = cx - w / 2, cy - h / 2, 9
        self.add(f'<path d="M{x},{y + e} V{y + h - e} A{w / 2},{e} 0 0 0 {x + w},{y + h - e} V{y + e} A{w / 2},{e} 0 0 0 {x},{y + e} Z" fill="{ACC_FILL}" stroke="{ACC}" stroke-width="2"/>')
        self.add(f'<path d="M{x},{y + e} A{w / 2},{e} 0 0 0 {x + w},{y + e}" fill="none" stroke="{ACC}" stroke-width="2"/>')
        self.text(cx, cy + 5, lines, size=15, weight="bold", color=ACC)

    def arrow(self, pts, dashed=False, label=None, lpos=None):
        d = "M" + " L".join(f"{x},{y}" for x, y in pts)
        dash = ' stroke-dasharray="6 5"' if dashed else ""
        self.add(f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="2"{dash} marker-end="url(#a)"/>')
        if label:
            x, y = lpos
            self.text(x, y, label, size=14, color=MUTED, anchor="start")

    def save(self, name):
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}">'
                f'<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto">'
                f'<path d="M0,0 L10,5 L0,10 z" fill="{INK}"/></marker></defs>'
                f'<rect width="100%" height="100%" fill="white"/>')
        open(f"{OUT}/{name}.svg", "w").write(head + "".join(self.p) + "</svg>")


# ---------------------------------------------------------------- control flow
def control():
    s = Svg(900, 1130)
    cx = 450
    s.text(cx, 24, "Member 5 ETL: control flow (BPMN)", size=18, weight="bold")
    s.event(cx, 74, "start", "Start", label_dx=44, label_dy=0)
    s.task(cx, 150, 280, 56, ["Check raw zone files exist", "(hadoop fs -test)"])
    s.gateway(cx, 226, "and")
    ys = 316
    xs = [160, 450, 740]
    names = [["Parse and stage", "pharmacy JSON"], ["Parse and stage", "inventory XML"], ["Parse and stage", "claims CSV"]]
    for x, n in zip(xs, names):
        s.task(x, ys, 240, 64, n)
    s.arrow([(cx, 100 + 0), (cx, 122)]) if False else None
    s.arrow([(cx, 91), (cx, 122)])
    s.arrow([(cx, 178), (cx, 202)])
    for x in xs:
        s.arrow([(cx, 226 + 24 if x == cx else 226), (x, 226) if x != cx else (cx, 250)] if False else
                ([(cx - 24, 226), (x, 226), (x, ys - 32)] if x < cx else
                 [(cx + 24, 226), (x, 226), (x, ys - 32)] if x > cx else [(cx, 250), (cx, ys - 32)]))
    s.gateway(cx, 406, "and")
    for x in xs:
        s.arrow([(x, ys + 32), (x, 406), (cx - 24 if x < cx else cx + 24, 406)] if x != cx else [(cx, ys + 32), (cx, 382)])
    s.task(cx, 492, 320, 60, ["Load cur_inventory", "(drug reference, loaded first)"])
    s.arrow([(cx, 430), (cx, 462)])
    s.gateway(cx, 574, "and")
    s.arrow([(cx, 522), (cx, 550)])
    xs2 = [290, 610]
    s.task(290, 676, 270, 64, ["Load cur_dispense", "(drug lookup, fact-like)"])
    s.task(610, 676, 270, 64, ["Load cur_claims", "(resubmission lookup)"])
    for x in xs2:
        s.arrow([((cx - 24) if x < cx else (cx + 24), 574), (x, 574), (x, 644)])
    s.gateway(cx, 778, "and")
    for x in xs2:
        s.arrow([(x, 708), (x, 778), ((cx - 24) if x < cx else (cx + 24), 778)])
    s.task(cx, 860, 320, 56, ["Load rej_business", "(rejects from all three sources)"])
    s.arrow([(cx, 802), (cx, 832)])
    s.task(cx, 946, 320, 56, ["Reconcile counts", "raw rows = curated + rejected"])
    s.arrow([(cx, 888), (cx, 918)])
    s.gateway(cx, 1030, "xor", label="Counts match?", label_dx=34, label_dy=-26)
    s.arrow([(cx, 974), (cx, 1006)])
    s.event(cx, 1096, "end", "ETL complete", label_dx=100, label_dy=0)
    s.add("")  # keep order
    s.arrow([(cx, 1054), (cx, 1079)], label="yes", lpos=(cx + 12, 1068))
    s.event(790, 1030, "error", "Stop and investigate", label_dx=0, label_dy=36)
    s.arrow([(cx + 24, 1030), (773, 1030)], label="no", lpos=(cx + 52, 1020))
    # legend
    s.add(f'<path d="M30,1070 l14,-14 l14,14 l-14,14 z" fill="white" stroke="{INK}" stroke-width="1.5"/><path d="M37,1070 h14 M44,1063 v14" stroke="{INK}" stroke-width="2.5"/>')
    s.text(68, 1070, "parallel gateway (AND)", size=13, anchor="start", color=MUTED)
    s.add(f'<path d="M30,1104 l14,-14 l14,14 l-14,14 z" fill="white" stroke="{INK}" stroke-width="1.5"/><path d="M38,1097 l12,12 M50,1097 l-12,12" stroke="{INK}" stroke-width="2.5"/>')
    s.text(68, 1104, "exclusive gateway (XOR)", size=13, anchor="start", color=MUTED)
    s.save("bpmn_control")


# ---------------------------------------------------------------- data flow
def dataflow(name, title, store_in, steps, out_ok, out_rej, gate_label="Row passes all checks?"):
    n = len(steps)
    step_h, gap = 52, 52
    top = 120
    H = top + n * (step_h + gap) + 270
    s = Svg(960, H)
    s.text(480, 24, title, size=18, weight="bold")
    X = 300  # centre of task column
    s.store(X, 78, 300, 56, store_in)
    y_prev = 78 + 28
    y = top + 70
    for i, (t, note) in enumerate(steps):
        cy = top + 30 + i * (step_h + gap) + step_h / 2
        s.arrow([(X, y_prev), (X, cy - step_h / 2)])
        s.task(X, cy, 320, step_h, t, kind="data")
        s.text(480, cy, note, size=14, color=MUTED, anchor="start")
        y_prev = cy + step_h / 2
    gy = y_prev + 56
    s.arrow([(X, y_prev), (X, gy - 24)])
    s.gateway(X, gy, "xor", label=gate_label, label_dx=34, label_dy=-30)
    sy = gy + 130
    s.store(X - 140, sy, 250, 62, out_ok)
    s.store(X + 190, sy, 250, 62, out_rej)
    s.arrow([(X - 24, gy), (X - 140, gy), (X - 140, sy - 31)], label="yes", lpos=(X - 190, gy - 10))
    s.arrow([(X + 24, gy), (X + 190, gy), (X + 190, sy - 31)], label="no", lpos=(X + 70, gy - 10))
    s.h = int(sy + 60)
    s.save(name)


def data_flows():
    dataflow("bpmn_pharmacy", "Data tasks: pharmacy JSON (v1 2024, v2 2025)",
             ["raw_pharmacy_json", "one JSON line per row"],
             [(["Read JSON lines"], "External table, one STRING column"),
              (["Detect schema version"], "v1 = 2024 files, v2 = 2025 files"),
              (["Map v1 and v2 to one layout"], "get_json_object + COALESCE over v1 and v2 names"),
              (["Convert timestamp"], "epoch milliseconds to Dubai time"),
              (["Validate"], "missing key, quantity <= 0, date out of range"),
              (["De-duplicate"], "one row per dispense_id (row_number)"),
              (["Look up drug_code"], "flag if not in cur_inventory")],
             ["cur_dispense", "month partitions, 8 MRN buckets"], ["rej_business", "reason + raw line"])
    dataflow("bpmn_inventory", "Data tasks: inventory XML (Oracle SCM)",
             ["raw_inventory_xml", "XML records, monthly files"],
             [(["Read XML records"], "External table, one STRING column"),
              (["Extract fields"], "xpath_string / xpath"),
              (["Convert Oracle date"], "DD-MON-YY to DATE"),
              (["Cast numbers"], "quantity, reorder level, unit cost"),
              (["Validate"], "missing drug_code, negative quantity"),
              (["Resolve duplicate IDs"], "keep latest record per ID")],
             ["cur_inventory", "month partitions"], ["rej_business", "reason + raw record"])
    dataflow("bpmn_claims", "Data tasks: claims CSV (Oracle billing)",
             ["raw_claims_csv", "quoted CSV, one file"],
             [(["Read quoted CSV"], "OpenCSVSerde keeps commas in amounts"),
              (["Clean amounts"], "'AED 1,234.50' to DECIMAL; blank = NULL"),
              (["Convert dates"], "submitted date to DATE"),
              (["Normalise diagnosis code"], "upper-case, add dot; flag valid or not"),
              (["Validate"], "missing claim_id, bad date, negative amount"),
              (["De-duplicate"], "one row per claim_id"),
              (["Link resubmissions"], "LEFT JOIN to original; dangling link = flag only")],
             ["cur_claims", "month partitions, 8 MRN buckets"], ["rej_business", "reason + raw row"])


control()
data_flows()

# ---------------------------------------------------------------- PNG render
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch()
    for f in sorted(os.listdir(OUT)):
        if f.endswith(".svg"):
            svg = open(f"{OUT}/{f}").read()
            import re
            w = int(re.search(r'width="(\d+)"', svg).group(1)); h = int(re.search(r'height="(\d+)"', svg).group(1))
            pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=2)
            pg.goto("file://" + os.path.abspath(f"{OUT}/{f}"))
            pg.screenshot(path=f"{OUT}/{f[:-4]}.png", clip={"x": 0, "y": 0, "width": w, "height": h})
            pg.close()
    b.close()
print(sorted(os.listdir(OUT)))
