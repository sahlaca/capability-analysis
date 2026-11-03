import csv
import os
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_dataset.py"
FIELDS = [
    "user_id", "test_id", "Question_Topic", "Question_Type", "Question_complexity",
    "questioncomplexity_id", "question_id", "chapter_name", "user_choice_id",
    "Inserted_Date_Time", "SCQ_choice_id", "MCQ_choice1", "MCQ_choice2", "MCQ_choice3", "MCQ_choice4",
]


def test_prepare_dataset_deduplicates_choices_and_scores_complexity(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    users = tmp_path / "users.csv"
    attempts = tmp_path / "out" / "attempts.csv"
    summary = tmp_path / "out" / "summary.csv"
    email_lookup = tmp_path / "out" / "email_lookup.csv"
    chapter_summary = tmp_path / "out" / "chapter_summary.csv"
    records = [
        {"user_id": 100, "test_id": "SQL-1", "Question_Topic": "SQL", "Question_Type": "Single Choice Question",
         "Question_complexity": "Beginner", "questioncomplexity_id": 1, "question_id": 501,
         "chapter_name": "Basics", "user_choice_id": "2.0", "Inserted_Date_Time": "2025-01-05 10:00:00",
         "SCQ_choice_id": 2, "MCQ_choice1": 0, "MCQ_choice2": 0, "MCQ_choice3": 0, "MCQ_choice4": 0},
        {"user_id": 100, "test_id": "SQL-1", "Question_Topic": "SQL", "Question_Type": "Multiple Choice Question",
         "Question_complexity": "Expert", "questioncomplexity_id": 3, "question_id": 502,
         "chapter_name": "Joins", "user_choice_id": 4, "Inserted_Date_Time": "2025-01-05 10:01:00",
         "SCQ_choice_id": 0, "MCQ_choice1": 4, "MCQ_choice2": 5, "MCQ_choice3": 0, "MCQ_choice4": 0},
        {"user_id": 100, "test_id": "SQL-1", "Question_Topic": "SQL", "Question_Type": "Multiple Choice Question",
         "Question_complexity": "Expert", "questioncomplexity_id": 3, "question_id": 502,
         "chapter_name": "Joins", "user_choice_id": 5, "Inserted_Date_Time": "2025-01-05 10:01:00",
         "SCQ_choice_id": 0, "MCQ_choice1": 4, "MCQ_choice2": 5, "MCQ_choice3": 0, "MCQ_choice4": 0},
        {"user_id": 100, "test_id": "SQL-1", "Question_Topic": "SQL", "Question_Type": "Single Choice Question",
         "Question_complexity": "Beginner", "questioncomplexity_id": 1, "question_id": 503,
         "chapter_name": "No Chapters added yet", "user_choice_id": 8, "Inserted_Date_Time": "2025-01-05 10:02:00",
         "SCQ_choice_id": 9, "MCQ_choice1": 0, "MCQ_choice2": 0, "MCQ_choice3": 0, "MCQ_choice4": 0},
    ]
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(records)
    with users.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "first_name", "last_name", "email", "password"])
        writer.writeheader()
        writer.writerows([
            {"id": 100, "first_name": "Student", "last_name": "Example", "email": "Student@Example.com", "password": "never-copy-this"},
            {"id": 0, "first_name": "Admin", "last_name": "Example", "email": "admin@example.com", "password": "not-exported"},
        ])

    env = os.environ.copy()
    env.update({
        "CAPABILITY_RAW_DATA": str(source),
        "CAPABILITY_USERS_DATA": str(users),
        "CAPABILITY_ATTEMPTS_PATH": str(attempts),
        "CAPABILITY_SUMMARY_PATH": str(summary),
        "CAPABILITY_EMAIL_LOOKUP_PATH": str(email_lookup),
        "CAPABILITY_CHAPTER_SUMMARY_PATH": str(chapter_summary),
        "CAPABILITY_EMAIL_LOOKUP_SECRET": "test-secret",
    })
    subprocess.run([sys.executable, str(SCRIPT)], check=True, env=env, capture_output=True, text=True)

    with attempts.open(encoding="utf-8", newline="") as handle:
        attempt_rows = list(csv.DictReader(handle))
    with summary.open(encoding="utf-8", newline="") as handle:
        summary_rows = list(csv.DictReader(handle))
    with email_lookup.open(encoding="utf-8", newline="") as handle:
        email_rows = list(csv.DictReader(handle))
    with chapter_summary.open(encoding="utf-8", newline="") as handle:
        chapter_rows = list(csv.DictReader(handle))

    assert len(attempt_rows) == 3
    assert {row["question_id"]: row["is_correct"] for row in attempt_rows} == {"501": "1", "502": "1", "503": "0"}
    assert len(summary_rows) == 1
    assert summary_rows[0]["total_questions"] == "3"
    assert summary_rows[0]["weighted_score"] == "4.0"
    assert summary_rows[0]["max_score"] == "5.0"
    assert summary_rows[0]["score_pct"] == "80.0"
    assert email_rows[0]["user_id"] == "100"
    assert set(email_rows[0]) == {"user_id", "full_name", "email_hmac"}
    assert email_rows[0]["full_name"] == "Student Example"
    assert "Student@Example.com" not in email_lookup.read_text(encoding="utf-8")
    assert "never-copy-this" not in email_lookup.read_text(encoding="utf-8")
    assert {row["chapter_name"] for row in chapter_rows} == {"Basics", "Joins", "General"}
    assert {row["test_date"] for row in chapter_rows} == {"2025-01-05"}
