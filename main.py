"""
Console quiz application — all logic in this module per specification.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import sys
import zlib
from typing import Any

# --- Constants ---
QUESTIONS_PATH = "questions.json"
SCORE_HISTORY_PATH = "score_history.bin"

VALID_DIFFICULTIES = ("easy", "medium", "hard")
VALID_TOPICS = ("sports", "pop culture", "economics", "political events")


def load_questions(path: str | None = None) -> list[dict[str, Any]]:
    p = path if path is not None else QUESTIONS_PATH
    if not os.path.isfile(p):
        raise FileNotFoundError(
            f"Question bank not found: '{p}'. Place questions.json in the project directory."
        )
    raw = open(p, "r", encoding="utf-8").read().strip()
    if not raw:
        print("Required data is missing from the file. Please check the file structure.")
        sys.exit(1)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print("Required data is missing from the file. Please check the file structure.")
        sys.exit(1)
    questions = data.get("questions")
    if not isinstance(questions, list) or len(questions) == 0:
        print("Required data is missing from the file. Please check the file structure.")
        sys.exit(1)
    return questions


def _question_key(q: dict[str, Any], index: int) -> str:
    text = str(q.get("question", ""))
    return hashlib.sha256(f"{index}:{text}".encode("utf-8")).hexdigest()[:24]


def _load_score_blob() -> dict[str, Any]:
    if not os.path.isfile(SCORE_HISTORY_PATH):
        return {}
    try:
        with open(SCORE_HISTORY_PATH, "rb") as f:
            raw = f.read()
        if not raw:
            return {}
        decoded = base64.b64decode(raw)
        decompressed = zlib.decompress(decoded)
        return json.loads(decompressed.decode("utf-8"))
    except (OSError, zlib.error, json.JSONDecodeError, ValueError):
        return {}


def _save_score_blob(blob: dict[str, Any]) -> None:
    payload = json.dumps(blob, separators=(",", ":")).encode("utf-8")
    compressed = zlib.compress(payload, level=9)
    encoded = base64.b64encode(compressed)
    with open(SCORE_HISTORY_PATH, "wb") as f:
        f.write(encoded)


def get_feedback_weights() -> dict[str, tuple[int, int]]:
    """Returns question_key -> (likes, dislikes) from anonymous global feedback."""
    blob = _load_score_blob()
    raw = blob.get("feedback", {})
    out: dict[str, tuple[int, int]] = {}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        if isinstance(v, dict) and ("likes" in v or "dislikes" in v):
            out[str(k)] = (int(v.get("likes", 0)), int(v.get("dislikes", 0)))
    return out


def record_feedback(qkey: str, liked: bool) -> None:
    blob = _load_score_blob()
    fb = blob.setdefault("feedback", {}).setdefault(
        qkey, {"likes": 0, "dislikes": 0}
    )
    if liked:
        fb["likes"] = fb.get("likes", 0) + 1
    else:
        fb["dislikes"] = fb.get("dislikes", 0) + 1
    _save_score_blob(blob)


def append_session_stats(
    topic: str,
    difficulty: str,
    correct: int,
    incorrect: int,
    total: int,
) -> None:
    blob = _load_score_blob()
    blob.setdefault("sessions", []).append(
        {
            "topic": topic,
            "difficulty": difficulty,
            "correct": correct,
            "incorrect": incorrect,
            "total": total,
            "percentage": round(100.0 * correct / total, 1) if total else 0.0,
        }
    )
    agg = blob.setdefault(
        "aggregate",
        {
            "quizzes_taken": 0,
            "questions_answered": 0,
            "questions_correct": 0,
            "topics": {},
            "difficulties": {},
        },
    )
    agg["quizzes_taken"] = agg.get("quizzes_taken", 0) + 1
    agg["questions_answered"] = agg.get("questions_answered", 0) + total
    agg["questions_correct"] = agg.get("questions_correct", 0) + correct
    agg["topics"][topic] = agg["topics"].get(topic, 0) + 1
    agg["difficulties"][difficulty] = agg["difficulties"].get(difficulty, 0) + 1
    _save_score_blob(blob)


def weighted_question_order(
    pool: list[tuple[int, dict[str, Any]]],
    weights_map: dict[str, tuple[int, int]],
) -> list[tuple[int, dict[str, Any]]]:
    """Liked questions get higher weight; disliked lower. Random weighted shuffle."""
    weighted: list[tuple[int, dict[str, Any], float]] = []
    for idx, q in pool:
        key = _question_key(q, idx)
        likes, dislikes = weights_map.get(key, (0, 0))
        w = 1.0 + (likes * 0.6) - (dislikes * 0.4)
        if w < 0.15:
            w = 0.15
        weighted.append((idx, q, w))
    out: list[tuple[int, dict[str, Any]]] = []
    remaining = weighted.copy()
    while remaining:
        total_w = sum(w for _, _, w in remaining)
        r = random.uniform(0, total_w)
        acc = 0.0
        chosen_i = 0
        for i, (_, _, w) in enumerate(remaining):
            acc += w
            if r <= acc:
                chosen_i = i
                break
        item = remaining.pop(chosen_i)
        out.append((item[0], item[1]))
    return out


def normalize_answer(qtype: str, raw: str) -> str:
    s = raw.strip()
    if qtype == "true_false":
        low = s.lower()
        if low in ("t", "true", "1", "yes", "y"):
            return "true"
        if low in ("f", "false", "0", "no", "n"):
            return "false"
        return low
    if qtype == "short_answer":
        return s.lower()
    if qtype == "multiple_choice":
        return s.strip()
    return s


def check_correct(q: dict[str, Any], user_ans: str) -> bool:
    qtype = q.get("type", "")
    expected = str(q.get("answer", ""))
    if qtype == "multiple_choice":
        opts = q.get("options")
        ua = user_ans.strip()
        if isinstance(opts, list) and ua.isdigit():
            n = int(ua)
            if 1 <= n <= len(opts):
                ua = str(opts[n - 1])
        got = ua.strip().lower()
        return got == expected.strip().lower()
    got = normalize_answer(qtype, user_ans)
    if qtype == "short_answer":
        return got == expected.strip().lower()
    if qtype == "true_false":
        return got == expected.strip().lower()
    return False


def prompt_difficulty() -> str:
    s = input(
        f"Choose difficulty ({', '.join(VALID_DIFFICULTIES)}): "
    ).strip().lower()
    if s not in VALID_DIFFICULTIES:
        raise ValueError(
            f"Invalid difficulty. Expected one of: {', '.join(VALID_DIFFICULTIES)}."
        )
    return s


def prompt_topic() -> str:
    raw = input(
        f"Choose topic ({', '.join(repr(t) for t in VALID_TOPICS)}): "
    ).strip()
    s = " ".join(raw.lower().split())
    topic_map = {t.lower(): t for t in VALID_TOPICS}
    if s in topic_map:
        return topic_map[s]
    raise ValueError(
        f"Invalid topic. Expected one of: {', '.join(VALID_TOPICS)}."
    )


def display_question(q: dict[str, Any]) -> None:
    print()
    print(q.get("question", ""))
    qtype = q.get("type", "")
    if qtype == "multiple_choice":
        opts = q.get("options") or []
        if not isinstance(opts, list):
            raise ValueError(
                "Invalid question data: multiple_choice requires an options array."
            )
        for i, opt in enumerate(opts, start=1):
            print(f"  {i}. {opt}")
        print("Enter the option text or its number.")


def run_quiz(
    questions: list[dict[str, Any]],
    difficulty: str,
    topic: str,
) -> None:
    pool: list[tuple[int, dict[str, Any]]] = []
    for i, q in enumerate(questions):
        if q.get("difficulty") != difficulty or q.get("topic") != topic:
            continue
        pool.append((i, q))
    if not pool:
        print(
            f"No questions found for topic {topic!r} and difficulty {difficulty!r}. "
            "Try another combination."
        )
        return

    weights_map = get_feedback_weights()
    ordered = weighted_question_order(pool, weights_map)

    correct_n = 0
    incorrect_n = 0
    total = len(ordered)

    for idx, q in ordered:
        qkey = _question_key(q, idx)
        display_question(q)
        ans = input("Your answer: ")
        is_ok = check_correct(q, ans)
        expected = str(q.get("answer", ""))
        if is_ok:
            print("✅ Correct")
            correct_n += 1
        else:
            print("❌ Incorrect")
            incorrect_n += 1
        print(f"The correct answer is: {expected}")

        rate = input("Rate this question — type 'like' or 'dislike': ").strip().lower()
        if rate in ("like", "l"):
            record_feedback(qkey, True)
        elif rate in ("dislike", "d"):
            record_feedback(qkey, False)
        else:
            raise ValueError(
                "Invalid rating. Expected 'like' or 'dislike' (or 'l' / 'd')."
            )

        proceed = input("Enter y to proceed to the next question: ").strip().lower()
        if proceed != "y":
            raise ValueError(
                "Invalid input. Enter 'y' to proceed to the next question."
            )

    pct = round(100.0 * correct_n / total, 1) if total else 0.0
    print()
    print("--- Quiz complete ---")
    print(f"Final score: {correct_n} / {total} ({pct}%)")
    print(
        f"Session summary — topic: {topic}, difficulty: {difficulty}, "
        f"correct: {correct_n}, incorrect: {incorrect_n}"
    )
    append_session_stats(topic, difficulty, correct_n, incorrect_n, total)
    print("Stats have been saved.")


def _configure_stdio_utf8() -> None:
    """Avoid UnicodeEncodeError for ✅/❌ on Windows consoles (cp1252)."""
    reconf = getattr(sys.stdout, "reconfigure", None)
    if callable(reconf):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass
    reerr = getattr(sys.stderr, "reconfigure", None)
    if callable(reerr):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def main() -> None:
    _configure_stdio_utf8()
    random.seed()
    try:
        all_q = load_questions()
    except FileNotFoundError as e:
        raise FileNotFoundError(str(e)) from e

    print("Welcome to the Quiz App.")
    diff = prompt_difficulty()
    topic = prompt_topic()

    print()
    print(f"You chose difficulty {diff!r} and topic {topic!r}.")
    start = input("Enter y to begin the quiz: ").strip().lower()
    if start != "y":
        raise ValueError(
            "Invalid input. Enter 'y' to begin the quiz."
        )

    run_quiz(all_q, diff, topic)


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
