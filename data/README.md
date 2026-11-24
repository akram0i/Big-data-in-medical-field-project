# Synthetic data artifacts

All project data is synthetic. No real American Hospital Dubai records are present.

The full generated dataset is not committed because it is approximately 1.9 GB. The 2% raw sample is also omitted to keep the assessment repository lightweight. This folder retains the files needed to understand or regenerate the data:

- `synthetic-kit/README.md` — source systems, schemas, joins, and loading notes.
- `synthetic-kit/ANSWER_KEY.md` — planted patterns used to validate the analyses.
- `synthetic-kit/generate_ahd.py` — deterministic generator, seed 312.
- `synthetic-kit/sample_2pct_manifest.json` — row counts for the supplied development sample.

The supplied full archive used for the final Member 7 validation had these authoritative counts:

| Source | Rows |
| --- | ---: |
| Encounters | 780,371 |
| Diagnoses | 1,296,906 |
| Claims | 735,391 |
| Pharmacy dispenses | 1,011,013 |
| Inventory transactions | 99,299 |
| Patient feedback | 92,593 |
| ICU events | 126 |
| ICU vital readings | 5,510,388 |

Generate a fresh full copy with `python3 synthetic-kit/generate_ahd.py --out ahd_data`, or add `--scale 0.02` for a development copy.
