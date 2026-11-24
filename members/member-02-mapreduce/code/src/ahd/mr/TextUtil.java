package ahd.mr;

import java.text.Normalizer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Pattern;

/** Shared text helpers for the feedback word count: CSV parsing, normalisation, stop words, script detection. */
public final class TextUtil {

    private TextUtil() {}

    private static final Pattern NON_LETTERS = Pattern.compile("[^\\p{L}]+");
    /** Arabic short vowels / tanween (combining marks) and the tatweel stretch character. */
    private static final Pattern ARABIC_MARKS = Pattern.compile("[\\p{Mn}\\u0640]");
    /** Hamza forms of alef -> bare alef, so "إلى" and "الى" count as one word. */
    private static final Pattern ALEF_FORMS = Pattern.compile("[\\u0622\\u0623\\u0625]");

    public static final Set<String> STOP_WORDS = new HashSet<String>(Arrays.asList(
        // English: standard list
        "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", "as", "at",
        "be", "because", "been", "before", "being", "below", "between", "both", "but", "by", "can", "could",
        "did", "do", "does", "doing", "down", "during", "each", "few", "for", "from", "further", "had", "has",
        "have", "having", "he", "her", "here", "hers", "him", "his", "how", "i", "if", "in", "into", "is", "it",
        "its", "just", "me", "more", "most", "my", "myself", "no", "nor", "not", "now", "of", "off", "on", "once",
        "only", "or", "other", "our", "ours", "out", "over", "own", "same", "she", "should", "so", "some", "such",
        "than", "that", "the", "their", "them", "then", "there", "these", "they", "this", "those", "through", "to",
        "too", "under", "until", "up", "us", "very", "was", "we", "were", "what", "when", "where", "which", "while",
        "who", "whom", "why", "will", "with", "would", "you", "your",
        // English: filler words that carry no theme in survey comments
        "still", "nobody", "kept", "took", "said", "asked", "come", "get", "got", "also", "even",
        // Arabic (already normalised: no diacritics, bare alef)
        "في", "من", "على", "الى", "عن", "مع", "او", "ثم", "قد", "كل", "ذلك", "هذا", "هذه", "التي", "الذي",
        "كان", "كانت", "يتم", "تم", "لم", "ولم", "لا", "ما", "جدا", "بعد", "قبل", "عند", "حتى", "ان", "و"
    ));

    /** Lower-case, strip Arabic diacritics/tatweel, unify alef forms. */
    public static String normalise(String s) {
        String t = Normalizer.normalize(s, Normalizer.Form.NFKC);
        t = ARABIC_MARKS.matcher(t).replaceAll("");
        t = ALEF_FORMS.matcher(t).replaceAll("ا");
        return t.toLowerCase(Locale.ROOT);
    }

    /** Words made only of letters (any script). Numbers and punctuation are separators. */
    public static String[] tokens(String normalised) {
        return NON_LETTERS.split(normalised);
    }

    /** True if the word is written in Arabic script. */
    public static boolean isArabic(String word) {
        if (word == null || word.isEmpty()) return false;
        Character.UnicodeBlock b = Character.UnicodeBlock.of(word.codePointAt(0));
        return b == Character.UnicodeBlock.ARABIC
            || b == Character.UnicodeBlock.ARABIC_SUPPLEMENT
            || b == Character.UnicodeBlock.ARABIC_PRESENTATION_FORMS_A
            || b == Character.UnicodeBlock.ARABIC_PRESENTATION_FORMS_B;
    }

    /**
     * Minimal RFC-4180 CSV line parser: handles "quoted, fields" and "" escapes.
     * Needed because Python's csv writer quotes comments that contain commas.
     */
    public static List<String> parseCsvLine(String line) {
        List<String> fields = new ArrayList<String>();
        StringBuilder cur = new StringBuilder();
        boolean inQuotes = false;
        for (int i = 0; i < line.length(); i++) {
            char c = line.charAt(i);
            if (inQuotes) {
                if (c == '"') {
                    if (i + 1 < line.length() && line.charAt(i + 1) == '"') { cur.append('"'); i++; }
                    else inQuotes = false;
                } else cur.append(c);
            } else if (c == '"') {
                inQuotes = true;
            } else if (c == ',') {
                fields.add(cur.toString());
                cur.setLength(0);
            } else cur.append(c);
        }
        fields.add(cur.toString());
        return fields;
    }
}
