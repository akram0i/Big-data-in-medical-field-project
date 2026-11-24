package ahd.mr;

import java.io.IOException;
import java.util.List;

import org.apache.hadoop.io.LongWritable;
import org.apache.hadoop.io.Text;
import org.apache.hadoop.mapreduce.Mapper;

/**
 * Job 3a mapper. Input: patient_feedback.csv rows
 *   feedback_id,submitted_at,channel,encounter_id,rating,comment
 * Output: (word, 1) for every non-stop-word in a complaint comment.
 *
 * "Complaint" = rating <= feedback.max.rating (default 3). Set -D feedback.max.rating=5 to count
 * every comment. Comments with no rating are skipped unless -D feedback.include.unrated=true.
 * -D feedback.from=yyyy-MM-dd / -D feedback.to=yyyy-MM-dd restrict to a period (e.g. winter vs summer).
 */
public class FeedbackTokenMapper extends Mapper<LongWritable, Text, Text, LongWritable> {

    public enum Fb {
        ROWS_READ, HEADER_SKIPPED, MALFORMED_ROWS, OUTSIDE_PERIOD, NOT_A_COMPLAINT, NO_RATING_SKIPPED,
        COMMENTS_USED, STOP_WORDS_REMOVED, ENGLISH_WORDS, ARABIC_WORDS
    }

    private static final int SUBMITTED = 1, RATING = 4, COMMENT = 5;
    private static final LongWritable ONE = new LongWritable(1);
    private final Text word = new Text();
    private int maxRating;
    private boolean includeUnrated;
    private String from, to;            // optional date window on submitted_at, "yyyy-MM-dd" (inclusive)

    @Override
    protected void setup(Context context) {
        maxRating = context.getConfiguration().getInt("feedback.max.rating", 3);
        includeUnrated = context.getConfiguration().getBoolean("feedback.include.unrated", false);
        from = context.getConfiguration().get("feedback.from", "");
        to = context.getConfiguration().get("feedback.to", "");
    }

    @Override
    protected void map(LongWritable key, Text value, Context context)
            throws IOException, InterruptedException {
        String line = value.toString();
        if (key.get() == 0 && line.startsWith("feedback_id")) {
            context.getCounter(Fb.HEADER_SKIPPED).increment(1);
            return;
        }
        context.getCounter(Fb.ROWS_READ).increment(1);

        List<String> f = TextUtil.parseCsvLine(line);
        if (f.size() < 6) {
            context.getCounter(Fb.MALFORMED_ROWS).increment(1);
            return;
        }

        // Optional period filter, e.g. -D feedback.from=2025-01-01 -D feedback.to=2025-02-28
        String day = f.get(SUBMITTED).length() >= 10 ? f.get(SUBMITTED).substring(0, 10) : "";
        if ((!from.isEmpty() && day.compareTo(from) < 0) || (!to.isEmpty() && day.compareTo(to) > 0)) {
            context.getCounter(Fb.OUTSIDE_PERIOD).increment(1);
            return;
        }

        String rating = f.get(RATING).trim();
        if (rating.isEmpty()) {
            if (!includeUnrated) {
                context.getCounter(Fb.NO_RATING_SKIPPED).increment(1);
                return;
            }
        } else {
            try {
                if (Integer.parseInt(rating) > maxRating) {
                    context.getCounter(Fb.NOT_A_COMPLAINT).increment(1);
                    return;
                }
            } catch (NumberFormatException e) {
                context.getCounter(Fb.MALFORMED_ROWS).increment(1);
                return;
            }
        }
        context.getCounter(Fb.COMMENTS_USED).increment(1);

        for (String w : TextUtil.tokens(TextUtil.normalise(f.get(COMMENT)))) {
            if (w.length() < 2) continue;                       // "a", "s", single Arabic letters
            if (TextUtil.STOP_WORDS.contains(w)) {
                context.getCounter(Fb.STOP_WORDS_REMOVED).increment(1);
                continue;
            }
            context.getCounter(TextUtil.isArabic(w) ? Fb.ARABIC_WORDS : Fb.ENGLISH_WORDS).increment(1);
            word.set(w);
            context.write(word, ONE);
        }
    }
}
