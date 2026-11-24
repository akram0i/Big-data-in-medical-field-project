package ahd.mr;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.conf.Configured;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.io.LongWritable;
import org.apache.hadoop.io.Text;
import org.apache.hadoop.mapreduce.Job;
import org.apache.hadoop.mapreduce.lib.input.FileInputFormat;
import org.apache.hadoop.mapreduce.lib.output.FileOutputFormat;
import org.apache.hadoop.util.Tool;
import org.apache.hadoop.util.ToolRunner;

/**
 * Job 2: number of High / Low / Normal results per lab test, from the lab_results CSV of Job 1.
 *
 *   Mapper      AbnormalResultsMapper   (panel, test, flag) -> 1
 *   Combiner    SumReducer              local sums on each map node, less data shuffled
 *   Partitioner PanelPartitioner        one reducer (and one output file) per panel
 *   Reducer     SumReducer              final sums
 *
 * Usage:
 *   hadoop jar ahd-mr.jar ahd.mr.AbnormalResultsDriver /datalake/curated/lab_results /datalake/curated/lab_abnormal_counts
 */
public class AbnormalResultsDriver extends Configured implements Tool {

    @Override
    public int run(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("Usage: AbnormalResultsDriver <lab_results dir> <output dir>");
            ToolRunner.printGenericCommandUsage(System.err);
            return 2;
        }
        Job job = Job.getInstance(getConf(), "AHD abnormal lab results per test");
        job.setJarByClass(AbnormalResultsDriver.class);

        job.setMapperClass(AbnormalResultsMapper.class);
        job.setCombinerClass(SumReducer.class);
        job.setPartitionerClass(PanelPartitioner.class);
        job.setReducerClass(SumReducer.class);
        job.setNumReduceTasks(PanelPartitioner.NUM_PANELS);

        job.setMapOutputKeyClass(Text.class);
        job.setMapOutputValueClass(LongWritable.class);
        job.setOutputKeyClass(Text.class);
        job.setOutputValueClass(LongWritable.class);

        FileInputFormat.addInputPath(job, new Path(args[0]));
        FileOutputFormat.setOutputPath(job, new Path(args[1]));
        return job.waitForCompletion(true) ? 0 : 1;
    }

    public static void main(String[] args) throws Exception {
        System.exit(ToolRunner.run(new Configuration(), new AbnormalResultsDriver(), args));
    }
}
