package ahd.mr;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.conf.Configured;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.io.NullWritable;
import org.apache.hadoop.io.Text;
import org.apache.hadoop.mapreduce.Job;
import org.apache.hadoop.mapreduce.lib.input.FileInputFormat;
import org.apache.hadoop.mapreduce.lib.output.FileOutputFormat;
import org.apache.hadoop.util.Tool;
import org.apache.hadoop.util.ToolRunner;

/**
 * Job 1 (map-only): HL7 v2.5.1 ORU^R01 lab messages  ->  lab_results CSV (one row per OBX result).
 *
 * Usage:
 *   hadoop jar ahd-mr.jar ahd.mr.Hl7ParserDriver /datalake/raw/lis_hl7 /datalake/curated/lab_results
 *
 * Data-quality rules applied in the mapper:
 *   - truncated messages (cut mid-segment)        -> skipped, counted
 *   - duplicate (resent) control IDs (MSH-10)     -> skipped, counted
 *   - glucose in mmol/L                           -> value and range x 18, unit mg/dL
 *   - missing abnormal flag (OBX-8)               -> derived from the reference range
 *   - result time before order time               -> kept, marked in qc_note
 */
public class Hl7ParserDriver extends Configured implements Tool {

    @Override
    public int run(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("Usage: Hl7ParserDriver <hl7 input dir> <output dir>");
            ToolRunner.printGenericCommandUsage(System.err);
            return 2;
        }
        Configuration conf = getConf();
        // One record = one HL7 message: messages are separated by a blank line.
        conf.set("textinputformat.record.delimiter", "\n\n");
        // Also read files inside dated sub-folders (e.g. lis_hl7/dt=2025-01-31/) from the ingestion job.
        conf.setBoolean("mapreduce.input.fileinputformat.input.dir.recursive", true);

        Job job = Job.getInstance(conf, "AHD HL7 parser (map-only)");
        job.setJarByClass(Hl7ParserDriver.class);

        job.setInputFormatClass(NonSplittableTextInputFormat.class);
        job.setMapperClass(Hl7ParserMapper.class);
        job.setNumReduceTasks(0);                 // map-only: output files are part-m-0000x

        job.setOutputKeyClass(NullWritable.class);
        job.setOutputValueClass(Text.class);

        FileInputFormat.addInputPath(job, new Path(args[0]));
        FileOutputFormat.setOutputPath(job, new Path(args[1]));

        return job.waitForCompletion(true) ? 0 : 1;
    }

    public static void main(String[] args) throws Exception {
        System.exit(ToolRunner.run(new Configuration(), new Hl7ParserDriver(), args));
    }
}
