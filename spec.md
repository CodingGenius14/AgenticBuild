# Quiz App — Technical Specification

## Overview

A console-based Python quiz application with user authentication, personalized question delivery, and persistent score tracking. No APIs, GUIs, HTML, or CSS — fully terminal-driven.

---

## Application Behavior

### 1. Startup & Login
- On launch, the app presents a login prompt.
- Users may log in with an existing username and password, or register a new account.
- Passwords must be stored securely (hashed — not stored in plain text).

### 2. Quiz Setup
Once logged in, the user is guided through two setup prompts:

| Step | Prompt | Options |
|------|--------|---------|
| 1 | Choose a difficulty level | `easy`, `medium`, `hard` |
| 2 | Choose a topic category | `sports`, `pop culture`, `economics`, `political events` |

### 3. Quiz Confirmation
After selecting preferences, the app displays a confirmation message summarizing the chosen difficulty and topic, then prompts the user to enter `y` to begin.

### 4. Question Flow
For each question:
1. The question is displayed.
2. The user submits their answer.
3. The app responds with:
   - ✅ **Correct** or ❌ **Incorrect**
   - The correct answer (always displayed)
   - A prompt asking the user to rate the question (like / dislike)
4. The user enters `y` to proceed to the next question.

### 5. End of Quiz
After all questions are answered, the app displays:
- Final score and percentage
- A session summary (topic, difficulty, number correct/incorrect)
- Updated stats saved to the score history file

---

## File Structure

```
project/
├── main.py          # All application logic, functions, and imports
└── questions.json   # Human-readable question bank
```

---

## Data Format

### Question Bank (`questions.json`)

All questions are stored in a single top-level `"questions"` array. Each entry follows this schema:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `question` | string | ✅ | The question text |
| `type` | string | ✅ | One of: `multiple_choice`, `true_false`, `short_answer` |
| `options` | array | ⚠️ | Required only for `multiple_choice` questions |
| `answer` | string | ✅ | The correct answer |
| `topic` | string | ✅ | One of: `sports`, `pop culture`, `economics`, `political events` |
| `difficulty` | string | ✅ | One of: `easy`, `medium`, `hard` |

#### Example

```json
{
  "questions": [
    {
      "question": "Which country hosted the 2016 Summer Olympics?",
      "type": "multiple_choice",
      "options": ["China", "Brazil", "UK", "Japan"],
      "answer": "Brazil",
      "topic": "sports",
      "difficulty": "easy"
    },
    {
      "question": "The Federal Reserve controls monetary policy in the US.",
      "type": "true_false",
      "answer": "true",
      "topic": "economics",
      "difficulty": "easy"
    },
    {
      "question": "What economic term describes a period of declining GDP for two consecutive quarters?",
      "type": "short_answer",
      "answer": "recession",
      "topic": "economics",
      "difficulty": "medium"
    }
  ]
}
```

> The question bank should contain a **large, mixed set of questions** spanning all difficulty levels and all four topic categories.

---

## Required Features

### 🔐 Authentication
- Prompt for username and password on startup.
- Allow new user registration in the same prompt flow.
- Passwords must be **hashed** before storage — plain text passwords are not acceptable.

### 📊 Score History
- Track and persist per-user statistics across sessions, including:
  - Scores per session
  - Topics and difficulties attempted
  - Any other useful performance metrics
- The history file must be **non-human-readable** (encoded/encrypted).
- Usernames may be discoverable from the file, but **passwords and scores must not be**.

### 👍 Question Feedback
- After each question, users can indicate whether they liked or disliked the question.
- This feedback must **influence future question selection** (e.g., liked questions appear more often; disliked ones are deprioritized).

### 📝 Editable Question Bank
- All questions live in a human-readable `questions.json` file.
- Engineers or users can modify this file directly to swap in questions for any subject, without changing any application code.

---

## Error Handling

| # | Error Condition | Handling Behavior |
|---|----------------|-------------------|
| 1 | `questions.json` not found | Raise `FileNotFoundError` with a descriptive message |
| 2 | Invalid user input | Raise `ValueError` and tell the user the expected input format |
| 3 | `questions.json` is empty or malformed | Display: *"Required data is missing from the file. Please check the file structure."* |

---

## Constraints

- **Language:** Python only
- **Interface:** Console / terminal only
- **No external dependencies** beyond the Python standard library (unless otherwise approved)
- No APIs, HTML, CSS, or GUI frameworks of any kind
