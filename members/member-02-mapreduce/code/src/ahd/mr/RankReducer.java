package ahd.mr;

import java.io.IOException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import org.apache.hadoop.io.LongWritable;
import org.apache.hadoop.io.Text;
import org.apache.hadoop.mapreduce.Reducer;

/**
 * Job 3b reducer: keys arrive in decreasing count order, so a running counter gives the rank.
 * Output line: rank \t word \t count   (words with equal counts are listed alphabetically).
 * Optional -D rank.top.n=N keeps only the top N words per language.
 */
public class RankReducer extends Reducer<LongWritable, Text, Text, LongWritable> {
    private long rank = 0;
    private long topN;
    private final Text out = new Text();

    @Override
    protected void setup(Context context) {
        topN = context.getConfiguration().getLong("rank.top.n", 0);   // 0 = keep all
    }

    @Override
    protected void reduce(LongWritable count, Iterable<Text> words, Context context)
            throws IOException, InterruptedException {
        List<String> tied = new ArrayList<String>();
        for (Text w : words) tied.add(w.toString());              // copy: Hadoop reuses the Text object
        Collections.sort(tied);
        for (String w : tied) {
            if (topN > 0 && rank >= topN) return;
            rank++;
            out.set(rank + "\t" + w);
            context.write(out, count);
        }
    }
}
