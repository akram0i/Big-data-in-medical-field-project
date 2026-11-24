package ahd.mr;

import org.apache.hadoop.io.LongWritable;
import org.apache.hadoop.io.Text;
import org.apache.hadoop.mapreduce.Partitioner;

/**
 * Job 3b: the key is now the count, so the language is read from the VALUE (the word).
 * A Partitioner may look at the value as well as the key.
 * part-r-00000 = English ranking, part-r-00001 = Arabic ranking.
 */
public class RankLanguagePartitioner extends Partitioner<LongWritable, Text> {
    @Override
    public int getPartition(LongWritable count, Text word, int numPartitions) {
        if (numPartitions <= 1) return 0;
        return TextUtil.isArabic(word.toString()) ? 1 : 0;
    }
}
