# Structured data — REPLACE THE PLACEHOLDERS

These CSVs are the **ground truth** for every factual answer the agent gives about
slots, course codes, counts, credits and instructor emails. RAG is deliberately not
used for them (vector search cannot count rows or preserve table alignment).

Every row carries a `verified` column:
- `yes` — transcribed from a real IITJ document, safe to be graded on.
- `no`  — **PLACEHOLDER. Replace before submission.**

Replace `no` rows from: this semester's floated-course list, the published timetable
with slot mappings, the faculty directory, and the B.Tech curriculum/credit rules.
Per the assignment brief, personal data (emails, phones) may stay as dummy values —
so `faculty.csv` can keep fabricated addresses, but names and course mappings should
be real if you want the email-drafting answers to be correct.

A wrong row here becomes a confidently wrong, correctly-cited answer — the worst
failure mode for the groundedness metric.
