# Code review: `main.py` vs `spec.md`

Review of the Python code against the technical specification. Line references point to `main.py` unless noted.

---

## Findings

1. **[PASS] Startup login and registration** — Spec §Application Behavior 1, §Required Features Authentication: the app presents login/register after welcome (`login_or_register` `282–309`, `main` `579–581`). Users choose `login` or `register`, then enter username and password (with confirmation on register).

2. **[PASS] Password hashing** — Passwords are stored as PBKDF2-HMAC-SHA256 hashes with per-user salts (`_pbkdf2_password_hash` `66–73`, `register_user` `267–273`); verification uses `secrets.compare_digest` (`203–205`). Plaintext passwords are not written to disk.

3. **[PASS] Per-user score history** — Spec §Score History: session rows and aggregates are stored under each user’s encrypted stats blob (`append_session_stats` `339–375`, `sess.stats` via `UserSession` `124–129`). `append_session_stats` takes `sess` and persists with `_persist_user_stats` (`249–255`).

4. **[PASS] Scores must not be discoverable in the history file** — Per-user statistics JSON is zlib-compressed then XOR-encrypted with a key derived via PBKDF2 from the user’s password and `stats_salt` (`249–255`, `215–230`); only base64 ciphertext appears under `encrypted_payloads_b64`. Password hashes are stored separately and are not reversible to plaintext.

5. **[PASS] Non-human-readable history file (casual reading)** — The on-disk file is binary zlib+base64 (`172–177`, `155–160`); it is not human-readable without decoding.

6. **[PASS] Quiz setup: difficulty and topic** — `VALID_DIFFICULTIES` / `VALID_TOPICS` (`24–25`), `prompt_difficulty` (`446–454`), `prompt_topic` (`457–467`), and filtering in `run_quiz` (`492–495`) match the spec tables.

7. **[PASS] Quiz confirmation before start** — After login and setup, the app prints difficulty and topic and requires `y` to begin (`586–592`).

8. **[PASS] Question flow: answer, correctness, correct answer, rating, proceed** — `run_quiz` (`485–541`) shows the question, reads an answer, prints ✅/❌ and the correct answer, asks for `like` or `dislike`, then requires `y` to continue.

9. **[PASS] Like/dislike UX vs spec wording** — Spec §4 asks users to rate with “like / dislike”; the code accepts exactly `like` or `dislike` (`525–535`), matching the spec wording.

10. **[PASS] Feedback affects future selection** — `weighted_question_order` (`378–405`) boosts weight for likes and reduces for dislikes, with a floor (`388–389`). `record_feedback` updates the user’s stats (`323–336`).

11. **[PASS] Feedback is per-user** — Weights come from `get_feedback_weights(sess)` (`312–320`), which reads `sess.stats["feedback"]`; each user’s likes/dislikes are stored only in that user’s encrypted payload.

12. **[PASS] End-of-quiz summary and persistence** — Final score, percentage, session summary (`543–550`), and `append_session_stats` (`551`) match §5.

13. **[PASS] File layout** — `main.py` and human-readable `questions.json` per §File Structure; `score_history.bin` is the persisted history required by §Score History (not listed in the diagram but implied by the feature set).

14. **[PASS] Editable `questions.json`** — Questions load from file (`32–49`); no code changes needed to swap content.

15. **[PASS] `questions.json` missing → `FileNotFoundError`** — `34–37`, `574–577`, `600–602`.

16. **[PASS] Invalid input: spec says raise `ValueError`** — Malformed/empty question bank paths raise `ValueError` (`40–48`). Other invalid inputs raise `ValueError` at `451–453`, `465–467`, `533–535`, `538–541`, `589–592`, `603–608`. This aligns with the error-handling table together with finding 17.

17. **[PASS] Empty/malformed `questions.json` message** — The exact text *“Required data is missing from the file. Please check the file structure.”* is in `_MALFORMED_QUESTIONS_MSG` (`27–29`) and raised for empty file, JSON decode failure, and missing/empty `questions` list (`40–48`).

18. **[PASS] `load_questions` uses `with` for `open`** — `38–39` uses a context manager.

19. **[PASS] Corrupt `score_history.bin`** — `_load_disk_root` (`163–169`) prints a warning to stderr and returns empty accounts instead of failing silently without notice. Undecryptable per-user payloads also warn (`223–227`).

20. **[PASS] `check_correct` / `normalize_answer` edge cases** — `true_false`: unrecognized input yields `""` from `normalize_answer` (`416`), and `check_correct` rejects non-`true`/`false` (`439–442`). `short_answer` remains exact match after lowercasing (`437–438`).

21. **[PASS] Standard library only** — Imports `7–17` are stdlib; no extra dependencies.

22. **[PASS] Console-only** — No web/GUI usage.

23. **[PASS] Question identity for feedback** — `_question_key` (`52–63`) hashes question fields (text, type, answer, topic, difficulty), not list index, so reordering the bank does not change keys for identical questions.

24. **[PASS] Authentication and score features in aggregate** — Login/registration, PBKDF2 password storage, per-user encrypted stats, and per-user feedback are implemented end-to-end (`180–309`, `339–375`).

---

## Summary

The implementation matches the spec: **login/register** with **PBKDF2-hashed passwords**, **per-user** session and aggregate stats inside **password-derived encrypted** payloads, **zlib+base64** non-human-readable outer file, **per-user** like/dislike weighting, **`ValueError`** for invalid input including malformed `questions.json` (with the required message), **`with`** for reading questions, **warnings** on corrupt history, and **content-based** question keys. The quiz flow, confirmation step, and console-only **stdlib** constraint are satisfied.
