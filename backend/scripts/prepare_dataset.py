from __future__ import annotations

import csv
import hashlib
import hmac
import os
from pathlib import Path

import duckdb

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
DEFAULT_SOURCE = PROJECT_ROOT.parent / "Final" / "final_revised.csv"
DEFAULT_USERS = PROJECT_ROOT.parent / "tables_chosen" / "tbl_users_1.csv"
SOURCE = Path(os.getenv("CAPABILITY_RAW_DATA", str(DEFAULT_SOURCE))).expanduser()
USERS_SOURCE = Path(os.getenv("CAPABILITY_USERS_DATA", str(DEFAULT_USERS))).expanduser()
if not SOURCE.is_absolute():
    SOURCE = (PROJECT_ROOT / SOURCE).resolve()
if not USERS_SOURCE.is_absolute():
    USERS_SOURCE = (PROJECT_ROOT / USERS_SOURCE).resolve()
ATTEMPTS_PATH = Path(os.getenv("CAPABILITY_ATTEMPTS_PATH", "data/processed/question_attempts.csv"))
SUMMARY_PATH = Path(os.getenv("CAPABILITY_SUMMARY_PATH", "data/processed/student_topic_summary.csv"))
EMAIL_LOOKUP_PATH = Path(os.getenv("CAPABILITY_EMAIL_LOOKUP_PATH", "data/processed/student_email_lookup.csv"))
CHAPTER_SUMMARY_PATH = Path(os.getenv("CAPABILITY_CHAPTER_SUMMARY_PATH", "data/processed/student_latest_chapter_summary.csv"))
if not ATTEMPTS_PATH.is_absolute():
    ATTEMPTS_PATH = BACKEND_ROOT / ATTEMPTS_PATH
if not SUMMARY_PATH.is_absolute():
    SUMMARY_PATH = BACKEND_ROOT / SUMMARY_PATH
if not EMAIL_LOOKUP_PATH.is_absolute():
    EMAIL_LOOKUP_PATH = BACKEND_ROOT / EMAIL_LOOKUP_PATH
if not CHAPTER_SUMMARY_PATH.is_absolute():
    CHAPTER_SUMMARY_PATH = BACKEND_ROOT / CHAPTER_SUMMARY_PATH
EMAIL_LOOKUP_SECRET = os.getenv("CAPABILITY_EMAIL_LOOKUP_SECRET", "local-development-only-change-me")

REQUIRED_COLUMNS = {
    "user_id", "test_id", "Question_Topic", "Question_Type", "Question_complexity", "questioncomplexity_id",
    "question_id", "chapter_name", "user_choice_id", "Inserted_Date_Time", "SCQ_choice_id",
    "MCQ_choice1", "MCQ_choice2", "MCQ_choice3", "MCQ_choice4",
}


def validate_source(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(
            f"Raw dataset not found: {path}\nSet CAPABILITY_RAW_DATA to the full CSV path."
        )
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        columns = set(next(csv.reader(handle), []))
    missing = REQUIRED_COLUMNS - columns
    if missing:
        raise ValueError(f"Raw dataset is missing required columns: {', '.join(sorted(missing))}")


def write_email_lookup(path: Path) -> None:
    """Write IDs, display names, and keyed email digests; never copy raw emails/passwords."""
    if not USERS_SOURCE.is_file():
        raise FileNotFoundError(
            f"Student email table not found: {USERS_SOURCE}\nSet CAPABILITY_USERS_DATA to a users CSV path."
        )
    with USERS_SOURCE.open("r", encoding="utf-8-sig", newline="") as source, path.open(
        "w", encoding="utf-8", newline=""
    ) as target:
        reader = csv.DictReader(source)
        if not {"id", "email", "first_name", "last_name"}.issubset(reader.fieldnames or []):
            raise ValueError("Student users CSV must include id and email columns.")
        writer = csv.DictWriter(target, fieldnames=["user_id", "full_name", "email_hmac"])
        writer.writeheader()
        seen: set[tuple[int, str, str]] = set()
        for row in reader:
            try:
                user_id = int(float(row.get("id", "")))
            except (TypeError, ValueError):
                continue
            email = (row.get("email") or "").strip().casefold()
            full_name = " ".join(
                part.strip() for part in (row.get("first_name") or "", row.get("last_name") or "") if part.strip()
            )
            if user_id <= 0 or not email:
                continue
            digest = hmac.new(EMAIL_LOOKUP_SECRET.encode("utf-8"), email.encode("utf-8"), hashlib.sha256).hexdigest()
            record = (user_id, digest, full_name)
            if record not in seen:
                writer.writerow({"user_id": user_id, "full_name": full_name, "email_hmac": digest})
                seen.add(record)


def sql_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def main() -> None:
    validate_source(SOURCE)
    ATTEMPTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    EMAIL_LOOKUP_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHAPTER_SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = BACKEND_ROOT / "data" / "duckdb-tmp"
    temp_path.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    con.execute("SET memory_limit='3GB'")
    con.execute(f"SET temp_directory='{sql_path(temp_path)}'")
    con.execute("SET preserve_insertion_order=false")
    source_sql = sql_path(SOURCE)

    # The source export can repeat a question response across choice rows. Aggregate
    # selected/correct choice IDs per exact answer timestamp, then retain the latest
    # answer for each question in a student's test on that calendar day.
    question_sql = f"""
        WITH raw AS (
            SELECT
                TRY_CAST(TRY_CAST(user_id AS DOUBLE) AS BIGINT) AS user_id,
                COALESCE(NULLIF(TRIM(test_id), ''), 'unspecified-test') AS test_id,
                COALESCE(NULLIF(TRIM(Question_Topic), ''), 'Uncategorized') AS topic,
                CASE
                    WHEN LOWER(COALESCE(Question_Type, '')) LIKE '%multiple%' THEN 'mcq'
                    WHEN LOWER(COALESCE(Question_Type, '')) LIKE '%single%' THEN 'scq'
                    ELSE 'unknown'
                END AS question_type,
                COALESCE(
                    TRY_CAST(questioncomplexity_id AS DOUBLE),
                    CASE LOWER(COALESCE(Question_complexity, ''))
                        WHEN 'beginner' THEN 1.0 WHEN 'intermediate' THEN 2.0 WHEN 'expert' THEN 3.0
                        ELSE 1.0
                    END
                ) AS complexity_id,
                TRY_CAST(TRY_CAST(question_id AS DOUBLE) AS BIGINT) AS question_id,
                                CASE
                                        WHEN chapter_name IS NULL OR TRIM(chapter_name) = ''
                                            OR LOWER(TRIM(chapter_name)) IN ('nan', 'null', '0', 'no chapters added yet',
                                                                                                                'no chapters added', 'general chapter')
                                        THEN 'General'
                                        ELSE TRIM(chapter_name)
                                END AS chapter_name,
                TRY_CAST(TRY_CAST(user_choice_id AS DOUBLE) AS BIGINT) AS selected_choice,
                TRY_CAST(TRY_CAST(SCQ_choice_id AS DOUBLE) AS BIGINT) AS scq_correct,
                TRY_CAST(TRY_CAST(MCQ_choice1 AS DOUBLE) AS BIGINT) AS mcq_1,
                TRY_CAST(TRY_CAST(MCQ_choice2 AS DOUBLE) AS BIGINT) AS mcq_2,
                TRY_CAST(TRY_CAST(MCQ_choice3 AS DOUBLE) AS BIGINT) AS mcq_3,
                TRY_CAST(TRY_CAST(MCQ_choice4 AS DOUBLE) AS BIGINT) AS mcq_4,
                TRY_CAST(Inserted_Date_Time AS TIMESTAMP) AS answered_at
            FROM read_csv_auto('{source_sql}', header=true, all_varchar=true,
                               null_padding=true, ignore_errors=true, strict_mode=false,
                               sample_size=20000)
        ), valid AS (
            SELECT * FROM raw
            WHERE user_id > 0 AND question_id IS NOT NULL AND answered_at IS NOT NULL
              AND complexity_id BETWEEN 1 AND 3 AND question_type IN ('scq', 'mcq')
        ), grouped AS (
            SELECT
                user_id, test_id, topic, question_type, complexity_id, question_id, chapter_name,
                CAST(answered_at AS DATE) AS test_date,
                answered_at,
                LIST_SORT(LIST_DISTINCT(LIST_FILTER(LIST(selected_choice), x -> x IS NOT NULL AND x > 0))) AS selected_choices,
                MAX(scq_correct) AS scq_correct,
                LIST_SORT(LIST_DISTINCT(LIST_FILTER(
                    LIST(mcq_1) || LIST(mcq_2) || LIST(mcq_3) || LIST(mcq_4),
                    x -> x IS NOT NULL AND x > 0
                ))) AS mcq_correct_choices
            FROM valid
            GROUP BY user_id, test_id, topic, question_type, complexity_id,
                     question_id, chapter_name, CAST(answered_at AS DATE), answered_at
        ), ranked AS (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY user_id, test_id, topic, question_id, test_date
                ORDER BY answered_at DESC
            ) AS answer_order
            FROM grouped
        )
        SELECT user_id, test_id, CAST(test_date AS VARCHAR) AS test_date,
               topic, chapter_name, question_id, question_type, complexity_id,
               CASE
                   WHEN question_type = 'scq' THEN
                       CASE WHEN LIST_CONTAINS(selected_choices, scq_correct) THEN 1 ELSE 0 END
                   WHEN question_type = 'mcq' THEN
                       CASE WHEN LEN(selected_choices) > 0 AND selected_choices = mcq_correct_choices THEN 1 ELSE 0 END
                   ELSE 0
               END AS is_correct
        FROM ranked
        WHERE answer_order = 1
    """

    con.execute(f"CREATE TEMP TABLE attempts AS {question_sql}")
    con.execute(f"COPY (SELECT * FROM attempts) TO '{sql_path(ATTEMPTS_PATH)}' (HEADER, DELIMITER ',')")
    summary_sql = """
        SELECT
            user_id,
            topic,
            test_date,
            COUNT(DISTINCT test_id) AS tests_attempted,
            COUNT(*) AS total_questions,
            SUM(is_correct) AS total_correct,
            SUM(CASE WHEN is_correct = 1 THEN complexity_id ELSE 0 END) AS weighted_score,
            SUM(complexity_id) AS max_score,
            ROUND(100.0 * SUM(CASE WHEN is_correct = 1 THEN complexity_id ELSE 0 END)
                  / NULLIF(SUM(complexity_id), 0), 2) AS score_pct
        FROM attempts
        GROUP BY user_id, topic, test_date
        ORDER BY user_id, topic, test_date
    """
    con.execute(f"COPY ({summary_sql}) TO '{sql_path(SUMMARY_PATH)}' (HEADER, DELIMITER ',')")
    chapter_summary_sql = """
        WITH latest AS (
            SELECT user_id, topic, MAX(test_date) AS latest_test_date
            FROM attempts
            GROUP BY user_id, topic
        )
        SELECT
            a.user_id,
            a.topic,
            a.test_date,
            a.chapter_name,
            COUNT(DISTINCT a.test_id) AS tests_attempted,
            COUNT(*) AS total_questions,
            SUM(a.is_correct) AS total_correct,
            SUM(CASE WHEN a.is_correct = 1 THEN a.complexity_id ELSE 0 END) AS weighted_score,
            SUM(a.complexity_id) AS max_score,
            ROUND(100.0 * SUM(CASE WHEN a.is_correct = 1 THEN a.complexity_id ELSE 0 END)
                  / NULLIF(SUM(a.complexity_id), 0), 2) AS score_pct
        FROM attempts a
        JOIN latest l ON a.user_id = l.user_id AND a.topic = l.topic AND a.test_date = l.latest_test_date
        GROUP BY a.user_id, a.topic, a.test_date, a.chapter_name
        ORDER BY a.user_id, a.topic, a.chapter_name
    """
    con.execute(f"COPY ({chapter_summary_sql}) TO '{sql_path(CHAPTER_SUMMARY_PATH)}' (HEADER, DELIMITER ',')")
    write_email_lookup(EMAIL_LOOKUP_PATH)
    rows = con.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
    users = con.execute("SELECT COUNT(DISTINCT user_id) FROM attempts").fetchone()[0]
    topics = con.execute("SELECT COUNT(DISTINCT topic) FROM attempts").fetchone()[0]
    print(f"Prepared {rows:,} question attempts for {users:,} students across {topics:,} topics.")
    print(f"Question-level file: {ATTEMPTS_PATH}")
    print(f"Summary file: {SUMMARY_PATH}")
    print(f"Latest-test chapter summary: {CHAPTER_SUMMARY_PATH}")
    print(f"Email/name lookup index (keyed email digests only): {EMAIL_LOOKUP_PATH}")


if __name__ == "__main__":
    main()
