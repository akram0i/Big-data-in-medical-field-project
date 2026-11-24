package ahd.mr;

import org.apache.hadoop.fs.Path;
import org.apache.hadoop.mapreduce.JobContext;
import org.apache.hadoop.mapreduce.lib.input.TextInputFormat;

/**
 * TextInputFormat that never splits a file: one monthly HL7 file = one input split = one mapper.
 *
 * Why: the LIS resends a duplicate message straight after the original, in the same file.
 * If a whole file is read by one mapper, a HashSet of control IDs inside that mapper is enough
 * to drop every duplicate in a map-only job (no reducer, no shuffle).
 *
 * The record delimiter is still taken from "textinputformat.record.delimiter", so with "\n\n"
 * each record handed to the mapper is one complete HL7 message (MSH ... OBX lines).
 */
public class NonSplittableTextInputFormat extends TextInputFormat {
    @Override
    protected boolean isSplitable(JobContext context, Path file) {
        return false;
    }
}
