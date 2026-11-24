package ahd.mr;

import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

import org.apache.hadoop.io.LongWritable;
import org.apache.hadoop.io.NullWritable;
import org.apache.hadoop.io.Text;
import org.apache.hadoop.mapreduce.Mapper;

/**
 * Input:  key = byte offset, value = one whole HL7 message (MSH, PID, PV1, OBR, OBX... lines).
 * Output: key = NullWritable, value = one CSV line per OBX result:
 *
 *   control_id,mrn,encounter_id,patient_class,department,panel_code,order_ts,result_ts,
 *   test_code,test_name,value,unit,ref_low,ref_high,abnormal_flag,qc_note
 *
 * Patient name and date of birth (PID-5, PID-7) are deliberately NOT copied to the curated
 * zone: the MRN is enough to join to patients (data minimisation).
 */
public class Hl7ParserMapper extends Mapper<LongWritable, Text, NullWritable, Text> {

    /** Counters shown at the end of the job and in the YARN / JobHistory UI. */
    public enum Hl7 {
        MESSAGES_READ, EMPTY_RECORDS, TRUNCATED_SKIPPED, DUPLICATE_SKIPPED, MESSAGES_PARSED,
        RESULTS_WRITTEN, GLUCOSE_CONVERTED, FLAG_DERIVED, RESULT_BEFORE_ORDER, BAD_VALUE_SKIPPED
    }

    /** Number of OBX results each panel must have; fewer means the message was cut short. */
    private static final Map<String, Integer> EXPECTED_OBX = new HashMap<String, Integer>();
    static {
        EXPECTED_OBX.put("CBC", 3);
        EXPECTED_OBX.put("BMP", 4);
        EXPECTED_OBX.put("LIPID", 4);
        EXPECTED_OBX.put("HBA1C", 1);
        EXPECTED_OBX.put("TROP", 1);
        EXPECTED_OBX.put("CRP", 1);
        EXPECTED_OBX.put("LACT", 1);
    }

    /** Minimum number of '|' fields per segment (index of the last field we read + 1). */
    private static final int MSH_MIN = 12;   // MSH-7 time = [6], MSH-10 control ID = [9]
    private static final int PID_MIN = 4;    // PID-3 MRN = [3]
    private static final int PV1_MIN = 20;   // PV1-2 class, PV1-3 dept, PV1-19 encounter = [19]
    private static final int OBR_MIN = 23;   // OBR-4 panel, OBR-7 order time, OBR-22 result time = [22]
    private static final int OBX_MIN = 15;   // OBX-3 test, OBX-5..8 value/unit/range/flag, OBX-14 time

    private static final double GLUCOSE_MMOL_TO_MGDL = 18.0;

    /** Control IDs already written by this mapper (one mapper reads one whole monthly file). */
    private final Set<String> seenControlIds = new HashSet<String>();
    private final Text out = new Text();

    @Override
    protected void map(LongWritable key, Text value, Context context)
            throws IOException, InterruptedException {

        String msg = value.toString().trim();
        if (msg.isEmpty()) {
            context.getCounter(Hl7.EMPTY_RECORDS).increment(1);
            return;
        }
        context.getCounter(Hl7.MESSAGES_READ).increment(1);

        // ---- 1. split into segments and check each one is complete
        String[] msh = null, pid = null, pv1 = null, obr = null;
        List<String[]> obx = new ArrayList<String[]>();
        boolean broken = false;

        for (String line : msg.split("\r?\n")) {
            if (line.isEmpty()) continue;
            String[] f = line.split("\\|", -1);
            String seg = f[0];
            if ("MSH".equals(seg))      { msh = f; broken |= f.length < MSH_MIN; }
            else if ("PID".equals(seg)) { pid = f; broken |= f.length < PID_MIN; }
            else if ("PV1".equals(seg)) { pv1 = f; broken |= f.length < PV1_MIN; }
            else if ("OBR".equals(seg)) { obr = f; broken |= f.length < OBR_MIN; }
            else if ("OBX".equals(seg)) { obx.add(f); broken |= f.length < OBX_MIN; }
            else broken = true;                     // unknown/partial segment name, e.g. "OB"
        }
        if (msh == null || pid == null || pv1 == null || obr == null || obx.isEmpty()) broken = true;

        String panel = broken ? null : comp(obr[4], 0);
        if (!broken) {
            Integer expected = EXPECTED_OBX.get(panel);
            if (expected != null && obx.size() < expected) broken = true;
        }
        if (broken) {
            context.getCounter(Hl7.TRUNCATED_SKIPPED).increment(1);
            return;
        }

        // ---- 2. drop resent duplicates (same MSH-10 control ID)
        String controlId = msh[9];
        if (!seenControlIds.add(controlId)) {
            context.getCounter(Hl7.DUPLICATE_SKIPPED).increment(1);
            return;
        }
        context.getCounter(Hl7.MESSAGES_PARSED).increment(1);

        // ---- 3. header fields shared by every result in the message
        String mrn = comp(pid[3], 0);
        String encounterId = pv1[19];
        String patientClass = pv1[2];
        String department = pv1[3].trim();
        String orderRaw = obr[7], resultRaw = obr[22];
        String orderTs = hl7Time(orderRaw), resultTs = hl7Time(resultRaw);
        boolean resultBeforeOrder = isTs(orderRaw) && isTs(resultRaw) && resultRaw.compareTo(orderRaw) < 0;
        if (resultBeforeOrder) context.getCounter(Hl7.RESULT_BEFORE_ORDER).increment(1);

        // ---- 4. one CSV row per OBX
        for (String[] o : obx) {
            String testCode = comp(o[3], 0);
            String testName = comp(o[3], 1);
            String valueStr = o[5].trim();
            String unit = o[6].trim();
            String range = o[7].trim();
            String flag = o[8].trim();

            double v;
            try {
                v = Double.parseDouble(valueStr);
            } catch (NumberFormatException e) {
                context.getCounter(Hl7.BAD_VALUE_SKIPPED).increment(1);
                continue;
            }
            double[] lohi = parseRange(range);       // null if no usable range
            String lo = lohi == null ? "" : fmtNum(lohi[0]);
            String hi = lohi == null ? "" : fmtNum(lohi[1]);
            StringBuilder qc = new StringBuilder();

            // Glucose reported in mmol/L by some analysers: convert to mg/dL (x 18), range too.
            if ("GLU".equals(testCode) && "mmol/L".equalsIgnoreCase(unit)) {
                v = v * GLUCOSE_MMOL_TO_MGDL;
                valueStr = String.format(Locale.ROOT, "%.1f", v);
                unit = "mg/dL";
                if (lohi != null) {
                    lohi[0] *= GLUCOSE_MMOL_TO_MGDL;
                    lohi[1] *= GLUCOSE_MMOL_TO_MGDL;
                    lo = String.format(Locale.ROOT, "%.1f", lohi[0]);
                    hi = String.format(Locale.ROOT, "%.1f", lohi[1]);
                }
                addNote(qc, "GLU_MMOL_CONVERTED");
                context.getCounter(Hl7.GLUCOSE_CONVERTED).increment(1);
            }

            // Missing abnormal flag: work it out from the reference range.
            if (flag.isEmpty() && lohi != null) {
                flag = v > lohi[1] ? "H" : (v < lohi[0] ? "L" : "N");
                addNote(qc, "FLAG_DERIVED");
                context.getCounter(Hl7.FLAG_DERIVED).increment(1);
            }
            if (resultBeforeOrder) addNote(qc, "RESULT_BEFORE_ORDER");
            if (qc.length() == 0) qc.append("OK");

            out.set(csv(controlId, mrn, encounterId, patientClass, department, panel,
                    orderTs, resultTs, testCode, testName, valueStr, unit, lo, hi, flag, qc.toString()));
            context.write(NullWritable.get(), out);
            context.getCounter(Hl7.RESULTS_WRITTEN).increment(1);
        }
    }

    // ------------------------------------------------------------------ helpers

    /** Component n of an HL7 field ("CBC^Complete blood count^L" -> n=0 "CBC"). */
    static String comp(String field, int n) {
        String[] c = field.split("\\^", -1);
        return n < c.length ? c[n].trim() : "";
    }

    static boolean isTs(String s) {
        if (s == null || s.length() != 14) return false;
        for (int i = 0; i < 14; i++) if (!Character.isDigit(s.charAt(i))) return false;
        return true;
    }

    /** "20240103072843" -> "2024-01-03 07:28:43" (Hive TIMESTAMP format); "" if malformed. */
    static String hl7Time(String s) {
        if (!isTs(s)) return "";
        return s.substring(0, 4) + "-" + s.substring(4, 6) + "-" + s.substring(6, 8) + " "
                + s.substring(8, 10) + ":" + s.substring(10, 12) + ":" + s.substring(12, 14);
    }

    /** "12.0-16.5" -> {12.0, 16.5}; null if the range cannot be read. */
    static double[] parseRange(String r) {
        int dash = r.indexOf('-', 1);              // start at 1 so a leading minus sign is allowed
        if (dash < 0) return null;
        try {
            return new double[]{Double.parseDouble(r.substring(0, dash)), Double.parseDouble(r.substring(dash + 1))};
        } catch (NumberFormatException e) {
            return null;
        }
    }

    static String fmtNum(double d) {
        return d == Math.rint(d) ? String.valueOf((long) d) : String.valueOf(d);
    }

    private static void addNote(StringBuilder sb, String note) {
        if (sb.length() > 0) sb.append(';');
        sb.append(note);
    }

    /** Join fields with commas; commas inside a field are replaced so the CSV stays one row. */
    static String csv(String... fields) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < fields.length; i++) {
            if (i > 0) sb.append(',');
            sb.append(fields[i] == null ? "" : fields[i].replace(',', ' '));
        }
        return sb.toString();
    }
}
