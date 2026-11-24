package ahd.mr;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.conf.Configured;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.io.LongWritable;
import org.apache.hadoop.io.Text;
import org.apache.hadoop.mapreduce.Job;
import org.apache.hadoop.mapreduce.lib.input.FileInputFormat;
import org.apache.hadoop.mapreduce.lib.input.KeyValueTextInputFormat;
import org.apache.hadoop.mapreduce.lib.output.FileOutputFormat;
import org.apache.hadoop.util.Tool;
import org.apache.hadoop.util.ToolRunner;

/**
 * Job 3: complaint themes from patient feedback. Two chained MapReduce jobs:
 *
 *   3a word count   FeedbackTokenMapper -> SumReducer (Combiner + Reducer), LanguagePartitioner (2 reducers)
 *                   output: <out>/counts/part-r-00000 (English), part-r-00001 (Arabic)
 *   3b ranking      RankMapper (count, word) -> decreasing sort -> RankReducer, RankLanguagePartitioner
 *                   output: <out>/ranked/part-r-00000 (English ranking), part-r-00001 (Arabic ranking)
 *
 * Usage:
 *   hadoop jar ahd-mr.jar ahd.mr.FeedbackWordCountDriver /datalake/raw/feedback /datalake/curated/feedback_words
 * Options (generic -D, read via ToolRunner):
 *   -D feedback.max.rating=3        only comments rated 1..3 count as complaints (5 = all comments)
 *   -D feedback.include.unrated=true include comments with a blank rating
 *   -D feedback.from=2025-01-01 -D feedback.to=2025-02-28   only comments submitted in that period
 *   -D rank.top.n=25                keep only the top 25 words per language in the ranking
 */
public class FeedbackWordCountDriver extends Configured implements Tool {

    @Override
    public int run(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("Usage: FeedbackWordCountDriver <feedback dir> <output dir>");
            ToolRunner.printGenericCommandUsage(System.err);
            return 2;
        }
        Path in = new Path(args[0]);
        Path counts = new Path(args[1], "counts");
        Path ranked = new Path(args[1], "ranked");
        Configuration conf = getConf();
        conf.setBoolean("mapreduce.input.fileinputformat.input.dir.recursive", true);

        // ---------------- Job 3a: word count
        Job wc = Job.getInstance(conf, "AHD feedback word count");
        wc.setJarByClass(FeedbackWordCountDriver.class);
        wc.setMapperClass(FeedbackTokenMapper.class);
        wc.setCombinerClass(SumReducer.class);
        wc.setPartitionerClass(LanguagePartitioner.class);
        wc.setReducerClass(SumReducer.class);
        wc.setNumReduceTasks(2);
        wc.setOutputKeyClass(Text.class);
        wc.setOutputValueClass(LongWritable.class);
        FileInputFormat.addInputPath(wc, in);
        FileOutputFormat.setOutputPath(wc, counts);
        if (!wc.waitForCompletion(true)) return 1;

        // ---------------- Job 3b: rank words by count, highest first, per language
        Job rk = Job.getInstance(conf, "AHD feedback word ranking");
        rk.setJarByClass(FeedbackWordCountDriver.class);
        rk.setInputFormatClass(KeyValueTextInputFormat.class);     // splits "word<TAB>count"
        rk.setMapperClass(RankMapper.class);
        rk.setMapOutputKeyClass(LongWritable.class);
        rk.setMapOutputValueClass(Text.class);
        rk.setSortComparatorClass(LongWritable.DecreasingComparator.class);
        rk.setPartitionerClass(RankLanguagePartitioner.class);
        rk.setReducerClass(RankReducer.class);
        rk.setNumReduceTasks(2);
        rk.setOutputKeyClass(Text.class);
        rk.setOutputValueClass(LongWritable.class);
        FileInputFormat.addInputPath(rk, counts);
        FileOutputFormat.setOutputPath(rk, ranked);
        return rk.waitForCompletion(true) ? 0 : 1;
    }

    public static void main(String[] args) throws Exception {
        System.exit(ToolRunner.run(new Configuration(), new FeedbackWordCountDriver(), args));
    }
}
