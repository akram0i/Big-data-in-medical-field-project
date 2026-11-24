package ahd.mr;

import java.io.IOException;

import org.apache.hadoop.io.LongWritable;
import org.apache.hadoop.io.Text;
import org.apache.hadoop.mapreduce.Reducer;

/**
 * Adds up the counts for one key. Used as BOTH the Combiner and the Reducer in Job 2 and Job 3a.
 *
 * This is safe as a Combiner because addition is associative and commutative:
 * sum(sum(a,b), sum(c)) = sum(a,b,c), and input/output types are the same (Text, LongWritable).
 * (Contrast with an average, which is NOT safe to combine directly - see Member 3's vitals job.)
 */
public class SumReducer extends Reducer<Text, LongWritable, Text, LongWritable> {
    private final LongWritable total = new LongWritable();

    @Override
    protected void reduce(Text key, Iterable<LongWritable> values, Context context)
            throws IOException, InterruptedException {
        long sum = 0;
        for (LongWritable v : values) sum += v.get();
        total.set(sum);
        context.write(key, total);
    }
}
