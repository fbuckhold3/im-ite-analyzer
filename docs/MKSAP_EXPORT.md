# Getting your program's MKSAP export

MKSAP Digital exports are available to **program administrators**. Individual residents cannot export
their own question-level data, so MKSAP analysis in im-ite-analyzer is program-level only
(Program data → Upload & Align → MKSAP).

## Which export?

| Export | What it contains | Use it for |
|---|---|---|
| **Members overview** (recommended) | One row per person: Last Name, First Name, Total Questions, Number Complete, Percentage Complete, Number Correct, Percentage Correct | Progress by class, volume bins, MKSAP vs next ITE — everything except section coverage |
| **Full detail** | One row per person and question: Last Name, First Name, Subspecialty, Question Number, Answered?, Correct? | Everything above **plus** section coverage |

The app detects which one you uploaded. The two exports count the question bank differently (in October 2026:
2,375 questions in the overview vs 3,156 rows per person in the detail), so "% of the bank" is only
comparable within one export type. Totals per person and every ITE analysis agree closely between the two.

## Steps

> TODO: exact MKSAP Digital program-administrator steps (where to log in, which page, which button) —
> to be added by the author once confirmed.

1. Sign in to MKSAP Digital with your program-administrator account.
2. Open your program's member / group view.
3. Download the **members overview** (or the full detail) as **.csv**.
4. Upload the file unchanged on **Program data → Upload & Align**.

## Tips

- Pull the export close to the ITE date if you want MKSAP progress "as of" the exam; note the date you exported.
- Graduates, faculty and other learners in your MKSAP group show up as unmatched accounts — that's expected.
- Never commit or email the export; it identifies residents.
