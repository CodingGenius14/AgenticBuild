"""
Console quiz application — all logic in this module per specification.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import random
import secrets
import sys
import zlib
from dataclasses import dataclass, field
from typing import Any

# --- Constants ---
QUESTIONS_PATH = "questions.json"
SCORE_HISTORY_PATH = "score_history.bin"

PBKDF2_ITERATIONS = 310_000
VALID_DIFFICULTIES = ("easy", "medium", "hard")
VALID_TOPICS = ("sports", "pop culture", "economics", "political events")

_MALFORMED_QUESTIONS_MSG = (
    "Required data is missing from the file. Please check the file structure."
)


def load_questions(path: str | None = None) -> list[dict[str, Any]]:
    p = path if path is not None else QUESTIONS_PATH
    if not os.path.isfile(p):
        raise FileNotFoundError(
            f"Question bank not found: '{p}'. Place questions.json in the project directory."
        )
    with open(p, "r", encoding="utf-8") as f:
        raw = f.read().strip()
    if not raw:
        raise ValueError(_MALFORMED_QUESTIONS_MSG)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(_MALFORMED_QUESTIONS_MSG) from e
    questions = data.get("questions")
    if not isinstance(questions, list) or len(questions) == 0:
        raise ValueError(_MALFORMED_QUESTIONS_MSG)
    return questions


def _question_key(q: dict[str, Any]) -> str:
    """Stable id from question content (not list index)."""
    payload = "|".join(
        (
            str(q.get("question", "")),
            str(q.get("type", "")),
            str(q.get("answer", "")),
            str(q.get("topic", "")),
            str(q.get("difficulty", "")),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _pbkdf2_password_hash(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
        dklen=32,
    )


def _derive_stats_key(password: str, stats_salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        stats_salt,
        PBKDF2_ITERATIONS,
        dklen=32,
    )


def _xor_keystream(key: bytes, nbytes: int) -> bytes:
    """Stdlib-only XOR stream from HMAC-SHA256 blocks (counter mode)."""
    out = bytearray()
    counter = 0
    while len(out) < nbytes:
        block = hmac.new(
            key,
            counter.to_bytes(8, "big"),
            hashlib.sha256,
        ).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:nbytes])


def _encrypt_stats_plaintext(plaintext: bytes, stats_key: bytes) -> bytes:
    ks = _xor_keystream(stats_key, len(plaintext))
    return bytes(a ^ b for a, b in zip(plaintext, ks))


def _decrypt_stats_ciphertext(ciphertext: bytes, stats_key: bytes) -> bytes:
    return _encrypt_stats_plaintext(ciphertext, stats_key)


def _empty_user_stats() -> dict[str, Any]:
    return {
        "sessions": [],
        "aggregate": {
            "quizzes_taken": 0,
            "questions_answered": 0,
            "questions_correct": 0,
            "topics": {},
            "difficulties": {},
        },
        "feedback": {},
    }


@dataclass
class UserSession:
    username: str
    stats_key: bytes
    stats_salt: bytes
    stats: dict[str, Any] = field(default_factory=_empty_user_stats)


def _parse_root_json(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize v2 root; warn if legacy unauthenticated format."""
    if "users" not in data and ("sessions" in data or "feedback" in data):
        print(
            "Warning: score history uses an older format without accounts; "
            "it will be ignored. Register a new account to continue.",
            file=sys.stderr,
        )
        return {"v": 2, "users": {}, "encrypted_payloads_b64": {}}
    if not isinstance(data, dict):
        return {"v": 2, "users": {}, "encrypted_payloads_b64": {}}
    data.setdefault("v", 2)
    data.setdefault("users", {})
    data.setdefault("encrypted_payloads_b64", {})
    return data


def _load_disk_root() -> dict[str, Any]:
    """Load outer JSON (usernames + salts + encrypted payloads), zlib+base64 on disk."""
    empty: dict[str, Any] = {"v": 2, "users": {}, "encrypted_payloads_b64": {}}
    if not os.path.isfile(SCORE_HISTORY_PATH):
        return empty
    try:
        with open(SCORE_HISTORY_PATH, "rb") as f:
            raw = f.read()
        if not raw:
            return empty
        decoded = base64.b64decode(raw)
        decompressed = zlib.decompress(decoded)
        data = json.loads(decompressed.decode("utf-8"))
        return _parse_root_json(data)
    except (OSError, zlib.error, json.JSONDecodeError, ValueError, UnicodeDecodeError):
        print(
            "Warning: score history file is corrupt or unreadable; "
            "starting with empty accounts. Previous stats could not be recovered.",
            file=sys.stderr,
        )
        return empty


def _save_disk_root(root: dict[str, Any]) -> None:
    text = json.dumps(root, separators=(",", ":"))
    compressed = zlib.compress(text.encode("utf-8"), level=9)
    encoded = base64.b64encode(compressed)
    with open(SCORE_HISTORY_PATH, "wb") as f:
        f.write(encoded)


def _decode_user_stats(
    username: str,
    password: str,
    root: dict[str, Any],
) -> UserSession | None:
    """
    Returns session on success, None if password does not match.
    Raises ValueError if stored account metadata is unreadable.
    """
    users = root.get("users") or {}
    if username not in users:
        return None
    meta = users[username]
    try:
        pwd_salt = base64.b64decode(meta["pwd_salt_b64"])
        pwd_hash_stored = base64.b64decode(meta["pwd_hash_b64"])
        stats_salt = base64.b64decode(meta["stats_salt_b64"])
    except (KeyError, ValueError, TypeError) as e:
        raise ValueError(
            "Stored account data is unreadable. Try re-registering or delete the "
            "score history file."
        ) from e

    pwd_hash = _pbkdf2_password_hash(password, pwd_salt)
    if not secrets.compare_digest(pwd_hash, pwd_hash_stored):
        return None

    stats_key = _derive_stats_key(password, stats_salt)
    payloads = root.get("encrypted_payloads_b64") or {}
    b64 = payloads.get(username)
    if not b64:
        sess = UserSession(username=username, stats_key=stats_key, stats_salt=stats_salt)
        sess.stats = _empty_user_stats()
        return sess

    try:
        ct = base64.b64decode(b64)
        pt = _decrypt_stats_ciphertext(ct, stats_key)
        decompressed = zlib.decompress(pt)
        stats = json.loads(decompressed.decode("utf-8"))
        if not isinstance(stats, dict):
            raise ValueError("stats not a dict")
    except (zlib.error, json.JSONDecodeError, ValueError, UnicodeDecodeError):
        print(
            f"Warning: could not decrypt or read stored stats for {username!r}; "
            "starting fresh stats for this account.",
            file=sys.stderr,
        )
        sess = UserSession(username=username, stats_key=stats_key, stats_salt=stats_salt)
        sess.stats = _empty_user_stats()
        return sess

    sess = UserSession(username=username, stats_key=stats_key, stats_salt=stats_salt)
    sess.stats = stats
    sess.stats.setdefault("sessions", [])
    sess.stats.setdefault("feedback", {})
    sess.stats.setdefault(
        "aggregate",
        {
            "quizzes_taken": 0,
            "questions_answered": 0,
            "questions_correct": 0,
            "topics": {},
            "difficulties": {},
        },
    )
    return sess


def _persist_user_stats(sess: UserSession, root: dict[str, Any]) -> None:
    payload = json.dumps(sess.stats, separators=(",", ":")).encode("utf-8")
    compressed = zlib.compress(payload, level=9)
    ct = _encrypt_stats_plaintext(compressed, sess.stats_key)
    b64 = base64.b64encode(ct).decode("ascii")
    root.setdefault("encrypted_payloads_b64", {})[sess.username] = b64
    _save_disk_root(root)


def register_user(username: str, password: str, root: dict[str, Any]) -> UserSession:
    users = root.setdefault("users", {})
    if username in users:
        raise ValueError("That username is already registered.")
    if not username.strip():
        raise ValueError("Username must be non-empty.")
    if not password:
        raise ValueError("Password must be non-empty.")

    pwd_salt = os.urandom(16)
    stats_salt = os.urandom(16)
    pwd_hash = _pbkdf2_password_hash(password, pwd_salt)
    users[username] = {
        "pwd_salt_b64": base64.b64encode(pwd_salt).decode("ascii"),
        "pwd_hash_b64": base64.b64encode(pwd_hash).decode("ascii"),
        "stats_salt_b64": base64.b64encode(stats_salt).decode("ascii"),
    }
    stats_key = _derive_stats_key(password, stats_salt)
    sess = UserSession(username=username, stats_key=stats_key, stats_salt=stats_salt)
    sess.stats = _empty_user_stats()
    _persist_user_stats(sess, root)
    return sess


def login_or_register() -> tuple[UserSession, dict[str, Any]]:
    root = _load_disk_root()
    mode = (
        input("Log in or register? Type 'login' or 'register': ")
        .strip()
        .lower()
    )
    if mode not in ("login", "register"):
        raise ValueError("Expected 'login' or 'register'.")

    username = input("Username: ").strip()
    if not username:
        raise ValueError("Username must be non-empty.")

    password = input("Password: ")

    if mode == "register":
        password2 = input("Confirm password: ")
        if password != password2:
            raise ValueError("Passwords do not match.")
        return register_user(username, password, root), root

    if username not in (root.get("users") or {}):
        raise ValueError("Unknown username or wrong password.")
    sess = _decode_user_stats(username, password, root)
    if sess is None:
        raise ValueError("Unknown username or wrong password.")
    return sess, root


def get_feedback_weights(sess: UserSession) -> dict[str, tuple[int, int]]:
    raw = sess.stats.get("feedback", {})
    out: dict[str, tuple[int, int]] = {}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        if isinstance(v, dict) and ("likes" in v or "dislikes" in v):
            out[str(k)] = (int(v.get("likes", 0)), int(v.get("dislikes", 0)))
    return out


def record_feedback(
    sess: UserSession,
    root: dict[str, Any],
    qkey: str,
    liked: bool,
) -> None:
    fb = sess.stats.setdefault("feedback", {}).setdefault(
        qkey, {"likes": 0, "dislikes": 0}
    )
    if liked:
        fb["likes"] = fb.get("likes", 0) + 1
    else:
        fb["dislikes"] = fb.get("dislikes", 0) + 1
    _persist_user_stats(sess, root)


def append_session_stats(
    sess: UserSession,
    root: dict[str, Any],
    topic: str,
    difficulty: str,
    correct: int,
    incorrect: int,
    total: int,
) -> None:
    sess.stats.setdefault("sessions", []).append(
        {
            "topic": topic,
            "difficulty": difficulty,
            "correct": correct,
            "incorrect": incorrect,
            "total": total,
            "percentage": round(100.0 * correct / total, 1) if total else 0.0,
        }
    )
    agg = sess.stats.setdefault(
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
    agg.setdefault("topics", {})
    agg.setdefault("difficulties", {})
    agg["topics"][topic] = agg["topics"].get(topic, 0) + 1
    agg["difficulties"][difficulty] = agg["difficulties"].get(difficulty, 0) + 1
    _persist_user_stats(sess, root)


def weighted_question_order(
    pool: list[tuple[int, dict[str, Any]]],
    weights_map: dict[str, tuple[int, int]],
) -> list[tuple[int, dict[str, Any]]]:
    """Liked questions get higher weight; disliked lower. Random weighted shuffle."""
    weighted: list[tuple[int, dict[str, Any], float]] = []
    for idx, q in pool:
        key = _question_key(q)
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
        return ""
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
        if got not in ("true", "false"):
            return False
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
    sess: UserSession,
    root: dict[str, Any],
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

    weights_map = get_feedback_weights(sess)
    ordered = weighted_question_order(pool, weights_map)

    correct_n = 0
    incorrect_n = 0
    total = len(ordered)

    for idx, q in ordered:
        qkey = _question_key(q)
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

        rate = (
            input("Rate this question — type 'like' or 'dislike': ").strip().lower()
        )
        if rate == "like":
            record_feedback(sess, root, qkey, True)
        elif rate == "dislike":
            record_feedback(sess, root, qkey, False)
        else:
            raise ValueError(
                "Invalid rating. Expected 'like' or 'dislike'."
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
    append_session_stats(sess, root, topic, difficulty, correct_n, incorrect_n, total)
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
    sess, root = login_or_register()
    print(f"Signed in as {sess.username!r}.")

    diff = prompt_difficulty()
    topic = prompt_topic()

    print()
    print(f"You chose difficulty {diff!r} and topic {topic!r}.")
    start = input("Enter y to begin the quiz: ").strip().lower()
    if start != "y":
        raise ValueError(
            "Invalid input. Enter 'y' to begin the quiz."
        )

    run_quiz(all_q, diff, topic, sess, root)


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        msg = str(e)
        if msg == _MALFORMED_QUESTIONS_MSG:
            print(msg, file=sys.stderr)
        else:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
