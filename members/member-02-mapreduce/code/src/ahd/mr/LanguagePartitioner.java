package ahd.mr;

import org.apache.hadoop.io.LongWritable;
import org.apache.hadoop.io.Text;
import org.apache.hadoop.mapreduce.Partitioner;

/**
 * Job 3a: English (Latin-script) words -> reducer 0, Arabic words -> reducer 1.
 * Output: part-r-00000 = English word counts, part-r-00001 = Arabic word counts.
 */
public class LanguagePartitioner extends Partitioner<Text, LongWritable> {
    @Override
    public int getPartition(Text key, LongWritable value, int numPartitions) {
        if (numPartitions <= 1) return 0;
        return TextUtil.isArabic(key.toString()) ? 1 : 0;
    }
}
