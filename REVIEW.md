# Code review: `main.py` vs `spec.md`

Review of the Python code against the technical specification. Line references point to `main.py` unless noted.

---

## Findings

1. **[FAIL] Startup login and registration** — Spec §Application Behavior 1, §Required Features Authentication: the app must present login/register on launch with username and password. `main()` goes straight from “Welcome” to difficulty/topic (`322–340`). There is no login, registration, or credential handling anywhere in the project.

2. **[FAIL] Password hashing** — Spec requires passwords stored hashed, not plaintext. `main.py` never stores or verifies passwords; `hashlib` is only used for question keys (`46–48`), not authentication.

3. **[FAIL] Per-user score history** — Spec §Score History: “Track and persist **per-user** statistics across sessions.” `append_session_stats` (`99–132`) appends to a global `sessions` list with no user identifier; all runs share one history. Not per-user.

4. **[WARN] Scores must not be discoverable in the history file** — Spec: “Usernames may be discoverable … but **passwords and scores must not be**.” The blob is JSON → zlib → base64 (`66–71`, `55–61`). That is encoding/compression, not confidentiality; scores and counts are plain JSON before compression and can be recovered trivially. This does not meet the stated privacy bar for scores.

5. **[PASS] Non-human-readable history file (casual reading)** — The file is binary-ish (base64+zlib) and not meant to be edited as text, which aligns with “non-human-readable” in a weak sense, but see finding 4 for the stricter “scores not discoverable” requirement.

6. **[PASS] Quiz setup: difficulty and topic** — `VALID_DIFFICULTIES` / `VALID_TOPICS` (`20–21`), `prompt_difficulty` (`201–209`), `prompt_topic` (`212–223`), and filtering in `run_quiz` (`246–249`) match the spec tables.

7. **[PASS] Quiz confirmation before start** — After choices, the app prints difficulty and topic and requires `y` to begin (`334–340`).

8. **[PASS] Question flow: answer, correctness, correct answer, rating, proceed** — `run_quiz` (`264–292`) shows the question, reads an answer, prints ✅/❌ and the correct answer, asks for like/dislike, then requires `y` to continue.

9. **[WARN] Like/dislike UX vs spec wording** — Spec §4 says users rate with “like / dislike”; the code accepts `like`/`dislike` or `l`/`d` (`278–286`). Reasonable extension; not a spec violation.

10. **[PASS] Feedback affects future selection** — `weighted_question_order` (`135–162`) boosts weight for likes and reduces for dislikes, with a floor (`145–146`). `record_feedback` updates the blob (`87–96`).

11. **[WARN] Feedback is global, not per-user** — Weights are keyed by question id only (`74–84`, `88–96`), with no user id. If “personalized” implies per-user preferences, this is incomplete; the spec is ambiguous here.

12. **[PASS] End-of-quiz summary and persistence** — Final score, percentage, session summary (`294–301`), and `append_session_stats` (`302`) match §5.

13. **[PASS] File layout** — `main.py` + `questions.json` per §File Structure (only those two as core artifacts).

14. **[PASS] Editable `questions.json`** — Questions load from file (`24–43`); no code changes needed to swap content.

15. **[PASS] `questions.json` missing → `FileNotFoundError`** — `26–29`, `325–328`, `346–350`.

16. **[WARN] Invalid input: spec says raise `ValueError`** — Many paths do (`206–208`, `220–222`, `284–291`, `337–340`, `351–353`). For **empty or malformed** JSON, `load_questions` **prints** the required message and **`sys.exit(1)`** (`31–33`, `36–38`, `40–42`) instead of raising `ValueError`. The error table only mandates the message for condition 3, not necessarily `ValueError`, but it is **inconsistent** with row 2’s “raise ValueError” pattern.

17. **[PASS] Empty/malformed `questions.json` message** — The exact text *“Required data is missing from the file. Please check the file structure.”* appears for empty file, JSON decode failure, and missing/empty `questions` list (`32–33`, `37–38`, `41–42`).

18. **[WARN] `load_questions` uses `open` without `with`** — `30` uses `open(p, "r", encoding="utf-8").read()`; a context manager would be safer and clearer (minor quality/resource pattern).

19. **[WARN] Corrupt `score_history.bin`** — `_load_score_blob` (`62–63`) swallows all errors and returns `{}`, silently discarding history. Users lose data without notice.

20. **[WARN] `check_correct` / `normalize_answer` edge cases** — `true_false`: unrecognized input falls through to `low` (`167–173`) and may still match `expected` if bizarre; low risk. `short_answer`: substring/word rules not specified; exact match after lowercasing is consistent.

21. **[PASS] Standard library only** — Imports `7–14` are stdlib; no extra dependencies.

22. **[PASS] Console-only** — No web/GUI usage.

23. **[WARN] Question identity for feedback** — `_question_key` (`46–48`) uses index in the full bank plus question text. Editing `questions.json` (reorder/remove) can change keys and orphan or split feedback counts; acceptable tradeoff but worth knowing for maintainers.

24. **[FAIL] Authentication and score features cannot be “implemented correctly” in aggregate** — Because login, hashed passwords, and per-user stats are absent, the **authentication** and **per-user score history** requirements are not met, regardless of other strengths.

---

## Summary

The quiz loop, validation prompts, confirmation step, like/dislike weighting, zlib-based history file, and error message for bad JSON are largely aligned with the spec. **Critical gaps:** no **login or registration**, no **password hashing**, and **no per-user** history. **Score confidentiality** as written (“scores must not” be discoverable) is **not** satisfied by base64+zlib of JSON. Minor issues: **`load_questions`** exit vs raise inconsistency, **bare `open`** on line 30, and **silent reset** of corrupt score files.
