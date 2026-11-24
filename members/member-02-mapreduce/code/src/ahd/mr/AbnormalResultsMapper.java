package ahd.mr;

import java.io.IOException;

import org.apache.hadoop.io.LongWritable;
import org.apache.hadoop.io.Text;
import org.apache.hadoop.mapreduce.Mapper;

/**
 * Input:  lab_results CSV rows written by Job 1.
 * Output: key = "PANEL \t TEST \t FLAG" (FLAG = H, L or N), value = 1.
 *
 * Emitting N (normal) as well as H/L lets us report an abnormal RATE per test, not just a count:
 *   abnormal % = (H + L) / (H + L + N)
 */
public class AbnormalResultsMapper extends Mapper<LongWritable, Text, Text, LongWritable> {

    public enum Abn { ROWS_READ, MALFORMED_ROWS, NO_FLAG, HIGH, LOW, NORMAL }

    // column positions in lab_results
    private static final int PANEL = 5, TEST = 8, FLAG = 14, NCOLS = 16;

    private static final LongWritable ONE = new LongWritable(1);
    private final Text outKey = new Text();

    @Override
    protected void map(LongWritable key, Text value, Context context)
            throws IOException, InterruptedException {
        context.getCounter(Abn.ROWS_READ).increment(1);
        String[] f = value.toString().split(",", -1);
        if (f.length != NCOLS || f[PANEL].isEmpty() || f[TEST].isEmpty()) {
            context.getCounter(Abn.MALFORMED_ROWS).increment(1);
            return;
        }
        String flag = f[FLAG].trim();
        if ("H".equals(flag))      context.getCounter(Abn.HIGH).increment(1);
        else if ("L".equals(flag)) context.getCounter(Abn.LOW).increment(1);
        else if ("N".equals(flag)) context.getCounter(Abn.NORMAL).increment(1);
        else {                                     // no range to derive a flag from
            context.getCounter(Abn.NO_FLAG).increment(1);
            return;
        }
        outKey.set(f[PANEL] + "\t" + f[TEST] + "\t" + flag);
        context.write(outKey, ONE);
    }
}
