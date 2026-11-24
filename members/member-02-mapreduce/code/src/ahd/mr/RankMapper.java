package ahd.mr;

import java.io.IOException;

import org.apache.hadoop.io.LongWritable;
import org.apache.hadoop.io.Text;
import org.apache.hadoop.mapreduce.Mapper;

/**
 * Job 3b mapper: swaps "word \t count" (output of Job 3a) into (count, word) so that the
 * shuffle sorts by count. The driver sets a DECREASING sort comparator, so the largest
 * counts reach the reducer first.
 */
public class RankMapper extends Mapper<Text, Text, LongWritable, Text> {
    private final LongWritable count = new LongWritable();

    @Override
    protected void map(Text word, Text countText, Context context)
            throws IOException, InterruptedException {
        try {
            count.set(Long.parseLong(countText.toString().trim()));
        } catch (NumberFormatException e) {
            return;
        }
        context.write(count, word);
    }
}
