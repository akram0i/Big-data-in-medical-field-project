package ahd.mr;

import java.util.HashMap;
import java.util.Map;

import org.apache.hadoop.io.LongWritable;
import org.apache.hadoop.io.Text;
import org.apache.hadoop.mapreduce.Partitioner;

/**
 * Sends every key of the same lab panel to the same reducer, one reducer per panel
 * (same idea as Tutorial 3's partitioner that sends words a-m to reducer 0 and n-z to reducer 1).
 *
 * With 7 reducers the output is one file per panel:
 *   part-r-00000 CBC, 00001 BMP, 00002 LIPID, 00003 HBA1C, 00004 TROP, 00005 CRP, 00006 LACT
 *
 * Key format: "PANEL \t TEST \t FLAG".
 */
public class PanelPartitioner extends Partitioner<Text, LongWritable> {

    private static final Map<String, Integer> PANEL_INDEX = new HashMap<String, Integer>();
    static {
        String[] panels = {"CBC", "BMP", "LIPID", "HBA1C", "TROP", "CRP", "LACT"};
        for (int i = 0; i < panels.length; i++) PANEL_INDEX.put(panels[i], i);
    }
    public static final int NUM_PANELS = 7;

    @Override
    public int getPartition(Text key, LongWritable value, int numPartitions) {
        if (numPartitions <= 1) return 0;
        String k = key.toString();
        int tab = k.indexOf('\t');
        String panel = tab < 0 ? k : k.substring(0, tab);
        Integer idx = PANEL_INDEX.get(panel);
        if (idx == null) {                          // a new panel we don't know yet
            return (panel.hashCode() & Integer.MAX_VALUE) % numPartitions;
        }
        return idx % numPartitions;
    }
}
